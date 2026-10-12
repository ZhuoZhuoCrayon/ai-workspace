#!/usr/bin/env python3
"""同一指标在不同上报范围的元信息不一致时，各存法的体积、读取与写入代价。

一个大数据源（20,000 指标 × 50 上报范围 = 1,000,000 成员）加 500 个背景数据源（各 200 指标 × 5 范围），
不一致比例 1%、10%、50% 依次装载，每档比较：
  1   每范围一份：成员内联完整元信息，另加指纹列供补报比较；1n 为不加指纹列，只量体积
  2   定义加例外（现方案）：定义表存默认元信息，成员只在与定义不同时内联完整元信息
  3   元信息值表：按 (group_id, 指纹) 去重，每个成员引用一个值
  4   定义加例外引用（对照）：定义表存默认元信息，例外取值按指纹去重进值表，成员只存定长引用，0 表示沿用定义
脚本自带独立 mysqld（端口 33310，数据目录 $TMPDIR/cm-meta-layout），与 explode.py 互不影响。

在本目录执行：
    # 冒烟：大数据源缩小为 1,000 指标 × 10 范围、背景 20 个数据源，每个用例只跑 1 + 3 次
    uv run --quiet --with 'pymysql==1.1.1' python meta_layout.py run --smoke
    # 正式
    uv run --quiet --with 'pymysql==1.1.1' python meta_layout.py run --out results/meta_layout.txt
    # 删除数据目录
    uv run --quiet --with 'pymysql==1.1.1' python meta_layout.py clean
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import pymysql
from pymysql.converters import escape_string
from pymysql.cursors import Cursor, DictCursor

from catalog import definition_meta, metric_kind, metric_names
from explode import GIB, Output, dir_size, execute, log, mib, parse_bytes, pool_reads, port_in_use

PORT: int = 33310
WORK: str = os.path.join(os.environ.get("TMPDIR", "/tmp"), "cm-meta-layout")
SOCKET: str = os.path.join(WORK, "mysql.sock")
DATABASE: str = "cm_meta_layout"
ROOT: str = os.path.dirname(os.path.abspath(__file__))
DISK_RESERVE: int = 3 * GIB
# 每档装载前的磁盘预估：全部存法的表、E 期间的页分裂与 undo，实测值见输出
EST_MEMBER_BYTES: int = 2_000
LOAD_CHUNK_ROWS: int = 100_000
LAST_SEEN: str = "2026-10-11 00:00:00.000000"
NOW: str = "2026-10-12 00:00:00.000000"
RATIOS: tuple[float, ...] = (0.01, 0.10, 0.50)
BATCH: int = 1_000
CHANGED: int = 10
SEGMENT: int = 10_000
WRITE_CHUNK: int = 1_000
POINT_SAMPLES: int = 1_000
# 平台外推口径：M2 成员数与定义数，见 PLAN.md 模型表
PLATFORM_MEMBERS: int = 40_091_444
PLATFORM_DEFINITIONS: int = 951_119


@dataclass(frozen=True)
class Shape:
    metrics: int
    scopes: int
    background: int
    background_metrics: int
    background_scopes: int

    @property
    def members(self) -> int:
        return self.metrics * self.scopes + self.background * self.background_metrics * self.background_scopes


FULL: Shape = Shape(20_000, 50, 500, 200, 5)
SMOKE_SHAPE: Shape = Shape(1_000, 10, 20, 200, 5)


@dataclass(frozen=True)
class Budget:
    warmup: int
    iterations: int


POINT: Budget = Budget(100, 1_000)
SCOPE: Budget = Budget(5, 50)
GROUP: Budget = Budget(3, 30)
VOTE: Budget = Budget(1, 10)
APPLY: Budget = Budget(30, 300)
SMOKE_BUDGET: Budget = Budget(1, 3)


@dataclass(frozen=True)
class Config:
    shape: Shape
    ratios: tuple[float, ...]
    layouts: tuple[str, ...]
    smoke: bool

    def budget(self, budget: Budget) -> Budget:
        return SMOKE_BUDGET if self.smoke else budget


def percentile(values: Sequence[float], p: float) -> float:
    ordered: list[float] = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


# ---------------------------------------------------------------- 数据画像


@dataclass(frozen=True)
class Source:
    """一个数据源；全部范围上报全部指标，指标、范围与成员 id 在数据源之间连续分配。"""

    group_id: int
    metrics: int
    scopes: int
    big: bool
    metric_base: int
    scope_base: int
    member_base: int

    @property
    def members(self) -> int:
        return self.metrics * self.scopes

    def metric_id(self, i: int) -> int:
        return self.metric_base + i + 1

    def scope_id(self, j: int) -> int:
        return self.scope_base + j + 1

    def index(self, scope_id: int, metric_id: int) -> int:
        """成员在数据源内按唯一键 (范围, 指标) 排序的下标。"""
        return (scope_id - self.scope_base - 1) * self.metrics + metric_id - self.metric_base - 1


def plan_sources(shape: Shape) -> list[Source]:
    """大数据源的 group_id 位于背景数据源中间，两侧都有其他分组的索引条目。"""
    big_id: int = shape.background // 2 + 1
    sources: list[Source] = []
    metric_base: int = 0
    scope_base: int = 0
    member_base: int = 0
    for g in range(1, shape.background + 2):
        big: bool = g == big_id
        metrics: int = shape.metrics if big else shape.background_metrics
        scopes: int = shape.scopes if big else shape.background_scopes
        sources.append(Source(g, metrics, scopes, big, metric_base, scope_base, member_base))
        metric_base += metrics
        scope_base += scopes
        member_base += metrics * scopes
    return sources


def canonical(meta: dict[str, Any]) -> str:
    """MySQL JSON 的输出文本：键按字节长度再按字节序排列，分隔符为 ', ' 与 ': '。

    客户端指纹取这段文本的 MD5，与服务端 MD5(meta) 相等，启动时由 check_canonical 校验。
    """
    keys: list[str] = sorted(meta, key=lambda k: (len(k.encode()), k.encode()))
    return json.dumps({k: meta[k] for k in keys})


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


@dataclass
class Texts:
    names: list[str] = field(default_factory=list)
    originals: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    default: list[str] = field(default_factory=list)
    default_fp: list[str] = field(default_factory=list)
    variant: list[str] = field(default_factory=list)
    variant_fp: list[str] = field(default_factory=list)


def build_texts(src: Source) -> Texts:
    """默认取值照抄 catalog.py 的定义字段，大数据源的 unit 改为 ms；不一致取值是另一 SDK 版本的上报，
    description、temporality、interval 不同，unit 相同，所以 E 对全部成员都是 ms → s。"""
    texts: Texts = Texts()
    for i in range(src.metrics):
        name, original = metric_names(i)
        meta: dict[str, Any] = json.loads(definition_meta(src.group_id, i, name, original))
        if src.big:
            meta["unit"] = "ms"
        legacy: dict[str, Any] = {
            **meta,
            "description": meta["description"] + " (legacy sdk)",
            "temporality": "delta",
            "interval": 30,
        }
        default: str = canonical(meta)
        variant: str = canonical(legacy)
        texts.names.append(name)
        texts.originals.append(original)
        texts.kinds.append(metric_kind(i))
        texts.default.append(default)
        texts.default_fp.append(md5_hex(default))
        texts.variant.append(variant)
        texts.variant_fp.append(md5_hex(variant))
    return texts


def build_flags(src: Source, ratio: float) -> bytearray:
    """按固定种子在数据源内均匀抽取恰好 ratio 的成员，标为上报不一致取值。"""
    flags: bytearray = bytearray(src.members)
    rng: random.Random = random.Random(f"{ratio}:{src.group_id}")
    for k in rng.sample(range(src.members), round(src.members * ratio)):
        flags[k] = 1
    return flags


@dataclass(frozen=True)
class Usage:
    """每个指标是否有成员沿用默认取值、是否有成员上报不一致取值，值表只装载被引用的取值。"""

    default: bytearray
    variant: bytearray


def metric_usage(src: Source, flags: bytearray) -> Usage:
    usage: Usage = Usage(bytearray(src.metrics), bytearray(src.metrics))
    for k, flag in enumerate(flags):
        (usage.variant if flag else usage.default)[k % src.metrics] = 1
    return usage


@dataclass(frozen=True)
class Report:
    scope_id: int
    metric_id: int
    field_name: str
    text: str
    fp: str


@dataclass
class State:
    """大数据源每个成员当前上报的取值：不一致标记加 D 的改动，D 与 E 的上报由它生成。"""

    big: Source
    texts: Texts
    flags: bytearray
    overrides: dict[int, str] = field(default_factory=dict)

    def text(self, k: int) -> str:
        override: str | None = self.overrides.get(k)
        if override is not None:
            return override
        i: int = k % self.big.metrics
        return self.texts.variant[i] if self.flags[k] else self.texts.default[i]


def build_batches(state: State, count: int, seed: str) -> list[list[Report]]:
    """每批随机抽 BATCH 个成员，其中 CHANGED 个改为从未出现的新取值（description 加修订号），其余重报当前取值。"""
    rng: random.Random = random.Random(seed)
    big: Source = state.big
    batches: list[list[Report]] = []
    serial: int = 0
    for _ in range(count):
        picks: list[int] = rng.sample(range(big.members), BATCH)
        changed: set[int] = set(rng.sample(range(BATCH), CHANGED))
        batch: list[Report] = []
        for pos, k in enumerate(picks):
            text: str = state.text(k)
            if pos in changed:
                serial += 1
                meta: dict[str, Any] = json.loads(text)
                meta["description"] = f"{meta['description'].split(' rev ')[0]} rev {serial}"
                text = canonical(meta)
                state.overrides[k] = text
            j, i = divmod(k, big.metrics)
            batch.append(Report(big.scope_id(j), big.metric_id(i), state.texts.names[i], text, md5_hex(text)))
        batches.append(batch)
    return batches


@dataclass
class Upgrade:
    """E 的上报：成员下标 → 把当前取值的 unit 改为 s 后的文本与指纹。"""

    texts: list[str]
    fps: list[str]


def build_upgrade(state: State) -> Upgrade:
    cache: dict[str, tuple[str, str]] = {}
    plan: Upgrade = Upgrade([], [])
    for k in range(state.big.members):
        old: str = state.text(k)
        hit: tuple[str, str] | None = cache.get(old)
        if hit is None:
            new: str = canonical({**json.loads(old), "unit": "s"})
            hit = (new, md5_hex(new))
            cache[old] = hit
        plan.texts.append(hit[0])
        plan.fps.append(hit[1])
    return plan


@dataclass(frozen=True)
class Probes:
    """读取样本：A 为大数据源随机 (范围, 指标)，B 为大数据源全部范围。"""

    points: list[tuple[int, int, int, str]]
    scopes: list[tuple[int, int]]


def build_probes(big: Source, texts: Texts, count: int) -> Probes:
    rng: random.Random = random.Random("probes")
    points: list[tuple[int, int, int, str]] = []
    for k in rng.sample(range(big.members), min(count, big.members)):
        j, i = divmod(k, big.metrics)
        points.append((big.group_id, big.scope_id(j), big.metric_id(i), texts.names[i]))
    return Probes(points, [(big.group_id, big.scope_id(j)) for j in range(big.scopes)])


# ---------------------------------------------------------------- MySQL


def free_disk() -> int:
    return shutil.disk_usage(WORK if os.path.isdir(WORK) else os.path.dirname(WORK)).free


def connect(raw: bool = False, database: str | None = DATABASE) -> pymysql.Connection:
    """raw 连接不做类型转换，读取计时不含 Python 解码；补报与升级用普通连接，取回 int 与 str。"""
    encoders_only: dict[Any, Any] = {k: v for k, v in pymysql.converters.conversions.items() if not isinstance(k, int)}
    options: dict[str, Any] = {"conv": encoders_only} if raw else {}
    return pymysql.connect(
        unix_socket=SOCKET,
        user="root",
        database=database,
        local_infile=True,
        autocommit=True,
        charset="utf8mb4",
        **options,
    )


def fetch(cur: Cursor, sql: str, params: Sequence[Any] | None = None) -> tuple[Any, ...]:
    cur.execute(sql, params)
    return cur.fetchall()


def start_server(buffer_pool: str, redo: str) -> subprocess.Popen[bytes]:
    """与 explode.py 相同的启动参数，只换端口与数据目录。"""
    if port_in_use(PORT):
        raise SystemExit(f"port {PORT} is already in use")
    datadir: str = os.path.join(WORK, "data")
    tmpdir: str = os.path.join(WORK, "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    os.makedirs(os.path.join(WORK, "load"), exist_ok=True)
    base: list[str] = ["mysqld", "--no-defaults", f"--datadir={datadir}", f"--innodb-redo-log-capacity={redo}"]
    if not os.path.isdir(os.path.join(datadir, "mysql")):
        with open(os.path.join(WORK, "init.log"), "wb") as fp:
            subprocess.run([*base, "--initialize-insecure"], check=True, stdout=fp, stderr=subprocess.STDOUT)
    server: list[str] = [
        *base,
        f"--socket={SOCKET}",
        f"--pid-file={os.path.join(WORK, 'mysqld.pid')}",
        f"--port={PORT}",
        "--bind-address=127.0.0.1",
        f"--tmpdir={tmpdir}",
        "--skip-log-bin",
        "--skip-mysqlx",
        "--local-infile=ON",
        "--character-set-server=utf8mb4",
        f"--innodb-buffer-pool-size={buffer_pool}",
        "--innodb-flush-log-at-trx-commit=1",
        "--max-allowed-packet=256M",
    ]
    with open(os.path.join(WORK, "mysqld.log"), "ab") as fp:
        proc: subprocess.Popen[bytes] = subprocess.Popen(server, stdout=fp, stderr=subprocess.STDOUT)
    for _ in range(180):
        if proc.poll() is not None:
            raise SystemExit(f"mysqld exited with {proc.returncode}, see {WORK}/mysqld.log")
        try:
            conn: pymysql.Connection = connect(database=None)
        except pymysql.err.OperationalError:
            time.sleep(1)
            continue
        execute(conn, f"DROP DATABASE IF EXISTS {DATABASE}")
        execute(conn, f"CREATE DATABASE {DATABASE}")
        conn.close()
        return proc
    proc.terminate()
    raise SystemExit("mysqld did not accept connections within 180 s")


def stop_server(proc: subprocess.Popen[bytes]) -> None:
    try:
        conn: pymysql.Connection = connect(database=None)
        execute(conn, "SHUTDOWN")
        conn.close()
    except pymysql.err.Error:
        proc.terminate()
    proc.wait(timeout=600)


class Loader:
    """把行写入临时 TSV，按块执行 LOAD DATA LOCAL INFILE。"""

    def __init__(self, conn: pymysql.Connection, table: str, columns: Sequence[str]) -> None:
        self.conn = conn
        self.table = table
        self.columns: list[str] = list(columns)
        self.lines: list[str] = []
        self.total: int = 0

    def add(self, line: str) -> None:
        self.lines.append(line)
        if len(self.lines) >= LOAD_CHUNK_ROWS:
            self.flush()

    def flush(self) -> None:
        if not self.lines:
            return
        with tempfile.NamedTemporaryFile(
            "w", suffix=".tsv", delete=False, encoding="utf-8", dir=os.path.join(WORK, "load")
        ) as fp:
            fp.write("\n".join(self.lines) + "\n")
            path: str = fp.name
        try:
            execute(
                self.conn,
                f"LOAD DATA LOCAL INFILE %s INTO TABLE {self.table} CHARACTER SET utf8mb4 "
                f"FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' ({', '.join(self.columns)})",
                (path,),
            )
        finally:
            os.unlink(path)
        self.total += len(self.lines)
        self.lines = []


def lit(value: int | str | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return f"'{escape_string(value)}'"


def tuples(rows: Sequence[Sequence[int | str | None]]) -> str:
    return ", ".join("(" + ", ".join(lit(v) for v in row) + ")" for row in rows)


def ints(values: Sequence[int]) -> str:
    return ", ".join(str(v) for v in values)


def quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upsert(
    cur: Cursor, table: str, columns: Sequence[str], rows: Sequence[Sequence[int | str | None]], sets: str
) -> int:
    """每 WRITE_CHUNK 行一条 INSERT ... ON DUPLICATE KEY UPDATE，行带主键时按主键命中；返回语句数。"""
    statements: int = 0
    for k in range(0, len(rows), WRITE_CHUNK):
        cur.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES {tuples(rows[k : k + WRITE_CHUNK])} "
            f"AS new ON DUPLICATE KEY UPDATE {sets}"
        )
        statements += 1
    return statements


def ensure_values(cur: Cursor, table: str, group_id: int, wanted: dict[str, str]) -> tuple[dict[str, int], int, int]:
    """按 (group_id, 指纹) 查值表，缺失的插入后重查；返回指纹 → id、语句数与插入行数。"""
    if not wanted:
        return {}, 0, 0
    lookup: str = VALUE_LOOKUP.format(table=table)
    found: dict[str, int] = dict(fetch(cur, lookup.format(g=group_id, fps=quoted(list(wanted)))))
    statements: int = 1
    missing: list[str] = [fp for fp in wanted if fp not in found]
    if missing:
        rows: list[tuple[int | str | None, ...]] = [(group_id, fp, wanted[fp]) for fp in missing]
        statements += upsert(cur, table, VALUE_COLUMNS, rows, "id = id")
        found.update(fetch(cur, lookup.format(g=group_id, fps=quoted(missing))))
        statements += 1
    return found, statements, len(missing)


def keyset_sql(columns: str, source: str, ref: str) -> str:
    """沿成员唯一键 (group_id, report_scope_id, ref) 分段读取，前两列必须是 report_scope_id 与引用列。"""
    return (
        f"SELECT {columns} FROM {source} WHERE m.group_id = %s "
        f"AND (m.report_scope_id > %s OR (m.report_scope_id = %s AND m.{ref} > %s)) "
        f"ORDER BY m.report_scope_id, m.{ref} LIMIT {SEGMENT}"
    )


def keyset(cur: Cursor, sql: str, group_id: int, last: tuple[int, int]) -> tuple[Any, ...]:
    return fetch(cur, sql, (group_id, last[0], last[0], last[1]))


def explain(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None) -> str:
    with conn.cursor(DictCursor) as cur:
        cur.execute("EXPLAIN " + sql, params)
        plans: list[dict[str, Any]] = list(cur.fetchall())
    return "; ".join(
        f"{p['table']}:{p['key'] or 'ALL'}/{p['type']} rows={p['rows'] if p['rows'] is not None else '-'}"
        f" [{p['Extra'] or ''}]"
        for p in plans
    )


# ---------------------------------------------------------------- 表结构

ID: str = "id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY"
FINGERPRINT: str = "fingerprint CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL"
DEFINITION_COLUMNS: list[str] = [
    "id",
    "group_id",
    "field_name",
    "original_name",
    "metric_type",
    "meta",
    "fingerprint",
    "seen_at",
]
VALUE_COLUMNS: list[str] = ["group_id", "fingerprint", "meta"]


def member_columns(ref: str, payload: Sequence[str]) -> list[str]:
    return ["id", "group_id", "report_scope_id", ref, "last_seen", *payload]


def member_ddl(table: str, ref: str, payload: Sequence[str]) -> str:
    return (
        f"CREATE TABLE {table} ({ID}, group_id INT NOT NULL, report_scope_id BIGINT NOT NULL, "
        f"{ref} BIGINT NOT NULL, last_seen DATETIME(6) NOT NULL, {', '.join(payload)}, "
        f"UNIQUE KEY uk_member (group_id, report_scope_id, {ref}), KEY idx_group_{ref} (group_id, {ref})"
        ") DEFAULT CHARSET=utf8mb3"
    )


def definition_ddl(table: str) -> str:
    return (
        f"CREATE TABLE {table} ({ID}, group_id INT NOT NULL, field_name VARCHAR(255) COLLATE utf8mb3_bin NOT NULL, "
        "original_name VARCHAR(255) COLLATE utf8mb3_bin NOT NULL, metric_type VARCHAR(16) NOT NULL, meta JSON NULL, "
        f"{FINGERPRINT}, seen_at DATETIME(6) NOT NULL, UNIQUE KEY uk_group_name (group_id, field_name)"
        ") DEFAULT CHARSET=utf8mb3"
    )


def value_ddl(table: str) -> str:
    return (
        f"CREATE TABLE {table} ({ID}, group_id INT NOT NULL, {FINGERPRINT}, meta JSON NULL, "
        "UNIQUE KEY uk_group_fingerprint (group_id, fingerprint)) DEFAULT CHARSET=utf8mb3"
    )


def emit_members(loader: Loader, src: Source, tails: Sequence[tuple[str, str]], flags: bytearray) -> None:
    """成员按唯一键 (范围, 指标) 顺序装载，tails[i] 为指标 i 一致、不一致两种取值的行尾。"""
    for j in range(src.scopes):
        head: str = f"\t{src.group_id}\t{src.scope_id(j)}"
        base: int = j * src.metrics
        for i in range(src.metrics):
            loader.add(f"{src.member_base + base + i + 1}{head}{tails[i][flags[base + i]]}")


def emit_definitions(loader: Loader, src: Source, texts: Texts) -> None:
    """定义取默认值，与 metric_id 同号；50% 档的默认值即升级前的旧取值，例外是尚未晋升的新取值。"""
    for i in range(src.metrics):
        loader.add(
            f"{src.metric_id(i)}\t{src.group_id}\t{texts.names[i]}\t{texts.originals[i]}\t{texts.kinds[i]}\t"
            f"{texts.default[i]}\t{texts.default_fp[i]}\t{LAST_SEEN}"
        )


# ---------------------------------------------------------------- 用例与计时

Run = Callable[[Cursor], tuple[int, int]]


@dataclass
class ReadCase:
    name: str
    budget: Budget
    runs: list[Run]
    sql: str
    params: tuple[Any, ...]


def run_statement(cur: Cursor, sql: str, params: tuple[Any, ...]) -> tuple[int, int]:
    return len(fetch(cur, sql, params)), 1


def statement_case(name: str, budget: Budget, sql: str, param_sets: Sequence[tuple[Any, ...]]) -> ReadCase:
    runs: list[Run] = [partial(run_statement, sql=sql, params=p) for p in param_sets]
    return ReadCase(name, budget, runs, sql, param_sets[0])


def steps_case(
    name: str,
    budget: Budget,
    run: Callable[..., tuple[int, int]],
    param_sets: Sequence[tuple[Any, ...]],
    sql: str,
    explain_params: tuple[Any, ...],
) -> ReadCase:
    """多语句用例，sql 与 explain_params 为首条语句及其参数，用于 EXPLAIN。"""
    runs: list[Run] = [partial(run, params=p) for p in param_sets]
    return ReadCase(name, budget, runs, sql, explain_params)


@dataclass
class Timing:
    name: str
    samples: list[float] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)
    stmts: list[int] = field(default_factory=list)
    disk_reads: int = 0

    def add(self, elapsed: float, rows: int, stmts: int) -> None:
        self.samples.append(elapsed)
        self.rows.append(rows)
        self.stmts.append(stmts)

    @property
    def p50(self) -> float:
        return statistics.median(self.samples)

    @property
    def p95(self) -> float:
        return percentile(self.samples, 0.95)

    @property
    def mean_rows(self) -> float:
        return statistics.mean(self.rows)

    @property
    def mean_stmts(self) -> float:
        return statistics.mean(self.stmts)

    def line(self) -> str:
        return (
            f"{self.name:<24}{self.p50:>11,.3f}{self.p95:>11,.3f}{max(self.samples):>11,.3f}"
            f"{self.mean_rows:>9,.0f}{self.mean_stmts:>7.1f}{len(self.samples):>6}{self.disk_reads:>9,}"
        )


TIMING_HEADER: str = (
    f"{'case':<24}{'p50 ms':>11}{'p95 ms':>11}{'max ms':>11}{'rows':>9}{'stmts':>7}{'runs':>6}{'disk rd':>9}"
)


def measure(label: str, conn: pymysql.Connection, case: ReadCase, config: Config) -> Timing:
    """请求序列只由用例名决定，各存法使用同一组样本与同一顺序；disk rd 为计时期间缓冲池未命中的页读取。"""
    budget: Budget = config.budget(case.budget)
    timing: Timing = Timing(label)
    rng: random.Random = random.Random(case.name)
    before: int = 0
    with conn.cursor() as cur:
        for i in range(budget.warmup + budget.iterations):
            if i == budget.warmup:
                before = pool_reads(conn)
            run: Run = case.runs[rng.randrange(len(case.runs))]
            start: float = time.perf_counter()
            rows, stmts = run(cur)
            elapsed: float = (time.perf_counter() - start) * 1000
            if i >= budget.warmup:
                timing.add(elapsed, rows, stmts)
    timing.disk_reads = pool_reads(conn) - before
    log(f"{label}: p50 {timing.p50:,.3f} ms, rows {timing.mean_rows:,.0f}")
    return timing


@dataclass
class Step:
    """E 的一个步骤：按成员唯一键每段 SEGMENT 行，一段一个事务；rows 为写入行数。"""

    name: str
    rows: int = 0
    statements: int = 0
    segments: list[float] = field(default_factory=list)
    seconds: float = 0.0

    def add(self, elapsed: float, rows: int, statements: int) -> None:
        self.segments.append(elapsed * 1000)
        self.seconds += elapsed
        self.rows += rows
        self.statements += statements

    def line(self) -> str:
        p50: float = percentile(self.segments, 0.5) if self.segments else 0.0
        p95: float = percentile(self.segments, 0.95) if self.segments else 0.0
        return (
            f"{self.name:<40}{self.rows:>11,}{self.statements:>8,}{len(self.segments):>6}{self.seconds:>9.2f}"
            f"{p50:>10.1f}{p95:>10.1f}{self.rows / max(self.seconds, 1e-9):>11,.0f}"
        )


STEP_HEADER: str = (
    f"{'step':<40}{'rows':>11}{'stmts':>8}{'segs':>6}{'total s':>9}{'seg p50':>10}{'seg p95':>10}{'rows/s':>11}"
)


def pick_winners(counts: dict[int, dict[Any, int]], empty: Any) -> dict[int, Any]:
    """例外取值中成员数最多、且多于沿用定义的成员时晋升；平票取较小的取值。"""
    winners: dict[int, Any] = {}
    for ref, bucket in counts.items():
        kept: int = bucket.get(empty, 0)
        best: tuple[int, Any] | None = None
        for value, count in bucket.items():
            if value == empty:
                continue
            if best is None or count > best[0] or (count == best[0] and value < best[1]):
                best = (count, value)
        if best is not None and best[0] > kept:
            winners[ref] = best[1]
    return winners


# ---------------------------------------------------------------- 存法


class Layout:
    """存法的建表、装载、读取用例、补报与全体升级；引用列对存法 1、3 是 metric_id，对存法 2、4 是定义 id，
    合成数据中两者同号。"""

    key: str = ""
    title: str = ""
    member: str = ""
    ref: str = ""
    definition: str = ""
    value: str = ""
    volume_only: bool = False
    compacts: bool = False

    def __init__(self) -> None:
        self.ddl: dict[str, str] = {}
        self.columns: dict[str, list[str]] = {}
        self.sql: dict[str, list[str]] = {}

    @property
    def tables(self) -> list[str]:
        return list(self.ddl)

    @property
    def label(self) -> str:
        return f"{self.key} {self.title}"

    def create(self, conn: pymysql.Connection) -> None:
        for table, ddl in self.ddl.items():
            execute(conn, f"DROP TABLE IF EXISTS {table}")
            execute(conn, ddl)

    def drop(self, conn: pymysql.Connection) -> None:
        for table in self.tables:
            execute(conn, f"DROP TABLE IF EXISTS {table}")

    def loaders(self, conn: pymysql.Connection) -> dict[str, Loader]:
        return {t: Loader(conn, t, self.columns[t]) for t in self.tables}

    def emit(self, loaders: dict[str, Loader], src: Source, texts: Texts, flags: bytearray, usage: Usage) -> None:
        raise NotImplementedError

    def read_cases(self, probes: Probes) -> list[ReadCase]:
        raise NotImplementedError

    def apply(self, cur: Cursor, big: Source, batch: Sequence[Report]) -> tuple[int, int]:
        """一批补报一个事务，返回语句数（不含 BEGIN、COMMIT）与写入行数。"""
        raise NotImplementedError

    def upgrade(self, cur: Cursor, big: Source, plan: Upgrade) -> Step:
        raise NotImplementedError

    def compact(self, cur: Cursor, big: Source, texts: Texts) -> list[Step]:
        return []

    def write_plans(self, big: Source, batch: Sequence[Report]) -> list[tuple[str, str, tuple[Any, ...] | None]]:
        raise NotImplementedError

    def verify(self, conn: pymysql.Connection, group_id: int, unit: str) -> str:
        raise NotImplementedError


class PerScope(Layout):
    """存法 1：每个成员内联完整元信息，没有定义表；with_fingerprint 时另加指纹列，补报只读指纹比较。"""

    def __init__(self, with_fingerprint: bool) -> None:
        super().__init__()
        self.with_fingerprint: bool = with_fingerprint
        self.key = "1" if with_fingerprint else "1n"
        self.title = "per-scope copy + fingerprint" if with_fingerprint else "per-scope copy, no fingerprint"
        self.member = "l1_member" if with_fingerprint else "l1n_member"
        self.ref = "metric_id"
        self.volume_only = not with_fingerprint
        payload: list[str] = ["meta JSON NOT NULL", *([FINGERPRINT] if with_fingerprint else [])]
        self.ddl = {self.member: member_ddl(self.member, self.ref, payload)}
        self.columns = {self.member: member_columns(self.ref, ["meta", *(["fingerprint"] if with_fingerprint else [])])}
        if with_fingerprint:
            self.sql = {
                "A": [L1_A],
                "B": [L1_B],
                "C": [L1_C],
                "C.any": [L1_ANY],
                "D": [L1_D, "BEGIN", upsert_doc(self.member, self.columns[self.member], L1_SETS), "COMMIT"],
                "E": [L1_E, "BEGIN", upsert_doc(self.member, self.columns[self.member], L1_SETS), "COMMIT"],
            }

    def emit(self, loaders: dict[str, Loader], src: Source, texts: Texts, flags: bytearray, usage: Usage) -> None:
        tails: list[tuple[str, str]] = []
        for i in range(src.metrics):
            head: str = f"\t{src.metric_id(i)}\t{LAST_SEEN}\t"
            if self.with_fingerprint:
                tails.append(
                    (
                        f"{head}{texts.default[i]}\t{texts.default_fp[i]}",
                        f"{head}{texts.variant[i]}\t{texts.variant_fp[i]}",
                    )
                )
            else:
                tails.append((head + texts.default[i], head + texts.variant[i]))
        emit_members(loaders[self.member], src, tails, flags)

    def read_cases(self, probes: Probes) -> list[ReadCase]:
        g: int = probes.scopes[0][0]
        return [
            statement_case("A", POINT, L1_A, [p[:3] for p in probes.points]),
            statement_case("B", SCOPE, L1_B, probes.scopes),
            statement_case("C", VOTE, L1_C, [(g,)]),
            statement_case("C.any", GROUP, L1_ANY, [(g,)]),
        ]

    def apply(self, cur: Cursor, big: Source, batch: Sequence[Report]) -> tuple[int, int]:
        g: int = big.group_id
        keys: str = ", ".join(f"({g}, {r.scope_id}, {r.metric_id})" for r in batch)
        current: dict[tuple[int, int], tuple[int, str]] = {
            (s, m): (mid, fp) for mid, s, m, fp in fetch(cur, L1_D.format(keys=keys))
        }
        rows: list[tuple[int | str | None, ...]] = []
        for r in batch:
            mid, fp = current[(r.scope_id, r.metric_id)]
            if fp != r.fp:
                rows.append((mid, g, r.scope_id, r.metric_id, NOW, r.text, r.fp))
        cur.execute("BEGIN")
        statements: int = 1 + upsert(cur, self.member, self.columns[self.member], rows, L1_SETS)
        cur.execute("COMMIT")
        return statements, len(rows)

    def upgrade(self, cur: Cursor, big: Source, plan: Upgrade) -> Step:
        g: int = big.group_id
        step: Step = Step("1 apply: rewrite every member")
        last: tuple[int, int] = (0, 0)
        while True:
            start: float = time.perf_counter()
            rows: tuple[Any, ...] = keyset(cur, L1_E, g, last)
            if not rows:
                break
            changed: list[tuple[int | str | None, ...]] = []
            for s, m, mid, fp in rows:
                k: int = big.index(s, m)
                if fp != plan.fps[k]:
                    changed.append((mid, g, s, m, NOW, plan.texts[k], plan.fps[k]))
            cur.execute("BEGIN")
            statements: int = 1 + upsert(cur, self.member, self.columns[self.member], changed, L1_SETS)
            cur.execute("COMMIT")
            step.add(time.perf_counter() - start, len(changed), statements)
            last = (rows[-1][0], rows[-1][1])
        return step

    def write_plans(self, big: Source, batch: Sequence[Report]) -> list[tuple[str, str, tuple[Any, ...] | None]]:
        keys: str = ", ".join(f"({big.group_id}, {r.scope_id}, {r.metric_id})" for r in batch)
        return [("D.read", L1_D.format(keys=keys), None), ("E.keyset", L1_E, (big.group_id, 0, 0, 0))]

    def verify(self, conn: pymysql.Connection, group_id: int, unit: str) -> str:
        total, matched = execute(
            conn,
            "SELECT COUNT(*), SUM(JSON_UNQUOTE(JSON_EXTRACT(meta, '$.unit')) = %s) FROM l1_member WHERE group_id = %s",
            (unit, group_id),
        )[0]
        return f"members {total:,}, effective unit={unit} {int(matched):,}"


def upsert_doc(table: str, columns: Sequence[str], sets: str) -> str:
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES {{rows}} AS new ON DUPLICATE KEY UPDATE {sets}"


L1_A: str = "SELECT meta FROM l1_member WHERE group_id = %s AND report_scope_id = %s AND metric_id = %s"
L1_B: str = "SELECT metric_id, meta FROM l1_member WHERE group_id = %s AND report_scope_id = %s"
L1_C: str = (
    "SELECT metric_id, meta FROM (SELECT metric_id, ANY_VALUE(meta) AS meta, "
    "ROW_NUMBER() OVER (PARTITION BY metric_id ORDER BY COUNT(*) DESC, fingerprint) AS rn "
    "FROM l1_member WHERE group_id = %s GROUP BY metric_id, fingerprint) t WHERE rn = 1"
)
L1_ANY: str = (
    "SELECT m.metric_id, m.meta FROM l1_member m "
    "JOIN (SELECT MIN(id) AS id FROM l1_member WHERE group_id = %s GROUP BY metric_id) f ON f.id = m.id"
)
L1_D: str = (
    "SELECT id, report_scope_id, metric_id, fingerprint FROM l1_member "
    "WHERE (group_id, report_scope_id, metric_id) IN ({keys})"
)
L1_E: str = keyset_sql("m.report_scope_id, m.metric_id, m.id, m.fingerprint", "l1_member m", "metric_id")
L1_SETS: str = "meta = new.meta, fingerprint = new.fingerprint"


class Definitions(Layout):
    """存法 2、4 共用：定义表存默认元信息；整理任务沿成员唯一键统计例外，成员数最多的例外取值晋升为定义，
    再分段把与新定义同指纹的例外置空。empty 为沿用定义的标记（存法 2 为 NULL，存法 4 为 0）。"""

    compacts = True
    empty: Any = None
    scan_sql: str = ""
    null_scan_sql: str = ""
    null_sql: str = ""
    definition_read: str = ""

    def read_definitions(self, cur: Cursor, group_id: int, batch: Sequence[Report]) -> dict[str, tuple[int, str]]:
        names: list[str] = sorted({r.field_name for r in batch})
        keys: str = ", ".join(f"({group_id}, {lit(n)})" for n in names)
        return {name: (did, fp) for did, name, fp in fetch(cur, self.definition_read.format(keys=keys))}

    def winner_texts(
        self, cur: Cursor, group_id: int, refs: Sequence[int], winners: dict[int, Any], sample: dict[tuple[int, Any], int]
    ) -> dict[int, tuple[str, str]]:
        """取晋升取值的文本与指纹，一条语句。"""
        raise NotImplementedError

    def compact(self, cur: Cursor, big: Source, texts: Texts) -> list[Step]:
        g: int = big.group_id
        scan: Step = Step(f"{self.key} compact: count exceptions")
        counts: dict[int, dict[Any, int]] = {}
        sample: dict[tuple[int, Any], int] = {}
        last: tuple[int, int] = (0, 0)
        while True:
            start: float = time.perf_counter()
            rows: tuple[Any, ...] = keyset(cur, self.scan_sql, g, last)
            if not rows:
                break
            for s, ref, value in rows:
                bucket: dict[Any, int] = counts.setdefault(ref, {})
                bucket[value] = bucket.get(value, 0) + 1
                if value != self.empty:
                    sample.setdefault((ref, value), s)
            scan.add(time.perf_counter() - start, 0, 1)
            last = (rows[-1][0], rows[-1][1])
        winners: dict[int, Any] = pick_winners(counts, self.empty)

        promote: Step = Step(f"{self.key} compact: promote definitions")
        refs: list[int] = sorted(winners)
        for k in range(0, len(refs), WRITE_CHUNK):
            start = time.perf_counter()
            chunk: list[int] = refs[k : k + WRITE_CHUNK]
            promoted: dict[int, tuple[str, str]] = self.winner_texts(cur, g, chunk, winners, sample)
            definitions: list[tuple[int | str | None, ...]] = []
            for ref in chunk:
                i: int = ref - big.metric_base - 1
                text, fp = promoted[ref]
                definitions.append((ref, g, texts.names[i], texts.originals[i], texts.kinds[i], text, fp, NOW))
            cur.execute("BEGIN")
            statements: int = 1 + upsert(cur, self.definition, DEFINITION_COLUMNS, definitions, DEFINITION_SETS)
            cur.execute("COMMIT")
            promote.add(time.perf_counter() - start, len(definitions), statements)

        clear: Step = Step(f"{self.key} compact: clear exceptions")
        last = (0, 0)
        while True:
            start = time.perf_counter()
            rows = keyset(cur, self.null_scan_sql, g, last)
            if not rows:
                break
            ids: list[int] = [mid for _, ref, mid, value in rows if value != self.empty and winners.get(ref) == value]
            statements = 1
            if ids:
                cur.execute("BEGIN")
                cur.execute(self.null_sql.format(ids=ints(ids)))
                cur.execute("COMMIT")
                statements += 1
            clear.add(time.perf_counter() - start, len(ids), statements)
            last = (rows[-1][0], rows[-1][1])
        return [scan, promote, clear]


DEFINITION_SETS: str = "meta = new.meta, fingerprint = new.fingerprint, seen_at = new.seen_at"


class Exceptions(Definitions):
    """存法 2（现方案）：成员 meta 只在上报取值与定义指纹不同时写入完整 JSON，其余为 NULL。"""

    def __init__(self) -> None:
        super().__init__()
        self.key = "2"
        self.title = "definition + inline exception"
        self.member = "l2_member"
        self.ref = "meta_id"
        self.definition = "l2_def"
        self.empty = None
        self.scan_sql = L2_SCAN
        self.null_scan_sql = L2_NULL_SCAN
        self.null_sql = L2_NULL
        self.definition_read = L2_D_DEFS
        self.ddl = {
            self.definition: definition_ddl(self.definition),
            self.member: member_ddl(self.member, self.ref, ["meta JSON NULL"]),
        }
        self.columns = {self.definition: DEFINITION_COLUMNS, self.member: member_columns(self.ref, ["meta"])}
        member_upsert: str = upsert_doc(self.member, self.columns[self.member], L2_SETS)
        self.sql = {
            "A": [L2_A_DEF, L2_A_MEMBER, "client: COALESCE(member.meta, definition.meta)"],
            "A.join": [L2_A_JOIN],
            "B": [L2_B],
            "B.in": [L2_B_MEMBERS, L2_B_DEFS, "client: COALESCE(member.meta, definition.meta)"],
            "C": [L2_C],
            "D": [L2_D_DEFS, L2_D_MEMBERS, "BEGIN", member_upsert, "COMMIT"],
            "E.1": [L2_E, L2_E_DEFS, "BEGIN", member_upsert, "COMMIT"],
            "E.2": [
                L2_SCAN,
                L2_WINNERS,
                "BEGIN",
                upsert_doc(self.definition, DEFINITION_COLUMNS, DEFINITION_SETS),
                "COMMIT",
                L2_NULL_SCAN,
                "BEGIN",
                L2_NULL,
                "COMMIT",
            ],
        }

    def emit(self, loaders: dict[str, Loader], src: Source, texts: Texts, flags: bytearray, usage: Usage) -> None:
        emit_definitions(loaders[self.definition], src, texts)
        tails: list[tuple[str, str]] = []
        for i in range(src.metrics):
            head: str = f"\t{src.metric_id(i)}\t{LAST_SEEN}\t"
            tails.append((head + "\\N", head + texts.variant[i]))
        emit_members(loaders[self.member], src, tails, flags)

    def read_a(self, cur: Cursor, params: tuple[Any, ...]) -> tuple[int, int]:
        g, s, _, name = params
        definition: tuple[Any, ...] = fetch(cur, L2_A_DEF, (g, name))[0]
        member: tuple[Any, ...] = fetch(cur, L2_A_MEMBER, (g, s, int(definition[0])))
        meta: str | None = member[0][0] if member and member[0][0] is not None else definition[1]
        return (0 if meta is None else 1), 2

    def read_b_in(self, cur: Cursor, params: tuple[Any, ...]) -> tuple[int, int]:
        members: tuple[Any, ...] = fetch(cur, L2_B_MEMBERS, params)
        defaults: dict[str, str] = dict(fetch(cur, L2_B_DEFS.format(ids=", ".join(r[0] for r in members))))
        effective: list[str] = [meta if meta is not None else defaults[ref] for ref, meta in members]
        return len(effective), 2

    def read_cases(self, probes: Probes) -> list[ReadCase]:
        g: int = probes.scopes[0][0]
        return [
            steps_case("A", POINT, self.read_a, probes.points, L2_A_DEF, (g, probes.points[0][3])),
            statement_case("A.join", POINT, L2_A_JOIN, [(p[1], p[0], p[3]) for p in probes.points]),
            statement_case("B", SCOPE, L2_B, probes.scopes),
            steps_case("B.in", SCOPE, self.read_b_in, probes.scopes, L2_B_MEMBERS, probes.scopes[0]),
            statement_case("C", GROUP, L2_C, [(g,)]),
        ]

    def apply(self, cur: Cursor, big: Source, batch: Sequence[Report]) -> tuple[int, int]:
        g: int = big.group_id
        definitions: dict[str, tuple[int, str]] = self.read_definitions(cur, g, batch)
        keys: str = ", ".join(f"({g}, {r.scope_id}, {definitions[r.field_name][0]})" for r in batch)
        current: dict[tuple[int, int], tuple[int, str | None]] = {
            (s, ref): (mid, None if meta is None else md5_hex(meta))
            for mid, s, ref, meta in fetch(cur, L2_D_MEMBERS.format(keys=keys))
        }
        rows: list[tuple[int | str | None, ...]] = []
        for r in batch:
            ref, definition_fp = definitions[r.field_name]
            want: str | None = None if r.fp == definition_fp else r.fp
            mid, have = current[(r.scope_id, ref)]
            if want != have:
                rows.append((mid, g, r.scope_id, ref, NOW, None if want is None else r.text))
        cur.execute("BEGIN")
        statements: int = 2 + upsert(cur, self.member, self.columns[self.member], rows, L2_SETS)
        cur.execute("COMMIT")
        return statements, len(rows)

    def upgrade(self, cur: Cursor, big: Source, plan: Upgrade) -> Step:
        g: int = big.group_id
        step: Step = Step("2 apply: write exceptions")
        last: tuple[int, int] = (0, 0)
        while True:
            start: float = time.perf_counter()
            rows: tuple[Any, ...] = keyset(cur, L2_E, g, last)
            if not rows:
                break
            refs: list[int] = sorted({row[1] for row in rows})
            definition_fp: dict[int, str] = dict(fetch(cur, L2_E_DEFS.format(ids=ints(refs))))
            changed: list[tuple[int | str | None, ...]] = []
            for s, ref, mid, meta in rows:
                k: int = big.index(s, ref)
                want: str | None = None if plan.fps[k] == definition_fp[ref] else plan.fps[k]
                have: str | None = None if meta is None else md5_hex(meta)
                if want != have:
                    changed.append((mid, g, s, ref, NOW, None if want is None else plan.texts[k]))
            cur.execute("BEGIN")
            statements: int = 2 + upsert(cur, self.member, self.columns[self.member], changed, L2_SETS)
            cur.execute("COMMIT")
            step.add(time.perf_counter() - start, len(changed), statements)
            last = (rows[-1][0], rows[-1][1])
        return step

    def winner_texts(
        self, cur: Cursor, group_id: int, refs: Sequence[int], winners: dict[int, Any], sample: dict[tuple[int, Any], int]
    ) -> dict[int, tuple[str, str]]:
        keys: str = ", ".join(f"({group_id}, {sample[(ref, winners[ref])]}, {ref})" for ref in refs)
        return {ref: (meta, winners[ref]) for ref, meta in fetch(cur, L2_WINNERS.format(keys=keys))}

    def write_plans(self, big: Source, batch: Sequence[Report]) -> list[tuple[str, str, tuple[Any, ...] | None]]:
        g: int = big.group_id
        names: list[str] = sorted({r.field_name for r in batch})
        keys: str = ", ".join(f"({g}, {r.scope_id}, {r.metric_id})" for r in batch)
        name_keys: str = ", ".join(f"({g}, {lit(n)})" for n in names)
        return [
            ("D.definitions", L2_D_DEFS.format(keys=name_keys), None),
            ("D.members", L2_D_MEMBERS.format(keys=keys), None),
            ("E.keyset", L2_E, (g, 0, 0, 0)),
            ("E.compact_scan", L2_SCAN, (g, 0, 0, 0)),
        ]

    def verify(self, conn: pymysql.Connection, group_id: int, unit: str) -> str:
        total, matched, exceptions = execute(
            conn,
            "SELECT COUNT(*), SUM(JSON_UNQUOTE(JSON_EXTRACT(COALESCE(m.meta, d.meta), '$.unit')) = %s), "
            "SUM(m.meta IS NOT NULL) FROM l2_member m JOIN l2_def d ON d.id = m.meta_id WHERE m.group_id = %s",
            (unit, group_id),
        )[0]
        return f"members {total:,}, effective unit={unit} {int(matched):,}, exceptions {int(exceptions):,}"


L2_A_DEF: str = "SELECT id, meta FROM l2_def WHERE group_id = %s AND field_name = %s"
L2_A_MEMBER: str = "SELECT meta FROM l2_member WHERE group_id = %s AND report_scope_id = %s AND meta_id = %s"
L2_A_JOIN: str = (
    "SELECT COALESCE(m.meta, d.meta) FROM l2_def d JOIN l2_member m ON m.group_id = d.group_id "
    "AND m.report_scope_id = %s AND m.meta_id = d.id WHERE d.group_id = %s AND d.field_name = %s"
)
L2_B: str = (
    "SELECT m.meta_id, COALESCE(m.meta, d.meta) FROM l2_member m JOIN l2_def d ON d.id = m.meta_id "
    "WHERE m.group_id = %s AND m.report_scope_id = %s"
)
L2_B_MEMBERS: str = "SELECT meta_id, meta FROM l2_member WHERE group_id = %s AND report_scope_id = %s"
L2_B_DEFS: str = "SELECT id, meta FROM l2_def WHERE id IN ({ids})"
L2_C: str = "SELECT id, field_name, meta FROM l2_def WHERE group_id = %s"
L2_D_DEFS: str = "SELECT id, field_name, fingerprint FROM l2_def WHERE (group_id, field_name) IN ({keys})"
L2_D_MEMBERS: str = (
    "SELECT id, report_scope_id, meta_id, meta FROM l2_member WHERE (group_id, report_scope_id, meta_id) IN ({keys})"
)
L2_E: str = keyset_sql("m.report_scope_id, m.meta_id, m.id, m.meta", "l2_member m", "meta_id")
L2_E_DEFS: str = "SELECT id, fingerprint FROM l2_def WHERE id IN ({ids})"
L2_SCAN: str = keyset_sql("m.report_scope_id, m.meta_id, MD5(m.meta)", "l2_member m", "meta_id")
L2_WINNERS: str = "SELECT meta_id, meta FROM l2_member WHERE (group_id, report_scope_id, meta_id) IN ({keys})"
L2_NULL_SCAN: str = keyset_sql("m.report_scope_id, m.meta_id, m.id, MD5(m.meta)", "l2_member m", "meta_id")
L2_NULL: str = "UPDATE l2_member SET meta = NULL WHERE id IN ({ids})"
L2_SETS: str = "meta = new.meta"


class Values(Layout):
    """存法 3：值表按 (group_id, 指纹) 去重，每个成员引用一个值；没有定义，默认元信息只能按成员投票。"""

    def __init__(self) -> None:
        super().__init__()
        self.key = "3"
        self.title = "content-addressed value table"
        self.member = "l3_member"
        self.ref = "metric_id"
        self.value = "l3_value"
        self.next_value: int = 0
        self.ddl = {
            self.value: value_ddl(self.value),
            self.member: member_ddl(self.member, self.ref, ["meta_value_id BIGINT NOT NULL"]),
        }
        self.columns = {
            self.value: ["id", *VALUE_COLUMNS],
            self.member: member_columns(self.ref, ["meta_value_id"]),
        }
        member_upsert: str = upsert_doc(self.member, self.columns[self.member], L3_SETS)
        value_steps: list[str] = [
            VALUE_LOOKUP.format(table=self.value),
            upsert_doc(self.value, VALUE_COLUMNS, "id = id") + "  -- only missing fingerprints",
            VALUE_LOOKUP.format(table=self.value) + "  -- re-read inserted ids",
        ]
        self.sql = {
            "A": [L3_A_MEMBER, L3_A_VALUE],
            "A.join": [L3_A_JOIN],
            "B": [L3_B],
            "B.in": [L3_B_MEMBERS, L3_B_VALUES],
            "C": [L3_C],
            "C.any": [L3_ANY],
            "D": [L3_D, "BEGIN", *value_steps, member_upsert, "COMMIT"],
            "E": [L3_E, "BEGIN", *value_steps, member_upsert, "COMMIT"],
        }

    def create(self, conn: pymysql.Connection) -> None:
        super().create(conn)
        self.next_value = 0

    def emit(self, loaders: dict[str, Loader], src: Source, texts: Texts, flags: bytearray, usage: Usage) -> None:
        values: Loader = loaders[self.value]
        tails: list[tuple[str, str]] = []
        for i in range(src.metrics):
            ids: list[int] = [0, 0]
            for slot, (used, text, fp) in enumerate(
                (
                    (usage.default[i], texts.default[i], texts.default_fp[i]),
                    (usage.variant[i], texts.variant[i], texts.variant_fp[i]),
                )
            ):
                if used:
                    self.next_value += 1
                    ids[slot] = self.next_value
                    values.add(f"{self.next_value}\t{src.group_id}\t{fp}\t{text}")
            head: str = f"\t{src.metric_id(i)}\t{LAST_SEEN}\t"
            tails.append((f"{head}{ids[0]}", f"{head}{ids[1]}"))
        emit_members(loaders[self.member], src, tails, flags)

    def read_a(self, cur: Cursor, params: tuple[Any, ...]) -> tuple[int, int]:
        member: tuple[Any, ...] = fetch(cur, L3_A_MEMBER, params[:3])[0]
        value: tuple[Any, ...] = fetch(cur, L3_A_VALUE, (int(member[0]),))
        return len(value), 2

    def read_b_in(self, cur: Cursor, params: tuple[Any, ...]) -> tuple[int, int]:
        members: tuple[Any, ...] = fetch(cur, L3_B_MEMBERS, params)
        refs: list[str] = sorted({r[1] for r in members})
        values: dict[str, str] = dict(fetch(cur, L3_B_VALUES.format(ids=", ".join(refs))))
        effective: list[str] = [values[ref] for _, ref in members]
        return len(effective), 2

    def read_cases(self, probes: Probes) -> list[ReadCase]:
        g: int = probes.scopes[0][0]
        return [
            steps_case("A", POINT, self.read_a, probes.points, L3_A_MEMBER, probes.points[0][:3]),
            statement_case("A.join", POINT, L3_A_JOIN, [p[:3] for p in probes.points]),
            statement_case("B", SCOPE, L3_B, probes.scopes),
            steps_case("B.in", SCOPE, self.read_b_in, probes.scopes, L3_B_MEMBERS, probes.scopes[0]),
            statement_case("C", VOTE, L3_C, [(g,)]),
            statement_case("C.any", GROUP, L3_ANY, [(g,)]),
        ]

    def apply(self, cur: Cursor, big: Source, batch: Sequence[Report]) -> tuple[int, int]:
        g: int = big.group_id
        keys: str = ", ".join(f"({g}, {r.scope_id}, {r.metric_id})" for r in batch)
        current: dict[tuple[int, int], tuple[int, str]] = {
            (s, m): (mid, fp) for mid, s, m, fp in fetch(cur, L3_D.format(keys=keys))
        }
        changed: list[tuple[int, Report]] = []
        for r in batch:
            mid, fp = current[(r.scope_id, r.metric_id)]
            if fp != r.fp:
                changed.append((mid, r))
        cur.execute("BEGIN")
        ids, statements, inserted = ensure_values(cur, self.value, g, {r.fp: r.text for _, r in changed})
        rows: list[tuple[int | str | None, ...]] = [
            (mid, g, r.scope_id, r.metric_id, NOW, ids[r.fp]) for mid, r in changed
        ]
        statements += upsert(cur, self.member, self.columns[self.member], rows, L3_SETS)
        cur.execute("COMMIT")
        return 1 + statements, len(rows) + inserted

    def upgrade(self, cur: Cursor, big: Source, plan: Upgrade) -> Step:
        g: int = big.group_id
        step: Step = Step("3 apply: insert values, repoint members")
        last: tuple[int, int] = (0, 0)
        while True:
            start: float = time.perf_counter()
            rows: tuple[Any, ...] = keyset(cur, L3_E, g, last)
            if not rows:
                break
            changed: list[tuple[int, int, int, int]] = []
            for s, m, mid, fp in rows:
                k: int = big.index(s, m)
                if fp != plan.fps[k]:
                    changed.append((mid, s, m, k))
            cur.execute("BEGIN")
            ids, statements, inserted = ensure_values(
                cur, self.value, g, {plan.fps[k]: plan.texts[k] for *_, k in changed}
            )
            out: list[tuple[int | str | None, ...]] = [
                (mid, g, s, m, NOW, ids[plan.fps[k]]) for mid, s, m, k in changed
            ]
            statements += upsert(cur, self.member, self.columns[self.member], out, L3_SETS)
            cur.execute("COMMIT")
            step.add(time.perf_counter() - start, len(out) + inserted, 1 + statements)
            last = (rows[-1][0], rows[-1][1])
        return step

    def write_plans(self, big: Source, batch: Sequence[Report]) -> list[tuple[str, str, tuple[Any, ...] | None]]:
        g: int = big.group_id
        keys: str = ", ".join(f"({g}, {r.scope_id}, {r.metric_id})" for r in batch)
        fps: str = quoted(sorted({r.fp for r in batch}))
        return [
            ("D.members", L3_D.format(keys=keys), None),
            ("D.values", VALUE_LOOKUP.format(table=self.value).format(g=g, fps=fps), None),
            ("E.keyset", L3_E, (g, 0, 0, 0)),
        ]

    def verify(self, conn: pymysql.Connection, group_id: int, unit: str) -> str:
        total, matched, referenced = execute(
            conn,
            "SELECT COUNT(*), SUM(JSON_UNQUOTE(JSON_EXTRACT(v.meta, '$.unit')) = %s), COUNT(DISTINCT m.meta_value_id) "
            "FROM l3_member m JOIN l3_value v ON v.id = m.meta_value_id WHERE m.group_id = %s",
            (unit, group_id),
        )[0]
        values: int = execute(conn, "SELECT COUNT(*) FROM l3_value WHERE group_id = %s", (group_id,))[0][0]
        return (
            f"members {total:,}, effective unit={unit} {int(matched):,}, values {values:,} "
            f"(referenced {referenced:,}, unreferenced {values - referenced:,})"
        )


VALUE_LOOKUP: str = "SELECT fingerprint, id FROM {table} WHERE group_id = {{g}} AND fingerprint IN ({{fps}})"
L3_A_MEMBER: str = "SELECT meta_value_id FROM l3_member WHERE group_id = %s AND report_scope_id = %s AND metric_id = %s"
L3_A_VALUE: str = "SELECT meta FROM l3_value WHERE id = %s"
L3_A_JOIN: str = (
    "SELECT v.meta FROM l3_member m JOIN l3_value v ON v.id = m.meta_value_id "
    "WHERE m.group_id = %s AND m.report_scope_id = %s AND m.metric_id = %s"
)
L3_B: str = (
    "SELECT m.metric_id, v.meta FROM l3_member m JOIN l3_value v ON v.id = m.meta_value_id "
    "WHERE m.group_id = %s AND m.report_scope_id = %s"
)
L3_B_MEMBERS: str = "SELECT metric_id, meta_value_id FROM l3_member WHERE group_id = %s AND report_scope_id = %s"
L3_B_VALUES: str = "SELECT id, meta FROM l3_value WHERE id IN ({ids})"
L3_C: str = (
    "SELECT t.metric_id, v.meta FROM (SELECT metric_id, meta_value_id, "
    "ROW_NUMBER() OVER (PARTITION BY metric_id ORDER BY COUNT(*) DESC, meta_value_id) AS rn "
    "FROM l3_member WHERE group_id = %s GROUP BY metric_id, meta_value_id) t "
    "JOIN l3_value v ON v.id = t.meta_value_id WHERE t.rn = 1"
)
L3_ANY: str = (
    "SELECT m.metric_id, v.meta FROM l3_member m "
    "JOIN (SELECT MIN(id) AS id FROM l3_member WHERE group_id = %s GROUP BY metric_id) f ON f.id = m.id "
    "JOIN l3_value v ON v.id = m.meta_value_id"
)
L3_D: str = (
    "SELECT m.id, m.report_scope_id, m.metric_id, v.fingerprint FROM l3_member m "
    "JOIN l3_value v ON v.id = m.meta_value_id WHERE (m.group_id, m.report_scope_id, m.metric_id) IN ({keys})"
)
L3_E: str = keyset_sql(
    "m.report_scope_id, m.metric_id, m.id, v.fingerprint",
    "l3_member m JOIN l3_value v ON v.id = m.meta_value_id",
    "metric_id",
)
L3_SETS: str = "meta_value_id = new.meta_value_id"


class ExceptionRefs(Definitions):
    """存法 4（对照）：定义同存法 2；例外取值按 (group_id, 指纹) 去重进值表，成员只存定长 BIGINT 引用，
    0 表示沿用定义，状态切换都是原地更新，不改变行长。"""

    def __init__(self) -> None:
        super().__init__()
        self.key = "4"
        self.title = "definition + exception value ref"
        self.member = "l4_member"
        self.ref = "meta_id"
        self.definition = "l4_def"
        self.value = "l4_value"
        self.empty = 0
        self.next_value: int = 0
        self.scan_sql = L4_SCAN
        self.null_scan_sql = L4_NULL_SCAN
        self.null_sql = L4_NULL
        self.definition_read = L4_D_DEFS
        self.ddl = {
            self.definition: definition_ddl(self.definition),
            self.value: value_ddl(self.value),
            self.member: member_ddl(self.member, self.ref, ["exception_value_id BIGINT NOT NULL DEFAULT 0"]),
        }
        self.columns = {
            self.definition: DEFINITION_COLUMNS,
            self.value: ["id", *VALUE_COLUMNS],
            self.member: member_columns(self.ref, ["exception_value_id"]),
        }
        member_upsert: str = upsert_doc(self.member, self.columns[self.member], L4_SETS)
        value_steps: list[str] = [
            VALUE_LOOKUP.format(table=self.value),
            upsert_doc(self.value, VALUE_COLUMNS, "id = id") + "  -- only missing fingerprints",
            VALUE_LOOKUP.format(table=self.value) + "  -- re-read inserted ids",
        ]
        self.sql = {
            "A": [L4_A_DEF, L4_A_MEMBER, L4_A_VALUE + "  -- only when exception_value_id <> 0"],
            "A.join": [L4_A_JOIN],
            "B": [L4_B],
            "B.in": [L4_B_MEMBERS, L4_B_DEFS, L4_B_VALUES + "  -- distinct non-zero refs"],
            "C": [L4_C],
            "D": [L4_D_DEFS, L4_D_MEMBERS, "BEGIN", *value_steps, member_upsert, "COMMIT"],
            "E.1": [L4_E, L4_E_DEFS, "BEGIN", *value_steps, member_upsert, "COMMIT"],
            "E.2": [
                L4_SCAN,
                L4_WINNERS,
                "BEGIN",
                upsert_doc(self.definition, DEFINITION_COLUMNS, DEFINITION_SETS),
                "COMMIT",
                L4_NULL_SCAN,
                "BEGIN",
                L4_NULL,
                "COMMIT",
            ],
        }

    def create(self, conn: pymysql.Connection) -> None:
        super().create(conn)
        self.next_value = 0

    def emit(self, loaders: dict[str, Loader], src: Source, texts: Texts, flags: bytearray, usage: Usage) -> None:
        emit_definitions(loaders[self.definition], src, texts)
        values: Loader = loaders[self.value]
        tails: list[tuple[str, str]] = []
        for i in range(src.metrics):
            variant_id: int = 0
            if usage.variant[i]:
                self.next_value += 1
                variant_id = self.next_value
                values.add(f"{variant_id}\t{src.group_id}\t{texts.variant_fp[i]}\t{texts.variant[i]}")
            head: str = f"\t{src.metric_id(i)}\t{LAST_SEEN}\t"
            tails.append((f"{head}0", f"{head}{variant_id}"))
        emit_members(loaders[self.member], src, tails, flags)

    def read_a(self, cur: Cursor, params: tuple[Any, ...]) -> tuple[int, int]:
        g, s, _, name = params
        definition: tuple[Any, ...] = fetch(cur, L4_A_DEF, (g, name))[0]
        ref: str = fetch(cur, L4_A_MEMBER, (g, s, int(definition[0])))[0][0]
        if ref == "0":
            return (0 if definition[1] is None else 1), 2
        return len(fetch(cur, L4_A_VALUE, (int(ref),))), 3

    def read_b_in(self, cur: Cursor, params: tuple[Any, ...]) -> tuple[int, int]:
        members: tuple[Any, ...] = fetch(cur, L4_B_MEMBERS, params)
        defaults: dict[str, str] = dict(fetch(cur, L4_B_DEFS.format(ids=", ".join(r[0] for r in members))))
        refs: list[str] = sorted({r[1] for r in members if r[1] != "0"})
        values: dict[str, str] = dict(fetch(cur, L4_B_VALUES.format(ids=", ".join(refs)))) if refs else {}
        effective: list[str] = [defaults[ref] if value == "0" else values[value] for ref, value in members]
        return len(effective), 3 if refs else 2

    def read_cases(self, probes: Probes) -> list[ReadCase]:
        g: int = probes.scopes[0][0]
        return [
            steps_case("A", POINT, self.read_a, probes.points, L4_A_DEF, (g, probes.points[0][3])),
            statement_case("A.join", POINT, L4_A_JOIN, [(p[1], p[0], p[3]) for p in probes.points]),
            statement_case("B", SCOPE, L4_B, probes.scopes),
            steps_case("B.in", SCOPE, self.read_b_in, probes.scopes, L4_B_MEMBERS, probes.scopes[0]),
            statement_case("C", GROUP, L4_C, [(g,)]),
        ]

    def apply(self, cur: Cursor, big: Source, batch: Sequence[Report]) -> tuple[int, int]:
        g: int = big.group_id
        definitions: dict[str, tuple[int, str]] = self.read_definitions(cur, g, batch)
        keys: str = ", ".join(f"({g}, {r.scope_id}, {definitions[r.field_name][0]})" for r in batch)
        current: dict[tuple[int, int], tuple[int, str | None]] = {
            (s, ref): (mid, fp) for mid, s, ref, fp in fetch(cur, L4_D_MEMBERS.format(keys=keys))
        }
        changes: list[tuple[int, int, int, Report | None]] = []
        for r in batch:
            ref, definition_fp = definitions[r.field_name]
            want: str | None = None if r.fp == definition_fp else r.fp
            mid, have = current[(r.scope_id, ref)]
            if want != have:
                changes.append((mid, r.scope_id, ref, None if want is None else r))
        cur.execute("BEGIN")
        wanted: dict[str, str] = {r.fp: r.text for *_, r in changes if r is not None}
        ids: dict[str, int] = {}
        statements: int = 0
        inserted: int = 0
        if wanted:
            ids, statements, inserted = ensure_values(cur, self.value, g, wanted)
        rows: list[tuple[int | str | None, ...]] = [
            (mid, g, s, ref, NOW, 0 if r is None else ids[r.fp]) for mid, s, ref, r in changes
        ]
        statements += upsert(cur, self.member, self.columns[self.member], rows, L4_SETS)
        cur.execute("COMMIT")
        return 2 + statements, len(rows) + inserted

    def upgrade(self, cur: Cursor, big: Source, plan: Upgrade) -> Step:
        g: int = big.group_id
        step: Step = Step("4 apply: insert values, set exception refs")
        last: tuple[int, int] = (0, 0)
        while True:
            start: float = time.perf_counter()
            rows: tuple[Any, ...] = keyset(cur, L4_E, g, last)
            if not rows:
                break
            refs: list[int] = sorted({row[1] for row in rows})
            definition_fp: dict[int, str] = dict(fetch(cur, L4_E_DEFS.format(ids=ints(refs))))
            changes: list[tuple[int, int, int, int]] = []
            for s, ref, mid, have in rows:
                k: int = big.index(s, ref)
                want: str | None = None if plan.fps[k] == definition_fp[ref] else plan.fps[k]
                if want != have:
                    changes.append((mid, s, ref, -1 if want is None else k))
            cur.execute("BEGIN")
            wanted: dict[str, str] = {plan.fps[k]: plan.texts[k] for *_, k in changes if k >= 0}
            ids: dict[str, int] = {}
            statements: int = 0
            inserted: int = 0
            if wanted:
                ids, statements, inserted = ensure_values(cur, self.value, g, wanted)
            out: list[tuple[int | str | None, ...]] = [
                (mid, g, s, ref, NOW, ids[plan.fps[k]] if k >= 0 else 0) for mid, s, ref, k in changes
            ]
            statements += upsert(cur, self.member, self.columns[self.member], out, L4_SETS)
            cur.execute("COMMIT")
            step.add(time.perf_counter() - start, len(out) + inserted, 2 + statements)
            last = (rows[-1][0], rows[-1][1])
        return step

    def winner_texts(
        self, cur: Cursor, group_id: int, refs: Sequence[int], winners: dict[int, Any], sample: dict[tuple[int, Any], int]
    ) -> dict[int, tuple[str, str]]:
        values: dict[int, tuple[str, str]] = {
            vid: (meta, fp) for vid, fp, meta in fetch(cur, L4_WINNERS.format(ids=ints([winners[r] for r in refs])))
        }
        return {ref: values[winners[ref]] for ref in refs}

    def write_plans(self, big: Source, batch: Sequence[Report]) -> list[tuple[str, str, tuple[Any, ...] | None]]:
        g: int = big.group_id
        names: list[str] = sorted({r.field_name for r in batch})
        keys: str = ", ".join(f"({g}, {r.scope_id}, {r.metric_id})" for r in batch)
        name_keys: str = ", ".join(f"({g}, {lit(n)})" for n in names)
        return [
            ("D.definitions", L4_D_DEFS.format(keys=name_keys), None),
            ("D.members", L4_D_MEMBERS.format(keys=keys), None),
            ("E.keyset", L4_E, (g, 0, 0, 0)),
            ("E.compact_scan", L4_SCAN, (g, 0, 0, 0)),
        ]

    def verify(self, conn: pymysql.Connection, group_id: int, unit: str) -> str:
        total, matched, exceptions, referenced = execute(
            conn,
            "SELECT COUNT(*), SUM(JSON_UNQUOTE(JSON_EXTRACT(COALESCE(v.meta, d.meta), '$.unit')) = %s), "
            "SUM(m.exception_value_id <> 0), COUNT(DISTINCT NULLIF(m.exception_value_id, 0)) "
            "FROM l4_member m JOIN l4_def d ON d.id = m.meta_id LEFT JOIN l4_value v ON v.id = m.exception_value_id "
            "WHERE m.group_id = %s",
            (unit, group_id),
        )[0]
        values: int = execute(conn, "SELECT COUNT(*) FROM l4_value WHERE group_id = %s", (group_id,))[0][0]
        return (
            f"members {total:,}, effective unit={unit} {int(matched):,}, exceptions {int(exceptions):,}, "
            f"values {values:,} (referenced {referenced:,}, unreferenced {values - referenced:,})"
        )


L4_A_DEF: str = "SELECT id, meta FROM l4_def WHERE group_id = %s AND field_name = %s"
L4_A_MEMBER: str = (
    "SELECT exception_value_id FROM l4_member WHERE group_id = %s AND report_scope_id = %s AND meta_id = %s"
)
L4_A_VALUE: str = "SELECT meta FROM l4_value WHERE id = %s"
L4_A_JOIN: str = (
    "SELECT COALESCE(v.meta, d.meta) FROM l4_def d JOIN l4_member m ON m.group_id = d.group_id "
    "AND m.report_scope_id = %s AND m.meta_id = d.id LEFT JOIN l4_value v ON v.id = m.exception_value_id "
    "WHERE d.group_id = %s AND d.field_name = %s"
)
L4_B: str = (
    "SELECT m.meta_id, COALESCE(v.meta, d.meta) FROM l4_member m JOIN l4_def d ON d.id = m.meta_id "
    "LEFT JOIN l4_value v ON v.id = m.exception_value_id WHERE m.group_id = %s AND m.report_scope_id = %s"
)
L4_B_MEMBERS: str = "SELECT meta_id, exception_value_id FROM l4_member WHERE group_id = %s AND report_scope_id = %s"
L4_B_DEFS: str = "SELECT id, meta FROM l4_def WHERE id IN ({ids})"
L4_B_VALUES: str = "SELECT id, meta FROM l4_value WHERE id IN ({ids})"
L4_C: str = "SELECT id, field_name, meta FROM l4_def WHERE group_id = %s"
L4_D_DEFS: str = "SELECT id, field_name, fingerprint FROM l4_def WHERE (group_id, field_name) IN ({keys})"
L4_D_MEMBERS: str = (
    "SELECT m.id, m.report_scope_id, m.meta_id, v.fingerprint FROM l4_member m "
    "LEFT JOIN l4_value v ON v.id = m.exception_value_id WHERE (m.group_id, m.report_scope_id, m.meta_id) IN ({keys})"
)
L4_E: str = keyset_sql(
    "m.report_scope_id, m.meta_id, m.id, v.fingerprint",
    "l4_member m LEFT JOIN l4_value v ON v.id = m.exception_value_id",
    "meta_id",
)
L4_E_DEFS: str = "SELECT id, fingerprint FROM l4_def WHERE id IN ({ids})"
L4_SCAN: str = keyset_sql("m.report_scope_id, m.meta_id, m.exception_value_id", "l4_member m", "meta_id")
L4_WINNERS: str = "SELECT id, fingerprint, meta FROM l4_value WHERE id IN ({ids})"
L4_NULL_SCAN: str = keyset_sql("m.report_scope_id, m.meta_id, m.id, m.exception_value_id", "l4_member m", "meta_id")
L4_NULL: str = "UPDATE l4_member SET exception_value_id = 0 WHERE id IN ({ids})"
L4_SETS: str = "exception_value_id = new.exception_value_id"

LAYOUTS: dict[str, Callable[[], Layout]] = {
    "1": partial(PerScope, True),
    "1n": partial(PerScope, False),
    "2": Exceptions,
    "3": Values,
    "4": ExceptionRefs,
}


# ---------------------------------------------------------------- 体积


@dataclass(frozen=True)
class Size:
    rows: int
    data: int
    index: int
    ibd: int

    @property
    def total(self) -> int:
        return self.data + self.index


def table_sizes(conn: pymysql.Connection, tables: Sequence[str]) -> dict[str, Size]:
    """ANALYZE 后取 information_schema 的数据与索引页，另列 .ibd 文件大小。"""
    execute(conn, "SET SESSION information_schema_stats_expiry = 0")
    datadir: str = execute(conn, "SELECT @@datadir")[0][0]
    sizes: dict[str, Size] = {}
    for table in tables:
        execute(conn, f"ANALYZE TABLE {table}")
        rows: int = execute(conn, f"SELECT COUNT(*) FROM {table}")[0][0]
        data, index = execute(
            conn,
            "SELECT data_length, index_length FROM information_schema.TABLES WHERE table_schema = %s AND table_name = %s",
            (DATABASE, table),
        )[0]
        ibd: int = os.path.getsize(os.path.join(datadir, DATABASE, f"{table}.ibd"))
        sizes[table] = Size(rows, int(data), int(index), ibd)
    return sizes


SIZE_HEADER: str = f"{'table':<16}{'rows':>12}{'data MiB':>11}{'index MiB':>11}{'d+i MiB':>10}{'ibd MiB':>10}{'d+i B/row':>11}"


def size_lines(sizes: dict[str, Size]) -> list[str]:
    return [
        f"{table:<16}{s.rows:>12,}{mib(s.data):>11}{mib(s.index):>11}{mib(s.total):>10}{mib(s.ibd):>10}"
        f"{s.total / max(1, s.rows):>11,.0f}"
        for table, s in sizes.items()
    ]


def warm(conn: pymysql.Connection, tables: Sequence[str]) -> None:
    """按每个索引做一次 COUNT(*)，把聚簇索引与二级索引读入缓冲池。"""
    for table in tables:
        keys: tuple[Any, ...] = execute(
            conn,
            "SELECT DISTINCT index_name FROM information_schema.STATISTICS WHERE table_schema = %s AND table_name = %s",
            (DATABASE, table),
        )
        for (key,) in keys:
            execute(conn, f"SELECT COUNT(*) FROM {table} FORCE INDEX (`{key}`)")


# ---------------------------------------------------------------- 一档不一致比例


@dataclass
class TierResult:
    ratio: float
    members: int
    definitions: int
    load_seconds: float
    sizes: dict[str, dict[str, Size]] = field(default_factory=dict)
    peak: dict[str, dict[str, Size]] = field(default_factory=dict)
    after: dict[str, dict[str, Size]] = field(default_factory=dict)
    reads: dict[str, dict[str, Timing]] = field(default_factory=dict)
    agreement: dict[str, dict[str, float]] = field(default_factory=dict)
    apply: dict[str, Timing] = field(default_factory=dict)
    upgrade: dict[str, list[Step]] = field(default_factory=dict)
    datadir_peak: int = 0


def agreement(conn: pymysql.Connection, case: ReadCase, big: Source, texts: Texts) -> float:
    """C 返回的每个指标的元信息与默认取值（存法 2、4 的定义）一致的比例。"""
    with conn.cursor() as cur:
        rows: tuple[Any, ...] = fetch(cur, case.sql, case.params)
    matched: int = sum(1 for row in rows if row[-1] == texts.default[int(row[0]) - big.metric_base - 1])
    return matched / big.metrics


def run_tier(
    ratio: float,
    sources: Sequence[Source],
    catalogs: Sequence[Texts],
    layouts: Sequence[Layout],
    config: Config,
    out: Output,
) -> TierResult:
    conn: pymysql.Connection = connect()
    raw: pymysql.Connection = connect(raw=True)
    datadir: str = os.path.join(WORK, "data")
    big_pos: int = next(k for k, s in enumerate(sources) if s.big)
    big: Source = sources[big_pos]
    big_texts: Texts = catalogs[big_pos]
    label: str = f"{ratio:.0%}"
    result: TierResult = TierResult(ratio, config.shape.members, sum(s.metrics for s in sources), 0.0)

    log(f"ratio {label}: loading {result.members:,} members into {len(layouts)} layouts")
    start: float = time.perf_counter()
    for layout in layouts:
        layout.create(conn)
    loaders: dict[str, Loader] = {}
    for layout in layouts:
        loaders.update(layout.loaders(conn))
    big_flags: bytearray = bytearray()
    inconsistent: int = 0
    for src, texts in zip(sources, catalogs):
        flags: bytearray = build_flags(src, ratio)
        usage: Usage = metric_usage(src, flags)
        inconsistent += sum(flags)
        for layout in layouts:
            layout.emit(loaders, src, texts, flags, usage)
        if src.big:
            big_flags = flags
    for loader in loaders.values():
        loader.flush()
    result.load_seconds = time.perf_counter() - start
    big_usage: Usage = metric_usage(big, big_flags)
    out(f"# ratio {label}: inconsistent members {inconsistent:,} of {result.members:,}")
    out(
        f"big source: {sum(big_flags):,} inconsistent members, {sum(big_usage.variant):,} of {big.metrics:,} metrics "
        f"have at least one inconsistent member; load {result.load_seconds:,.0f} s"
    )
    out("")

    out(f"## {label}: sizes after load (information_schema after ANALYZE)")
    out(SIZE_HEADER)
    for layout in layouts:
        result.sizes[layout.key] = table_sizes(conn, layout.tables)
        for line in size_lines(result.sizes[layout.key]):
            out(line)
    result.datadir_peak = max(result.datadir_peak, dir_size(datadir))
    out("")
    for layout in [x for x in layouts if x.volume_only]:
        layout.drop(conn)
    active: list[Layout] = [x for x in layouts if not x.volume_only]
    for layout in active:
        out(f"verify {layout.key} after load: {layout.verify(conn, big.group_id, 'ms')}")
    out("")

    probes: Probes = build_probes(big, big_texts, POINT_SAMPLES)
    for layout in active:
        warm(conn, layout.tables)
    out(
        f"## {label}: reads on the big source, wall ms over unix socket without type conversion "
        "(A = point, B = one scope, C = all metrics' default)"
    )
    out(TIMING_HEADER)
    plans: list[str] = []
    for layout in active:
        result.reads[layout.key] = {}
        result.agreement[layout.key] = {}
        for case in layout.read_cases(probes):
            timing: Timing = measure(f"{layout.key}.{case.name}", raw, case, config)
            result.reads[layout.key][case.name] = timing
            out(timing.line())
            plans.append(f"{layout.key}.{case.name}: {explain(conn, case.sql, case.params)}")
            if case.name.startswith("C"):
                result.agreement[layout.key][case.name] = agreement(conn, case, big, big_texts)
    out("")
    out(f"## {label}: C result equal to the default value (share of {big.metrics:,} metrics)")
    for layout in active:
        out(
            f"{layout.key}: "
            + ", ".join(f"{name} {share:.2%}" for name, share in result.agreement[layout.key].items())
        )
    out("")

    state: State = State(big, big_texts, big_flags)
    budget: Budget = config.budget(APPLY)
    batches: list[list[Report]] = build_batches(state, budget.warmup + budget.iterations, f"apply:{ratio}")
    out(
        f"## {label}: D apply, {BATCH} reports per batch with {CHANGED} changed to a new value, one transaction "
        f"per batch, {budget.iterations} batches after {budget.warmup} warmup (rows = rows written)"
    )
    out(TIMING_HEADER)
    for layout in active:
        timing = Timing(f"{layout.key}.D")
        before: int = 0
        with conn.cursor() as cur:
            for k, batch in enumerate(batches):
                if k == budget.warmup:
                    before = pool_reads(conn)
                start = time.perf_counter()
                stmts, written = layout.apply(cur, big, batch)
                elapsed: float = (time.perf_counter() - start) * 1000
                if k >= budget.warmup:
                    timing.add(elapsed, written, stmts)
        timing.disk_reads = pool_reads(conn) - before
        log(f"{timing.name}: p50 {timing.p50:,.3f} ms, written {timing.mean_rows:,.1f}")
        result.apply[layout.key] = timing
        out(timing.line())
        for name, sql, params in layout.write_plans(big, batches[0]):
            plans.append(f"{layout.key}.{name}: {explain(conn, sql, params)}")
    out("")

    plan: Upgrade = build_upgrade(state)
    out(
        f"## {label}: E unit ms -> s on all {big.members:,} big-source members, segments of {SEGMENT:,} members "
        f"along the member unique key, one transaction per segment, writes in statements of {WRITE_CHUNK:,} rows"
    )
    out(STEP_HEADER)
    for layout in active:
        log(f"{layout.key}.E: apply")
        with conn.cursor() as cur:
            steps: list[Step] = [layout.upgrade(cur, big, plan)]
            out(steps[0].line())
            if layout.compacts:
                result.peak[layout.key] = table_sizes(conn, layout.tables)
                log(f"{layout.key}.E: compact")
                for step in layout.compact(cur, big, big_texts):
                    steps.append(step)
                    out(step.line())
        result.upgrade[layout.key] = steps
        log(f"{layout.key}.E: {sum(s.rows for s in steps):,} rows in {sum(s.seconds for s in steps):,.1f} s")
    out("")
    for layout in active:
        out(f"verify {layout.key} after E: {layout.verify(conn, big.group_id, 's')}")
    out("")

    out(f"## {label}: sizes after E (2 and 4 also after the apply step, before compaction)")
    out(SIZE_HEADER)
    for layout in active:
        result.after[layout.key] = table_sizes(conn, layout.tables)
        for line in size_lines(result.after[layout.key]):
            out(line)
        for table, s in result.peak.get(layout.key, {}).items():
            out(size_lines({f"{table}*": s})[0])
    result.datadir_peak = max(result.datadir_peak, dir_size(datadir))
    out("* = after the apply step of E, before compaction")
    out("")

    out(f"## {label}: EXPLAIN (table:key/type rows [Extra])")
    for line in plans:
        out(line)
    out("")
    for layout in active:
        layout.drop(conn)
    raw.close()
    conn.close()
    return result


# ---------------------------------------------------------------- 汇总


def extrapolate(sizes: dict[str, Size], member_table: str, result: TierResult) -> float:
    """成员表按每成员字节乘平台成员数，定义与值表按每个指标的字节乘平台定义数（外推，非实测）。"""
    member: int = sizes[member_table].total
    side: int = sum(s.total for t, s in sizes.items() if t != member_table)
    return member / result.members * PLATFORM_MEMBERS + side / result.definitions * PLATFORM_DEFINITIONS


def report_volume(results: Sequence[TierResult], layouts: Sequence[Layout], out: Output) -> None:
    for title, pick in (("after load", "sizes"), ("after E", "after")):
        out(
            f"## summary: volume {title}, data + index of all tables of the layout, "
            f"B/member over {results[0].members:,} members, ext = extrapolated to platform"
        )
        out(f"{'layout':<40}" + "".join(f"{f'{r.ratio:.0%} MiB':>11}{'B/member':>10}{'ext GiB':>9}" for r in results))
        for layout in layouts:
            if pick == "after" and layout.volume_only:
                continue
            line: str = f"{layout.label:<40}"
            for r in results:
                sizes: dict[str, Size] = getattr(r, pick)[layout.key]
                total: int = sum(s.total for s in sizes.values())
                line += (
                    f"{mib(total):>11}{total / r.members:>10,.0f}"
                    f"{extrapolate(sizes, layout.member, r) / GIB:>9.2f}"
                )
            out(line)
        out("")
    out(
        f"ext = member table B/member x {PLATFORM_MEMBERS:,} members + definition/value tables B/metric x "
        f"{PLATFORM_DEFINITIONS:,} definitions (extrapolated, M2 caliber in PLAN.md)"
    )
    out("")


def report_reads(results: Sequence[TierResult], layouts: Sequence[Layout], out: Output) -> None:
    cases: list[str] = ["A", "A.join", "B", "B.in", "C", "C.any"]
    for r in results:
        out(f"## summary: reads p50 / p95 ms, ratio {r.ratio:.0%}")
        out(f"{'case':<10}" + "".join(f"{layout.label[:30]:>32}" for layout in layouts))
        for name in cases:
            cells: list[str] = []
            for layout in layouts:
                timing: Timing | None = r.reads[layout.key].get(name)
                cells.append(f"{'-' if timing is None else f'{timing.p50:,.3f} / {timing.p95:,.3f}':>32}")
            out(f"{name:<10}" + "".join(cells))
        out("")
    out(
        "A = spec form (2: definition uk + member uk, 3: member uk + value pk, 4: + value pk when exception); "
        "A.join = one statement; B = one statement (1: range scan, 2-4: JOIN); B.in = members then one IN; "
        "C = definitions (2, 4) or majority vote (1, 3); C.any = MIN(id) member per metric"
    )
    out("")


def report_writes(results: Sequence[TierResult], layouts: Sequence[Layout], out: Output) -> None:
    for r in results:
        out(f"## summary: writes, ratio {r.ratio:.0%} (E.1 = apply, E.2 = compaction scan + promote + clear)")
        out(
            f"{'layout':<40}{'D p50':>8}{'D p95':>8}{'stmts':>7}{'rows':>6}{'E.1 rows':>11}{'E.1 s':>8}"
            f"{'E.2 rows':>11}{'E.2 s':>8}{'E rows':>11}{'E s':>8}"
        )
        for layout in layouts:
            apply: Timing = r.apply[layout.key]
            steps: list[Step] = r.upgrade[layout.key]
            compaction: list[Step] = steps[1:]
            out(
                f"{layout.label:<40}{apply.p50:>8.2f}{apply.p95:>8.2f}{apply.mean_stmts:>7.1f}{apply.mean_rows:>6.0f}"
                f"{steps[0].rows:>11,}{steps[0].seconds:>8.1f}"
                f"{sum(s.rows for s in compaction):>11,}{sum(s.seconds for s in compaction):>8.1f}"
                f"{sum(s.rows for s in steps):>11,}{sum(s.seconds for s in steps):>8.1f}"
            )
        out("")


def report_profile(sources: Sequence[Source], catalogs: Sequence[Texts], config: Config, out: Output) -> None:
    big_pos: int = next(k for k, s in enumerate(sources) if s.big)
    big: Source = sources[big_pos]
    texts: Texts = catalogs[big_pos]
    shape: Shape = config.shape
    out("## data profile")
    out(
        f"big source: group_id {big.group_id}, {big.metrics:,} metrics x {big.scopes} report scopes = "
        f"{big.members:,} members (every scope reports every metric)"
    )
    out(
        f"background: {shape.background} sources x {shape.background_metrics} metrics x {shape.background_scopes} "
        f"scopes = {shape.background * shape.background_metrics * shape.background_scopes:,} members, "
        f"group_ids on both sides of the big source"
    )
    out(
        f"total: {len(sources):,} sources, {sum(s.metrics for s in sources):,} metrics (= definitions), "
        f"{sum(s.scopes for s in sources):,} report scopes, {shape.members:,} members"
    )
    out(
        "inconsistent: exactly ratio x members of every source, drawn with a fixed seed; "
        "an inconsistent member reports the metric's legacy-SDK value (description + ' (legacy sdk)', "
        "temporality delta, interval 30, same unit)"
    )
    out(
        "meta JSON fields as catalog.py definition_meta (unit, description, temporality, interval, usage, "
        f"sub_item for histograms), big source unit ms; avg JSON text {statistics.mean(map(len, texts.default)):.0f} B "
        f"default, {statistics.mean(map(len, texts.variant)):.0f} B legacy; e.g. {texts.default[0]}"
    )
    out(
        "fingerprint = MD5 of the MySQL-normalized JSON text (keys by length then bytes), checked equal to "
        "MD5(meta) on the server, so compaction groups exceptions with MD5(meta) server-side"
    )
    out(
        "layouts 1 and 3 assume the caller already holds metric_id (metric item field_id); 2 and 4 resolve "
        "field_name through the definition unique key; synthetic metric_id and meta_id share numbering"
    )
    out(
        "D: 1 also reads the member fingerprint, 2 reads member meta and fingerprints it in the client; "
        "definition seen_at refresh and member last_seen refresh are not due, so only changed rows are written"
    )
    out(
        "E: reports carry the new value for every member, segment reads use the member unique key keyset; "
        "2 and 4 then run compaction (count exceptions, promote the most reported value, clear exceptions equal "
        "to it); runs after D, so ~3,300 D-changed members per tier are included"
    )
    out("")


def report_schema(layouts: Sequence[Layout], out: Output) -> None:
    out("## schema")
    for layout in layouts:
        for ddl in layout.ddl.values():
            out(f"[{layout.key}] {ddl}")
    out("")
    out("## SQL per case (%s = bound parameter, {keys} = tuples of the batch, {ids} = id list, {rows} = values)")
    for layout in layouts:
        for case, statements in layout.sql.items():
            out(f"[{layout.key}] {case}")
            for sql in statements:
                out(f"    {sql}")
    out("")


def check_canonical(conn: pymysql.Connection, texts: Texts) -> None:
    """客户端规范文本必须与服务端 JSON 输出一致，指纹才能与 MD5(meta) 互换。"""
    samples: list[str] = [*texts.default[:10], *texts.variant[:10]]
    samples += [canonical({**json.loads(t), "unit": "s"}) for t in samples[:4]]
    for text in samples:
        server, digest = execute(conn, "SELECT CAST(CAST(%s AS JSON) AS CHAR), MD5(CAST(%s AS JSON))", (text, text))[0]
        if server != text or digest != md5_hex(text):
            raise SystemExit(f"JSON normalization differs:\n client {text}\n server {server}")


def environment(out: Output, config: Config) -> None:
    conn: pymysql.Connection = connect()
    version: str = execute(conn, "SELECT VERSION()")[0][0]
    variables: dict[str, str] = dict(
        execute(
            conn,
            "SHOW VARIABLES WHERE Variable_name IN ('innodb_buffer_pool_size', 'innodb_redo_log_capacity', "
            "'innodb_flush_log_at_trx_commit', 'log_bin', 'innodb_page_size', 'innodb_flush_method', "
            "'innodb_doublewrite', 'transaction_isolation', 'innodb_autoinc_lock_mode', 'temptable_max_ram', "
            "'range_optimizer_max_mem_size', 'character_set_server')",
        )
    )
    conn.close()
    shape: Shape = config.shape
    out(
        f"# meta layout benchmark: big source {shape.metrics:,} metrics x {shape.scopes} scopes, background "
        f"{shape.background} x {shape.background_metrics} x {shape.background_scopes}, ratios "
        f"{', '.join(f'{r:.0%}' for r in config.ratios)}, layouts {', '.join(config.layouts)}, smoke={config.smoke}"
    )
    out(f"python {platform.python_version()}, pymysql {importlib.metadata.version('pymysql')}, mysql {version}")
    out(f"{platform.system()}/{platform.machine()}, {os.cpu_count()} logical cpu, free disk {free_disk() / GIB:.1f} GiB")
    out(
        f"buffer pool {int(variables['innodb_buffer_pool_size']) / GIB:.0f} GiB, "
        f"innodb_flush_log_at_trx_commit={variables['innodb_flush_log_at_trx_commit']}, binlog {variables['log_bin']}"
    )
    out(", ".join(f"{k}={v}" for k, v in sorted(variables.items())))
    budgets: list[tuple[str, Budget]] = [
        ("point", POINT),
        ("scope", SCOPE),
        ("group", GROUP),
        ("vote", VOTE),
        ("apply", APPLY),
    ]
    out(
        "warmup/iterations: "
        + ", ".join(f"{name} {b.warmup}/{b.iterations}" for name, b in budgets)
        + (f" (smoke overrides all to {SMOKE_BUDGET.warmup}/{SMOKE_BUDGET.iterations})" if config.smoke else "")
    )
    out("timings include the Python client (pymysql 1.1.1) building and escaping statements")
    out("")


# ---------------------------------------------------------------- 入口


def clean() -> None:
    if port_in_use(PORT):
        raise SystemExit(f"port {PORT} is in use, stop mysqld before cleaning")
    shutil.rmtree(WORK, ignore_errors=True)
    print(f"removed {WORK}, free disk {free_disk() / GIB:.1f} GiB")


def run(config: Config, path: str, buffer_pool: str, redo: str) -> None:
    sources: list[Source] = plan_sources(config.shape)
    os.makedirs(WORK, exist_ok=True)
    need: int = config.shape.members * EST_MEMBER_BYTES + parse_bytes(redo) + 2 * GIB - dir_size(WORK)
    if free_disk() - need < DISK_RESERVE:
        raise SystemExit(
            f"need ~{need / GIB:.1f} GiB but free disk is {free_disk() / GIB:.1f} GiB "
            f"with {DISK_RESERVE / GIB:.0f} GiB reserve"
        )
    started: float = time.perf_counter()
    log("building meta texts")
    catalogs: list[Texts] = [build_texts(s) for s in sources]
    proc: subprocess.Popen[bytes] = start_server(buffer_pool, redo)
    try:
        with open(os.path.join(ROOT, path), "w", encoding="utf-8") as fp:
            out: Output = Output(fp)
            environment(out, config)
            conn: pymysql.Connection = connect()
            check_canonical(conn, catalogs[next(k for k, s in enumerate(sources) if s.big)])
            conn.close()
            report_profile(sources, catalogs, config, out)
            layouts: list[Layout] = [LAYOUTS[k]() for k in config.layouts]
            report_schema(layouts, out)
            results: list[TierResult] = [
                run_tier(ratio, sources, catalogs, layouts, config, out) for ratio in config.ratios
            ]
            report_volume(results, layouts, out)
            active: list[Layout] = [x for x in layouts if not x.volume_only]
            report_reads(results, active, out)
            report_writes(results, active, out)
            out(
                f"datadir peak {max(r.datadir_peak for r in results) / GIB:.2f} GiB, "
                f"total run {(time.perf_counter() - started) / 60:.1f} min, free disk {free_disk() / GIB:.1f} GiB"
            )
    finally:
        stop_server(proc)
        log(f"mysqld stopped, free disk {free_disk() / GIB:.1f} GiB")


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(dest="command", required=True)
    run_parser: argparse.ArgumentParser = commands.add_parser("run")
    run_parser.add_argument("--smoke", action="store_true")
    run_parser.add_argument("--ratios", default=",".join(str(r) for r in RATIOS))
    run_parser.add_argument("--layouts", default=",".join(LAYOUTS))
    run_parser.add_argument("--out")
    run_parser.add_argument("--buffer-pool")
    run_parser.add_argument("--redo")
    commands.add_parser("clean")
    args: argparse.Namespace = parser.parse_args()
    if args.command == "clean":
        clean()
        return
    config: Config = Config(
        SMOKE_SHAPE if args.smoke else FULL,
        tuple(float(r) for r in args.ratios.split(",")),
        tuple(args.layouts.split(",")),
        args.smoke,
    )
    path: str = args.out or (os.path.join(WORK, "smoke.txt") if args.smoke else "results/meta_layout.txt")
    run(config, path, args.buffer_pool or ("1G" if args.smoke else "8G"), args.redo or ("64M" if args.smoke else "2G"))


if __name__ == "__main__":
    main()
