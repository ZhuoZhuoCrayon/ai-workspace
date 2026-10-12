#!/usr/bin/env python3
"""A 展开方案在百万指标项基线下的单表与分表压测。

服务并入指标项身份：每个「指标 × 服务 × scope_name」一行 metadata_timeseriesmetric，field_scope 按 Collector 的 APM
范围编码保存「服务-scope_name」。比较单表与按 group_id % 16 分表的体积、管理页、服务页、批量读取、全平台扫描、
日常刷新与在线 DDL。长尾分层与 catalog.py 的 M1 一致，便于与压缩方案对照。
脚本自带独立 mysqld（端口 33309，数据目录 $TMPDIR/cm-explode-bench），不依赖 run.sh 与 bench.py。

在本目录执行：
    # 冒烟：XL 缩小为 300 指标 × 16 服务、长尾取 0.5%，数据目录 < 300 MiB，每个用例只跑 1 + 3 次
    uv run --quiet --with 'pymysql==1.1.1' python explode.py run --smoke
    # 正式（M1 完整）：5 个 XL 分组加全部长尾，1,000,038 个指标项、9,954,638 行
    uv run --quiet --with 'pymysql==1.1.1' python explode.py run --out results/m1_explode.txt
    # 正式（缩减口径）：3 个 XL 分组加部分长尾，磁盘不足以装载完整 M1 时使用
    uv run --quiet --with 'pymysql==1.1.1' python explode.py run --xl-groups 3 --tail-factor 0.2 --out results/m1_explode.txt
    # 删除数据目录
    uv run --quiet --with 'pymysql==1.1.1' python explode.py clean
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import random
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, TextIO

import pymysql
from pymysql.cursors import DictCursor, SSCursor

PORT: int = 33309
WORK: str = os.path.join(os.environ.get("TMPDIR", "/tmp"), "cm-explode-bench")
SOCKET: str = os.path.join(WORK, "mysql.sock")
DATABASE: str = "cm_explode"
ROOT: str = os.path.dirname(os.path.abspath(__file__))
MIB: int = 1024**2
GIB: int = 1024**3
DISK_RESERVE: int = 3 * GIB
# 装载前磁盘检查使用的每行 .ibd 字节预估，实测值见输出
EST_ROW_BYTES: int = 1_000

BASE_TIME: str = "2026-10-11 00:00:00"
NEXT_DAY: str = "2026-10-12 00:00:00"
# TIME_SERIES_METRIC_EXPIRED_SECONDS 为 30 d
EXPIRE_SINCE: str = "2026-09-11 00:00:00"
STALE_TIME: str = "2026-08-20 00:00:00"
CREATE_TIME: str = "2026-06-01 00:00:00"
LOAD_CHUNK_ROWS: int = 100_000
SHARD_COUNT: int = 16
# metadata.utils.db.filter_model_by_in_page 的默认分页
IN_PAGE_SIZE: int = 500
KEYSET_SIZE: int = 10_000
PAGE_SIZE: int = 50
DEEP_OFFSET: int = 10_000
STALE_SERVICE_PERCENT: int = 3
SCOPE_NAMES: tuple[str, str] = ("default", "custom")
TOTAL_METRICS: int = 1_000_000

TAGS: tuple[str, ...] = (
    "app_name",
    "service_name",
    "scope_name",
    "bk_target_ip",
    "instance",
    "namespace",
    "pod",
    "container",
    "node",
    "callee_method",
    "callee_service",
    "callee_server",
    "caller_service",
    "caller_server",
    "code",
    "code_type",
    "env",
    "region",
    "user_type",
)
# 每个指标 15 至 19 个维度名，平均 17 个
TAG_LISTS: tuple[str, ...] = tuple(json.dumps(list(TAGS[: 15 + k])) for k in range(5))
METRIC_STEMS: tuple[str, ...] = (
    "trpc_server_handled_seconds_bucket",
    "trpc_client_handled_total",
    "go_memstats_heap_alloc_bytes",
    "process_resident_memory_bytes",
    "ActsLotteryDrawFailTotal",
    "timer_task_duration_seconds_sum",
    "rpc_server_handled_seconds_count",
    "LockFailLoginCount",
)
DISABLED_CONFIG: str = json.dumps({"disabled": True})


@dataclass(frozen=True)
class Profile:
    name: str
    metrics: int
    services: int
    pairs: int

    @property
    def dense(self) -> bool:
        return self.pairs >= self.metrics * self.services


# XL 按任务口径为 20,000 个指标 × 50 个服务全量上报，M1 与 M2 都是 5 个，受单数据源 1,000,000 成员上限约束
XL: Profile = Profile("XL", 20_000, 50, 1_000_000)
SMOKE_XL: Profile = Profile("XL", 300, 16, 4_800)
XL_GROUPS: int = 5
# 长尾与 catalog.py 一致：L、M、S 取自 bkte 实测（成员 = 指标 × 服务 × 密度 0.717、0.810、0.657），XS 补足 1,000,000 个指标项。
# M1 按 15 min 活跃服务数，M2 按 30 d 登记服务数；M2 只用于外推，不装载。
TIERS: dict[str, tuple[tuple[Profile, int], ...]] = {
    "m1": (
        (Profile("L", 221, 28, 4_437), 600),
        (Profile("M", 145, 6, 705), 2_000),
        (Profile("S", 83, 4, 218), 3_000),
    ),
    "m2": (
        (Profile("L", 221, 126, 19_966), 1_550),
        (Profile("M", 145, 12, 1_409), 2_000),
        (Profile("S", 83, 8, 436), 3_000),
    ),
}
XS: Profile = Profile("XS", 111, 2, 111)


def tail_tiers(scale: str, xl: Profile) -> list[tuple[Profile, int]]:
    tiers: list[tuple[Profile, int]] = list(TIERS[scale])
    rest: int = TOTAL_METRICS - XL_GROUPS * xl.metrics - sum(p.metrics * n for p, n in tiers)
    return [*tiers, (XS, max(0, round(rest / XS.metrics)))]


@dataclass(frozen=True)
class Expected:
    metrics: int
    rows: int
    tail_groups: int
    tail_rows: int


def expected(scale: str, xl: Profile) -> Expected:
    """完整 M1、M2 的期望规模，按画像的「指标 × 服务」数计算，不生成数据。"""
    tiers: list[tuple[Profile, int]] = tail_tiers(scale, xl)
    tail_rows: int = sum(p.pairs * n for p, n in tiers)
    return Expected(
        XL_GROUPS * xl.metrics + sum(p.metrics * n for p, n in tiers),
        XL_GROUPS * xl.pairs + tail_rows,
        sum(n for _, n in tiers),
        tail_rows,
    )


@dataclass(frozen=True)
class Budget:
    warmup: int
    iterations: int


LIGHT: Budget = Budget(30, 300)
HEAVY: Budget = Budget(5, 50)
BULK: Budget = Budget(3, 30)
SCAN: Budget = Budget(0, 3)
SMOKE_BUDGET: Budget = Budget(1, 3)


@dataclass(frozen=True)
class Config:
    xl: Profile
    xl_groups: int
    tail_factor: float
    smoke: bool

    def budget(self, budget: Budget) -> Budget:
        return SMOKE_BUDGET if self.smoke else budget


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


class Output:
    """结果写标准输出与 --out 文件，进度日志写标准错误。"""

    def __init__(self, fp: TextIO) -> None:
        self.fp = fp

    def __call__(self, line: str = "") -> None:
        print(line, flush=True)
        self.fp.write(line + "\n")
        self.fp.flush()


# ---------------------------------------------------------------- 数据画像


def apm_escape(part: str) -> str:
    return part.replace("%", "%25").replace("-", "%2D")


def apm_raw_scope(service: str, scope_name: str) -> str:
    """Collector APM 范围编码：各部分先转义 % 与 -，再用 - 连接。"""
    return f"{apm_escape(service)}-{apm_escape(scope_name)}"


def like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def scope_name_of(metric_idx: int) -> str:
    return SCOPE_NAMES[metric_idx % len(SCOPE_NAMES)]


def metric_name(metric_idx: int) -> str:
    return f"{METRIC_STEMS[metric_idx % len(METRIC_STEMS)]}_{metric_idx:05d}"


def field_config(group_id: int, metric_idx: int) -> str:
    """0.5% 的指标被用户禁用，5% 配置别名，2% 配置单位与聚合方法，其余为空对象；同一指标的各服务行配置一致。"""
    bucket: int = (group_id * 7919 + metric_idx * 104729) % 1000
    if bucket < 5:
        return DISABLED_CONFIG
    if bucket < 55:
        return json.dumps({"alias": f"metric {metric_idx}"})
    if bucket < 75:
        return json.dumps({"unit": "ms", "aggregate_method": "sum"})
    return "{}"


@dataclass(frozen=True)
class Group:
    group_id: int
    profile: Profile

    @property
    def table_prefix(self) -> str:
        return f"space_4228598_bkapm_metric_app{self.group_id:04d}-microservices-production"

    def service(self, service_idx: int) -> str:
        return f"app{self.group_id:04d}-activities-svc-{service_idx:03d}"

    def is_stale(self, service_idx: int) -> bool:
        """约 3% 的服务超过 30 d 未上报，bmw 不再刷新，批量读取按 last_modify_time 过滤掉。"""
        return (self.group_id * 31 + service_idx * 17) % 100 < STALE_SERVICE_PERCENT

    def members(self) -> list[list[int]]:
        """按服务列出上报的指标下标；XL 的每个服务上报全部指标，长尾按画像密度随机抽取，每个指标至少一个服务。"""
        profile: Profile = self.profile
        if profile.dense:
            return [list(range(profile.metrics)) for _ in range(profile.services)]
        rng: random.Random = random.Random(self.group_id)
        avg: float = profile.pairs / profile.metrics
        by_service: list[list[int]] = [[] for _ in range(profile.services)]
        for i in range(profile.metrics):
            count: int = int(avg) + (1 if rng.random() < avg - int(avg) else 0)
            for j in rng.sample(range(profile.services), min(profile.services, max(1, count))):
                by_service[j].append(i)
        for metric_idxs in by_service:
            metric_idxs.sort()
        return by_service


def build_plan(config: Config) -> list[Group]:
    """XL 分组均匀插入 group_id 序列并落在互不相同的分表，长尾画像按固定种子打散。"""
    tail: list[Profile] = [
        p for p, n in tail_tiers("m1", config.xl) for _ in range(max(1, round(n * config.tail_factor)))
    ]
    random.Random(2026).shuffle(tail)
    total: int = len(tail) + config.xl_groups
    xl_ids: list[int] = []
    for k in range(1, config.xl_groups + 1):
        candidate: int = max(1, total * k // (config.xl_groups + 1))
        while candidate % SHARD_COUNT in {g % SHARD_COUNT for g in xl_ids}:
            candidate += 1
        xl_ids.append(candidate)
    rest: Iterator[Profile] = iter(tail)
    return [Group(g, config.xl if g in xl_ids else next(rest)) for g in range(1, total + 1)]


@dataclass
class PlanStats:
    groups: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, int] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    shard_rows: list[int] = field(default_factory=lambda: [0] * SHARD_COUNT)

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())

    @property
    def total_metrics(self) -> int:
        return sum(self.metrics.values())


def plan_stats(plan: Sequence[Group]) -> PlanStats:
    stats: PlanStats = PlanStats()
    for group in plan:
        name: str = group.profile.name
        rows: int = sum(len(m) for m in group.members())
        stats.groups[name] = stats.groups.get(name, 0) + 1
        stats.metrics[name] = stats.metrics.get(name, 0) + group.profile.metrics
        stats.rows[name] = stats.rows.get(name, 0) + rows
        stats.shard_rows[group.group_id % SHARD_COUNT] += rows
    return stats


def generate(plan: Sequence[Group]) -> Iterator[tuple[int, list[Any]]]:
    """按分组、服务、指标的顺序产出行，field_id 与 scope_id 全局递增；每个「服务 × scope_name」对应一个页面分组。"""
    field_id: int = 0
    scope_id: int = 0
    for group in plan:
        g: int = group.group_id
        names: list[str] = [metric_name(i) for i in range(group.profile.metrics)]
        configs: list[str] = [field_config(g, i) for i in range(group.profile.metrics)]
        for service_idx, metric_idxs in enumerate(group.members()):
            service: str = group.service(service_idx)
            stale: bool = group.is_stale(service_idx)
            when: str = STALE_TIME if stale else BASE_TIME
            scopes: dict[str, tuple[int, str]] = {}
            for scope_name in SCOPE_NAMES:
                scope_id += 1
                scopes[scope_name] = (scope_id, apm_raw_scope(service, scope_name))
            for i in metric_idxs:
                field_id += 1
                sid, field_scope = scopes[scope_name_of(i)]
                yield (
                    g,
                    [
                        field_id,
                        g,
                        0 if configs[i] == DISABLED_CONFIG else sid,
                        f"{group.table_prefix}.{names[i]}",
                        field_scope,
                        names[i],
                        TAG_LISTS[i % len(TAG_LISTS)],
                        configs[i],
                        CREATE_TIME,
                        when,
                        "",
                        0 if stale else 1,
                        0,
                    ],
                )


# ---------------------------------------------------------------- MySQL


def free_disk() -> int:
    return shutil.disk_usage(WORK if os.path.isdir(WORK) else os.path.dirname(WORK)).free


def dir_size(path: str) -> int:
    total: int = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def parse_bytes(value: str) -> int:
    units: dict[str, int] = {"K": 1024, "M": MIB, "G": GIB}
    return int(value[:-1]) * units[value[-1].upper()] if value[-1].upper() in units else int(value)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def connect(raw: bool = False, database: str | None = DATABASE) -> pymysql.Connection:
    """raw 连接不做类型转换，计时只覆盖服务端执行与传输，不含 Python 解码 datetime、JSON 的开销。"""
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


def execute(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None = None) -> tuple[Any, ...]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def stream(conn: pymysql.Connection, sql: str, params: Sequence[Any]) -> tuple[int, Any]:
    """无缓冲游标逐行读取，大结果集不在客户端堆积；返回行数与最后一行。"""
    with conn.cursor(SSCursor) as cur:
        cur.execute(sql, params)
        rows: int = 0
        last: Any = None
        for last in cur.fetchall_unbuffered():
            rows += 1
        return rows, last


def pool_reads(conn: pymysql.Connection) -> int:
    return int(execute(conn, "SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_reads'")[0][1])


def start_server(buffer_pool: str, redo: str) -> subprocess.Popen[bytes]:
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
        execute(conn, f"CREATE DATABASE IF NOT EXISTS {DATABASE}")
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


class DiskLow(RuntimeError):
    pass


class Loader:
    """把行写入临时 TSV，按块执行 LOAD DATA LOCAL INFILE；每块之后检查磁盘余量。"""

    def __init__(self, conn: pymysql.Connection, table: str) -> None:
        self.conn = conn
        self.table = table
        self.rows: list[str] = []
        self.total: int = 0

    def add(self, row: Sequence[Any]) -> None:
        self.rows.append("\t".join("\\N" if v is None else str(v) for v in row))
        if len(self.rows) >= LOAD_CHUNK_ROWS:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        with tempfile.NamedTemporaryFile(
            "w", suffix=".tsv", delete=False, encoding="utf-8", dir=os.path.join(WORK, "load")
        ) as fp:
            fp.write("\n".join(self.rows) + "\n")
            path: str = fp.name
        try:
            execute(
                self.conn,
                f"LOAD DATA LOCAL INFILE %s INTO TABLE {self.table} CHARACTER SET utf8mb4 "
                f"FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' ({', '.join(LOAD_COLUMNS)})",
                (path,),
            )
        finally:
            os.unlink(path)
        self.total += len(self.rows)
        self.rows = []
        if free_disk() < DISK_RESERVE + 512 * MIB:
            raise DiskLow(f"free disk {free_disk() / GIB:.1f} GiB below reserve while loading {self.table}")


# bk-monitor TimeSeriesMetric：field_scope、field_name 为 utf8_bin，tag_list 为 LONGTEXT 存 JSON，field_config 为 JSON
METRIC_TABLE: str = """
    field_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    group_id INT NOT NULL,
    scope_id INT NULL,
    table_id VARCHAR(255) NOT NULL DEFAULT '',
    field_scope VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL DEFAULT 'default',
    field_name VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
    tag_list LONGTEXT NOT NULL,
    field_config JSON NOT NULL,
    create_time DATETIME(6) NULL,
    last_modify_time DATETIME(6) NOT NULL,
    label VARCHAR(255) NOT NULL DEFAULT '',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    last_index INT NOT NULL DEFAULT 0,
    UNIQUE KEY uk_identity (group_id, field_scope, field_name),
    KEY idx_group (group_id),
    KEY idx_scope (scope_id),
    KEY idx_label (label),
    KEY idx_active (is_active),
    KEY idx_group_scope_field (group_id, scope_id, field_name)
"""
LOAD_COLUMNS: list[str] = [
    "field_id",
    "group_id",
    "scope_id",
    "table_id",
    "field_scope",
    "field_name",
    "tag_list",
    "field_config",
    "create_time",
    "last_modify_time",
    "label",
    "is_active",
    "last_index",
]


@dataclass(frozen=True)
class Layout:
    name: str
    tables: list[str]

    def table(self, group_id: int) -> str:
        return self.tables[0] if len(self.tables) == 1 else self.tables[group_id % SHARD_COUNT]


LAYOUTS: dict[str, Layout] = {
    "single": Layout("single", ["a_metric"]),
    "shard": Layout("shard", [f"a_metric_{k:02d}" for k in range(SHARD_COUNT)]),
}


def load(layout: Layout, plan: Sequence[Group]) -> float:
    conn: pymysql.Connection = connect()
    for table in layout.tables:
        execute(conn, f"DROP TABLE IF EXISTS {table}")
        execute(conn, f"CREATE TABLE {table} ({METRIC_TABLE}) DEFAULT CHARSET=utf8mb3")
    loaders: dict[str, Loader] = {t: Loader(conn, t) for t in layout.tables}
    start: float = time.perf_counter()
    for loaded, (group_id, row) in enumerate(generate(plan), start=1):
        loaders[layout.table(group_id)].add(row)
        if loaded % 1_000_000 == 0:
            log(f"{layout.name}: generated {loaded:,} rows, free disk {free_disk() / GIB:.1f} GiB")
    for loader in loaders.values():
        loader.flush()
    for table in layout.tables:
        execute(conn, f"ANALYZE TABLE {table}")
    conn.close()
    return time.perf_counter() - start


# ---------------------------------------------------------------- 体积


@dataclass(frozen=True)
class Size:
    rows: int
    data: int
    index: int
    ibd: int


def table_sizes(conn: pymysql.Connection, tables: Sequence[str]) -> dict[str, Size]:
    execute(conn, "SET SESSION information_schema_stats_expiry = 0")
    datadir: str = execute(conn, "SELECT @@datadir")[0][0]
    sizes: dict[str, Size] = {}
    for table in tables:
        rows: int = execute(conn, f"SELECT COUNT(*) FROM {table}")[0][0]
        data, index = execute(
            conn,
            "SELECT data_length, index_length FROM information_schema.TABLES WHERE table_schema = %s AND table_name = %s",
            (DATABASE, table),
        )[0]
        ibd: int = os.path.getsize(os.path.join(datadir, DATABASE, f"{table}.ibd"))
        sizes[table] = Size(rows, int(data), int(index), ibd)
    return sizes


def index_sizes(conn: pymysql.Connection, tables: Sequence[str]) -> dict[str, int]:
    page: int = execute(conn, "SELECT @@innodb_page_size")[0][0]
    marks: str = ", ".join(["%s"] * len(tables))
    rows: tuple[Any, ...] = execute(
        conn,
        "SELECT index_name, SUM(stat_value) FROM mysql.innodb_index_stats "
        f"WHERE database_name = %s AND table_name IN ({marks}) AND stat_name = 'size' GROUP BY index_name",
        (DATABASE, *tables),
    )
    return {name: int(pages) * page for name, pages in rows}


def mib(value: float) -> str:
    return f"{value / MIB:,.1f}"


def total_size(sizes: dict[str, Size]) -> Size:
    return Size(
        sum(s.rows for s in sizes.values()),
        sum(s.data for s in sizes.values()),
        sum(s.index for s in sizes.values()),
        sum(s.ibd for s in sizes.values()),
    )


SIZE_HEADER: str = (
    f"{'table':<20}{'rows':>13}{'data MiB':>11}{'index MiB':>11}{'ibd MiB':>11}{'ibd B/row':>11}{'d+i B/row':>11}"
)


def size_line(name: str, s: Size) -> str:
    rows: int = max(1, s.rows)
    return (
        f"{name:<20}{s.rows:>13,}{mib(s.data):>11}{mib(s.index):>11}{mib(s.ibd):>11}"
        f"{s.ibd / rows:>11,.0f}{(s.data + s.index) / rows:>11,.0f}"
    )


def report_sizes(conn: pymysql.Connection, layout: Layout, out: Output) -> dict[str, Size]:
    sizes: dict[str, Size] = table_sizes(conn, layout.tables)
    out(f"## {layout.name}: table sizes (information_schema after ANALYZE, ibd = file on disk)")
    out(SIZE_HEADER)
    if len(layout.tables) == 1:
        out(size_line(layout.tables[0], sizes[layout.tables[0]]))
    else:
        ordered: list[str] = sorted(layout.tables, key=lambda t: sizes[t].rows)
        out(size_line(f"min {ordered[0]}", sizes[ordered[0]]))
        out(size_line(f"median {ordered[len(ordered) // 2]}", sizes[ordered[len(ordered) // 2]]))
        out(size_line(f"max {ordered[-1]}", sizes[ordered[-1]]))
        out(size_line(f"sum of {len(layout.tables)}", total_size(sizes)))
    out("")
    rows: int = total_size(sizes).rows
    out(f"## {layout.name}: index sizes (innodb_index_stats size pages, summed over tables)")
    for name, value in sorted(index_sizes(conn, layout.tables).items(), key=lambda kv: -kv[1]):
        out(f"{name:<24}{mib(value):>11} MiB{value / max(1, rows):>9,.0f} B/row")
    out(f"datadir on disk {mib(dir_size(os.path.join(WORK, 'data')))} MiB, free disk {free_disk() / GIB:.1f} GiB")
    out("")
    return sizes


# ---------------------------------------------------------------- 用例

ENABLED: str = "NOT (scope_id = 0 AND scope_id IS NOT NULL)"
# Django：field_config__disabled__isnull=True | field_config__disabled=False
NOT_DISABLED: str = (
    f"{ENABLED} AND (JSON_EXTRACT(field_config, '$.\"disabled\"') IS NULL "
    "OR JSON_EXTRACT(field_config, '$.\"disabled\"') = JSON_EXTRACT('false', '$'))"
)
# QueryTimeSeriesMetricResource 的 .only(...)，按指标名去重后取代表值
MGMT_COLUMNS: str = (
    "field_name, MIN(field_id), COUNT(*), ANY_VALUE(scope_id), ANY_VALUE(tag_list), ANY_VALUE(field_config), "
    "MIN(create_time), MAX(last_modify_time)"
)
MGMT_ORDERS: dict[str, str] = {"name": "field_name", "update": "MAX(last_modify_time) DESC, field_name"}
PAGE_COLUMNS: str = "field_id, scope_id, field_name, tag_list, field_config, field_scope, create_time, last_modify_time"
ALL_COLUMNS: str = (
    "field_id, group_id, scope_id, table_id, field_scope, field_name, tag_list, field_config, create_time, "
    "last_modify_time, label, is_active, last_index"
)


def mgmt_sql(table: str, order: str) -> str:
    return (
        f"SELECT {MGMT_COLUMNS} FROM {table} WHERE group_id = %s AND {NOT_DISABLED} "
        f"GROUP BY field_name ORDER BY {MGMT_ORDERS[order]} LIMIT %s, {PAGE_SIZE}"
    )


def count_sql(table: str) -> str:
    return f"SELECT COUNT(DISTINCT field_name) FROM {table} WHERE group_id = %s AND {NOT_DISABLED}"


def service_like_sql(table: str) -> str:
    return (
        f"SELECT {PAGE_COLUMNS} FROM {table} WHERE group_id = %s AND {ENABLED} AND field_scope LIKE %s "
        "ORDER BY field_name"
    )


def service_in_sql(table: str) -> str:
    marks: str = ", ".join(["%s"] * len(SCOPE_NAMES))
    return (
        f"SELECT {PAGE_COLUMNS} FROM {table} WHERE group_id = %s AND {ENABLED} AND field_scope IN ({marks}) "
        "ORDER BY field_name"
    )


def batch_sql(table: str, count: int) -> str:
    marks: str = ", ".join(["%s"] * count)
    return f"SELECT {ALL_COLUMNS} FROM {table} WHERE group_id IN ({marks}) AND last_modify_time > %s"


def keyset_sql(table: str) -> str:
    return f"SELECT {ALL_COLUMNS} FROM {table} WHERE field_id > %s ORDER BY field_id LIMIT {KEYSET_SIZE}"


Statement = tuple[str, tuple[Any, ...]]
Run = Callable[[pymysql.Connection], tuple[int, int]]


@dataclass
class Case:
    name: str
    budget: Budget
    runs: list[Run]
    sql: str
    params: tuple[Any, ...]


def statements_run(statements: Sequence[Statement]) -> Run:
    def run(conn: pymysql.Connection) -> tuple[int, int]:
        return sum(stream(conn, sql, params)[0] for sql, params in statements), len(statements)

    return run


def statement_case(name: str, budget: Budget, statements: Sequence[Statement]) -> Case:
    return Case(name, budget, [statements_run([s]) for s in statements], *statements[0])


def batch_statements(layout: Layout, group_ids: Sequence[int]) -> list[Statement]:
    """filter_model_by_in_page：每 500 个分组一条语句；分表时先按分表拆分，每张表各自分页。"""
    by_table: dict[str, list[int]] = {}
    for g in sorted(group_ids):
        by_table.setdefault(layout.table(g), []).append(g)
    statements: list[Statement] = []
    for table, ids in sorted(by_table.items()):
        for i in range(0, len(ids), IN_PAGE_SIZE):
            chunk: list[int] = ids[i : i + IN_PAGE_SIZE]
            statements.append((batch_sql(table, len(chunk)), (*chunk, EXPIRE_SINCE)))
    return statements


def batch_case(name: str, budget: Budget, layout: Layout, group_sets: Sequence[Sequence[int]]) -> Case:
    per_run: list[list[Statement]] = [batch_statements(layout, ids) for ids in group_sets]
    return Case(name, budget, [statements_run(s) for s in per_run], *per_run[0][0])


def keyset_case(layout: Layout) -> Case:
    """按 field_id 键集分页读取全部行（不过滤过期），分表时逐表扫描。"""

    def run(conn: pymysql.Connection) -> tuple[int, int]:
        rows: int = 0
        stmts: int = 0
        for table in layout.tables:
            last: int = 0
            while True:
                count, row = stream(conn, keyset_sql(table), (last,))
                stmts += 1
                if not count:
                    break
                rows += count
                last = int(row[0])
        return rows, stmts

    return Case("platform.scan_pk10000", SCAN, [run], keyset_sql(layout.tables[0]), (0,))


@dataclass(frozen=True)
class ServicePick:
    group_id: int
    service: str

    @property
    def scopes(self) -> tuple[str, ...]:
        return tuple(apm_raw_scope(self.service, s) for s in SCOPE_NAMES)

    @property
    def like(self) -> str:
        return like_escape(apm_escape(self.service)) + "-%"


@dataclass
class Samples:
    l_groups: list[int]
    l_services: list[ServicePick]
    xl_groups: list[int]
    xl_services: list[ServicePick]
    tail_sets: list[list[int]]
    refresh_xl: list[int]
    refresh_l: list[int]


def build_samples(plan: Sequence[Group]) -> Samples:
    """与 catalog.py 同量：L 取 20 个分组各 5 个服务，XL 取全部分组各 10 个服务；批量读取取 10 组各 500 个长尾分组。"""
    rng: random.Random = random.Random(7)
    l_all: list[Group] = [g for g in plan if g.profile.name == "L"]
    xl_all: list[Group] = [g for g in plan if g.profile.name == "XL"]
    tail: list[int] = [g.group_id for g in plan if g.profile.name != "XL"]
    l_chosen: list[Group] = rng.sample(l_all, min(20, len(l_all)))
    l_services: list[ServicePick] = [
        ServicePick(g.group_id, g.service(j)) for g in l_chosen for j in rng.sample(range(g.profile.services), 5)
    ]
    xl_services: list[ServicePick] = [
        ServicePick(g.group_id, g.service(j))
        for g in xl_all
        for j in rng.sample(range(g.profile.services), min(10, g.profile.services))
    ]
    tail_sets: list[list[int]] = [sorted(rng.sample(tail, min(IN_PAGE_SIZE, len(tail)))) for _ in range(10)]
    refresh_l: list[int] = [g.group_id for g in rng.sample(l_all, min(5, len(l_all)))]
    return Samples(
        [g.group_id for g in l_chosen],
        l_services,
        [g.group_id for g in xl_all],
        xl_services,
        tail_sets,
        [g.group_id for g in xl_all[:3]],
        refresh_l,
    )


def mgmt_cases(layout: Layout, label: str, groups: Sequence[int], budget: Budget, offset: int) -> list[Case]:
    cases: list[Case] = [
        statement_case(f"{label}.mgmt_page1", budget, [(mgmt_sql(layout.table(g), "name"), (g, 0)) for g in groups]),
        statement_case(
            f"{label}.mgmt_page1_update", budget, [(mgmt_sql(layout.table(g), "update"), (g, 0)) for g in groups]
        ),
    ]
    if offset:
        cases.append(
            statement_case(
                f"{label}.mgmt_offset_{offset}",
                budget,
                [(mgmt_sql(layout.table(g), "name"), (g, offset)) for g in groups],
            )
        )
    cases.append(statement_case(f"{label}.mgmt_count", budget, [(count_sql(layout.table(g)), (g,)) for g in groups]))
    return cases


def service_cases(layout: Layout, label: str, picks: Sequence[ServicePick]) -> list[Case]:
    return [
        statement_case(
            f"{label}.service_like",
            LIGHT,
            [(service_like_sql(layout.table(p.group_id)), (p.group_id, p.like)) for p in picks],
        ),
        statement_case(
            f"{label}.service_in",
            LIGHT,
            [(service_in_sql(layout.table(p.group_id)), (p.group_id, *p.scopes)) for p in picks],
        ),
    ]


def build_cases(layout: Layout, plan: Sequence[Group], samples: Samples, config: Config) -> list[Case]:
    offset: int = min(DEEP_OFFSET, config.xl.metrics // 2)
    return [
        *mgmt_cases(layout, "L", samples.l_groups, LIGHT, 0),
        *service_cases(layout, "L", samples.l_services),
        batch_case("L.group_metrics", LIGHT, layout, [[g] for g in samples.l_groups]),
        *mgmt_cases(layout, "XL", samples.xl_groups, HEAVY, offset),
        *service_cases(layout, "XL", samples.xl_services),
        batch_case("XL.group_metrics", BULK, layout, [[g] for g in samples.xl_groups]),
        batch_case("tail500.group_metrics", BULK, layout, samples.tail_sets),
        batch_case("platform.scan_group500", SCAN, layout, [[g.group_id for g in plan]]),
        keyset_case(layout),
    ]


# ---------------------------------------------------------------- 计时


@dataclass
class Timing:
    name: str
    samples: list[float] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)
    stmts: list[int] = field(default_factory=list)
    disk_reads: int = 0

    def pct(self, p: float) -> float:
        ordered: list[float] = sorted(self.samples)
        return ordered[min(len(ordered) - 1, int(len(ordered) * p))]

    @property
    def p50(self) -> float:
        return statistics.median(self.samples)

    @property
    def mean_rows(self) -> float:
        return statistics.mean(self.rows)

    def line(self) -> str:
        return (
            f"{self.name:<36}{self.p50:>12,.3f}{self.pct(0.95):>12,.3f}{max(self.samples):>12,.3f}"
            f"{self.mean_rows:>12,.0f}{statistics.mean(self.stmts):>7.0f}{len(self.samples):>6}"
            f"{self.disk_reads / len(self.samples):>12,.0f}"
        )


TIMING_HEADER: str = (
    f"{'case':<36}{'p50 ms':>12}{'p95 ms':>12}{'max ms':>12}{'rows':>12}{'stmts':>7}{'runs':>6}{'disk rd/run':>12}"
)


def run_case(case: Case, conn: pymysql.Connection, config: Config, prefix: str) -> Timing:
    """请求序列只由用例名决定，单表与分表使用同一组样本与同一顺序；disk rd 为缓冲池未命中的页读取。"""
    budget: Budget = config.budget(case.budget)
    timing: Timing = Timing(f"{prefix}.{case.name}")
    rng: random.Random = random.Random(case.name)
    before: int = 0
    for i in range(budget.warmup + budget.iterations):
        if i == budget.warmup:
            before = pool_reads(conn)
        run: Run = case.runs[rng.randrange(len(case.runs))]
        start: float = time.perf_counter()
        rows, stmts = run(conn)
        elapsed: float = (time.perf_counter() - start) * 1000
        if i >= budget.warmup:
            timing.samples.append(elapsed)
            timing.rows.append(rows)
            timing.stmts.append(stmts)
    timing.disk_reads = pool_reads(conn) - before
    log(f"{timing.name}: p50 {timing.p50:,.3f} ms, rows {timing.mean_rows:,.0f}")
    return timing


def explain(conn: pymysql.Connection, sql: str, params: Sequence[Any]) -> str:
    with conn.cursor(DictCursor) as cur:
        cur.execute("EXPLAIN " + sql, params)
        plans: list[dict[str, Any]] = list(cur.fetchall())
    return "; ".join(
        f"{p['table']}:{p['key'] or 'ALL'}/{p['type']} rows={p['rows']:,} filtered={p['filtered']} [{p['Extra'] or ''}]"
        for p in plans
    )


def explain_analyze(conn: pymysql.Connection, sql: str, params: Sequence[Any]) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("EXPLAIN ANALYZE " + sql, params)
        tree: str = cur.fetchall()[0][0]
    return [f"    {line}" for line in tree.splitlines()]


# ---------------------------------------------------------------- 写入与 DDL


@dataclass(frozen=True)
class Refresh:
    select_ms: float
    update_ms: float
    statements: int
    rows: int


def daily_refresh(conn: pymysql.Connection, table: str, group_id: int) -> Refresh:
    """bmw BulkUpdateMetricsByKeys：先按分组读出指标项，再对仍在上报且超过 24 h 未刷新的行逐行 UPDATE（自动提交）。"""
    with conn.cursor() as cur:
        start: float = time.perf_counter()
        cur.execute(
            "SELECT field_id, field_name, field_scope, tag_list, field_config, last_modify_time, is_active, scope_id "
            f"FROM {table} WHERE group_id = %s",
            (group_id,),
        )
        metrics: tuple[Any, ...] = cur.fetchall()
        select_ms: float = (time.perf_counter() - start) * 1000
        updated: int = 0
        start = time.perf_counter()
        for field_id, _, _, tags, _, _, is_active, scope_id in metrics:
            if not is_active:
                continue
            if scope_id:
                cur.execute(
                    f"UPDATE {table} SET tag_list = %s, last_modify_time = %s, scope_id = %s WHERE field_id = %s",
                    (tags, NEXT_DAY, scope_id, field_id),
                )
            else:
                cur.execute(
                    f"UPDATE {table} SET tag_list = %s, last_modify_time = %s WHERE field_id = %s",
                    (tags, NEXT_DAY, field_id),
                )
            updated += 1
        update_ms: float = (time.perf_counter() - start) * 1000
    return Refresh(select_ms, update_ms, 1 + updated, updated)


def report_refresh(conn: pymysql.Connection, layout: Layout, samples: Samples, out: Output) -> dict[str, list[Refresh]]:
    results: dict[str, list[Refresh]] = {"XL": [], "L": []}
    for label, groups in (("XL", samples.refresh_xl), ("L", samples.refresh_l)):
        for g in groups:
            results[label].append(daily_refresh(conn, layout.table(g), g))
            log(f"{layout.name}.{label}.daily_refresh group {g}: {results[label][-1]}")
    out(f"## {layout.name}: daily refresh per group (bmw select + per-row UPDATE, autocommit), wall ms")
    out(
        f"{'case':<28}{'groups':>7}{'select':>10}{'update':>12}{'total':>12}{'min':>12}{'max':>12}"
        f"{'stmts':>11}{'us/UPDATE':>11}"
    )
    for label, values in results.items():
        totals: list[float] = [v.select_ms + v.update_ms for v in values]
        per_update: float = statistics.median(v.update_ms * 1000 / max(1, v.rows) for v in values)
        out(
            f"{layout.name + '.' + label + '.daily_refresh':<28}{len(values):>7}"
            f"{statistics.median(v.select_ms for v in values):>10,.1f}"
            f"{statistics.median(v.update_ms for v in values):>12,.1f}{statistics.median(totals):>12,.1f}"
            f"{min(totals):>12,.1f}{max(totals):>12,.1f}{statistics.median(v.statements for v in values):>11,.0f}"
            f"{per_update:>11.1f}"
        )
    out("")
    return results


@dataclass(frozen=True)
class Ddl:
    op: str
    table: str
    rows: int
    ibd: int
    seconds: float | None


DDL_OPS: dict[str, tuple[str, str | None]] = {
    "add_column_instant": (
        "ADD COLUMN probe_instant VARCHAR(64) NULL, ALGORITHM=INSTANT",
        "DROP COLUMN probe_instant, ALGORITHM=INSTANT",
    ),
    "add_index_inplace": (
        "ADD INDEX idx_probe (group_id, field_name), ALGORITHM=INPLACE, LOCK=NONE",
        "DROP INDEX idx_probe, ALGORITHM=INPLACE, LOCK=NONE",
    ),
    "add_column_inplace": ("ADD COLUMN probe_inplace VARCHAR(64) NULL, ALGORITHM=INPLACE, LOCK=NONE", None),
}


def ddl_need(op: str, size: Size) -> int:
    """在线 DDL 需要的临时磁盘：加索引按每行 240 B 估算排序文件与新索引，INPLACE 加列重建整表。"""
    if op == "add_index_inplace":
        return size.rows * 240
    if op == "add_column_inplace":
        return int(size.ibd * 1.1)
    return 0


def run_ddl(
    conn: pymysql.Connection, layout: Layout, sizes: dict[str, Size], with_index: Callable[[], None] | None
) -> list[Ddl]:
    results: list[Ddl] = []
    for op, (alter, revert) in DDL_OPS.items():
        for table in sorted(layout.tables, key=lambda t: -sizes[t].rows):
            size: Size = sizes[table]
            if free_disk() - ddl_need(op, size) < DISK_RESERVE:
                log(f"skip {op} on {table}: free disk {free_disk() / GIB:.1f} GiB")
                results.append(Ddl(op, table, size.rows, size.ibd, None))
                continue
            start: float = time.perf_counter()
            execute(conn, f"ALTER TABLE {table} {alter}")
            elapsed: float = time.perf_counter() - start
            results.append(Ddl(op, table, size.rows, size.ibd, elapsed))
            log(f"{layout.name}.{op} {table}: {elapsed:.2f} s, free disk {free_disk() / GIB:.1f} GiB")
            if op == "add_index_inplace" and with_index is not None:
                with_index()
            if revert:
                execute(conn, f"ALTER TABLE {table} {revert}")
    return results


def report_ddl(layout: Layout, results: Sequence[Ddl], out: Output) -> None:
    out(f"## {layout.name}: online DDL, wall seconds (5.7 has no INSTANT, ADD COLUMN there rebuilds like INPLACE here)")
    out(f"{'op':<22}{'table':<22}{'rows':>13}{'ibd MiB':>11}{'seconds':>10}{'rows/s':>12}")

    def line(op: str, label: str, rows: int, ibd: int, seconds: float | None) -> str:
        if seconds is None:
            return f"{op:<22}{label:<22}{rows:>13,}{mib(ibd):>11}{'skipped':>10}{'(disk)':>12}"
        return f"{op:<22}{label:<22}{rows:>13,}{mib(ibd):>11}{seconds:>10.2f}{rows / max(seconds, 1e-6):>12,.0f}"

    for op in DDL_OPS:
        done: list[Ddl] = [r for r in results if r.op == op]
        largest: Ddl = max(done, key=lambda r: r.rows)
        out(line(op, largest.table, largest.rows, largest.ibd, largest.seconds))
        if len(done) > 1:
            measured: list[Ddl] = [r for r in done if r.seconds is not None]
            total: float | None = sum(r.seconds or 0 for r in measured) if len(measured) == len(done) else None
            out(line(op, f"sum of {len(done)}", sum(r.rows for r in done), sum(r.ibd for r in done), total))
    out("")


# ---------------------------------------------------------------- 阶段


@dataclass
class PhaseResult:
    layout: Layout
    load_seconds: float
    sizes: dict[str, Size]
    timings: dict[str, Timing]
    refresh: dict[str, list[Refresh]]
    ddl: list[Ddl]


def run_phase(layout: Layout, plan: Sequence[Group], samples: Samples, config: Config, out: Output) -> PhaseResult:
    log(f"{layout.name}: loading")
    load_seconds: float = load(layout, plan)
    out(f"## {layout.name}: load {load_seconds:,.0f} s into {len(layout.tables)} table(s)")
    out("")
    conn: pymysql.Connection = connect()
    raw: pymysql.Connection = connect(raw=True)
    sizes: dict[str, Size] = report_sizes(conn, layout, out)

    cases: list[Case] = build_cases(layout, plan, samples, config)
    out(f"## {layout.name}: EXPLAIN of the first statement per case (table:key/type rows filtered [Extra])")
    for case in cases:
        out(f"{case.name}: {explain(conn, case.sql, case.params)}")
    out("")
    if layout.name == "single":
        by_name: dict[str, Case] = {c.name: c for c in cases}
        for name in ("XL.mgmt_page1", "XL.mgmt_count", "tail500.group_metrics"):
            log(f"EXPLAIN ANALYZE {name}")
            out(f"## single: EXPLAIN ANALYZE {name}")
            out("\n".join(explain_analyze(conn, by_name[name].sql, by_name[name].params)))
        out("")

    timings: dict[str, Timing] = {}
    for case in cases:
        timings[case.name] = run_case(case, raw, config, layout.name)
    out(
        f"## {layout.name}: read latency, wall ms over unix socket without type conversion, "
        "runs after warmup listed per case"
    )
    out(TIMING_HEADER)
    for timing in timings.values():
        out(timing.line())
    out("")

    refresh: dict[str, list[Refresh]] = report_refresh(conn, layout, samples, out)

    with_index: Callable[[], None] | None = None
    if layout.name == "single":
        offset: int = min(DEEP_OFFSET, config.xl.metrics // 2)
        indexed: list[Case] = mgmt_cases(layout, "XL", samples.xl_groups, HEAVY, offset)

        def run_indexed() -> None:
            out("## single + idx_probe (group_id, field_name): XL management page")
            for case in indexed:
                out(f"{case.name}: {explain(conn, case.sql, case.params)}")
            out(TIMING_HEADER)
            for case in indexed:
                timing: Timing = run_case(case, raw, config, "single+idx")
                timings[f"idx.{case.name}"] = timing
                out(timing.line())
            out("")

        with_index = run_indexed
    ddl: list[Ddl] = run_ddl(conn, layout, sizes, with_index)
    report_ddl(layout, ddl, out)

    for table in layout.tables:
        execute(conn, f"DROP TABLE IF EXISTS {table}")
    raw.close()
    conn.close()
    return PhaseResult(layout, load_seconds, sizes, timings, refresh, ddl)


# ---------------------------------------------------------------- 汇总


def report_profile(plan: Sequence[Group], stats: PlanStats, config: Config, out: Output) -> None:
    m1: Expected = expected("m1", config.xl)
    out("## data profile (A rows = metric x service x scope_name)")
    out(f"{'profile':<9}{'groups':>8}{'metrics':>12}{'services':>10}{'rows':>13}{'rows/metric':>13}")
    profiles: list[Profile] = [config.xl, *(p for p, _ in tail_tiers("m1", config.xl))]
    for profile in profiles:
        name: str = profile.name
        out(
            f"{name:<9}{stats.groups.get(name, 0):>8,}{stats.metrics.get(name, 0):>12,}{profile.services:>10}"
            f"{stats.rows.get(name, 0):>13,}{stats.rows.get(name, 0) / max(1, stats.metrics.get(name, 0)):>13.2f}"
        )
    out(
        f"{'total':<9}{len(plan):>8,}{stats.total_metrics:>12,}{'':>10}{stats.total_rows:>13,}"
        f"{stats.total_rows / stats.total_metrics:>13.2f}"
    )
    xl_ids: list[int] = [g.group_id for g in plan if g.profile.name == config.xl.name]
    out(f"XL group_id -> shard: {', '.join(f'{g} -> {g % SHARD_COUNT:02d}' for g in xl_ids)}")
    ordered: list[int] = sorted(stats.shard_rows)
    out(
        f"rows per shard: min {ordered[0]:,}, median {int(statistics.median(ordered)):,}, max {ordered[-1]:,}; "
        f"full M1 = {m1.metrics:,} metrics, {m1.rows:,} rows, {m1.tail_groups + XL_GROUPS:,} groups; "
        f"loaded {stats.total_rows / m1.rows:.1%} of M1 rows"
    )
    out(
        f"field_scope = '<escaped service>-<scope_name>', e.g. {apm_raw_scope(plan[0].service(1), 'default')!r}; "
        f"{STALE_SERVICE_PERCENT}% services stale (> 30 d), 0.5% metrics disabled (scope_id 0); "
        "rows loaded group by group in field_id order"
    )
    if stats.total_rows < m1.rows:
        out(
            f"reduced scale: {config.xl_groups} XL groups + {config.tail_factor:.0%} of the long tail; "
            "group-level cases run on full XL groups, M1 / M2 platform-wide figures are extrapolated by rows"
        )
    out("")


def report_compare(results: Sequence[PhaseResult], out: Output) -> None:
    if len(results) < 2:
        return
    single, shard = results[0], results[1]
    out("## single vs shard: p50 / p95 ms (same request sequence)")
    out(f"{'case':<28}{'single p50':>13}{'single p95':>13}{'shard p50':>13}{'shard p95':>13}{'rows':>12}{'stmts':>11}")
    for name, timing in single.timings.items():
        other: Timing | None = shard.timings.get(name)
        if other is None:
            continue
        stmts: str = f"{statistics.mean(timing.stmts):.0f}/{statistics.mean(other.stmts):.0f}"
        out(
            f"{name:<28}{timing.p50:>13,.3f}{timing.pct(0.95):>13,.3f}{other.p50:>13,.3f}{other.pct(0.95):>13,.3f}"
            f"{timing.mean_rows:>12,.0f}{stmts:>11}"
        )
    out("")


def report_extrapolation(results: Sequence[PhaseResult], stats: PlanStats, config: Config, out: Output) -> None:
    """按实测每行字节与每行耗时线性外推到完整 M1 与 M2；XL 分组 M1、M2 相同，组内用例不随 M2 放大。"""
    m1: Expected = expected("m1", config.xl)
    m2: Expected = expected("m2", config.xl)
    tag: str = "measured" if stats.total_rows >= m1.rows else "extrapolated"
    out("## volume: measured and extrapolated (ibd bytes per row x rows)")
    out(f"{'layout':<10}{'rows':>13}{'ibd GiB':>10}{'B/row':>8}{'M1 GiB':>10}{'M2 GiB':>10}")
    for result in results:
        total: Size = total_size(result.sizes)
        per_row: float = total.ibd / max(1, total.rows)
        out(
            f"{result.layout.name:<10}{total.rows:>13,}{total.ibd / GIB:>10.2f}{per_row:>8,.0f}"
            f"{per_row * m1.rows / GIB:>10.2f}{per_row * m2.rows / GIB:>10.2f}"
        )
    out(f"M1 = {m1.rows:,} rows ({tag}), M2 = {m2.rows:,} rows (extrapolated, catalog.py m2 tiers)")
    out("")
    tail_groups: int = sum(n for k, n in stats.groups.items() if k != config.xl.name)
    loaded_avg: float = (stats.total_rows - stats.rows.get(config.xl.name, 0)) / max(1, tail_groups)
    m1_avg: float = m1.tail_rows / m1.tail_groups
    m2_avg: float = m2.tail_rows / m2.tail_groups
    out("## platform-wide costs, linear in rows read (XL group cases are the same in M1 and M2)")
    out(f"{'item':<48}{'measured':>12}{'M1':>12}{'M2':>12}")
    for result in results:
        prefix: str = result.layout.name
        for name in ("platform.scan_group500", "platform.scan_pk10000"):
            scan: Timing | None = result.timings.get(name)
            if scan is not None:
                per_row_ms: float = scan.p50 / max(1, scan.mean_rows)
                out(
                    f"{prefix + ' ' + name + ' s':<48}{scan.p50 / 1000:>12,.1f}"
                    f"{per_row_ms * m1.rows / 1000:>12,.1f}{per_row_ms * m2.rows / 1000:>12,.1f}"
                )
        batch: Timing | None = result.timings.get("tail500.group_metrics")
        if batch is not None:
            out(
                f"{prefix + ' tail500.group_metrics ms':<48}{batch.p50:>12,.1f}"
                f"{batch.p50 * m1_avg / loaded_avg:>12,.1f}{batch.p50 * m2_avg / loaded_avg:>12,.1f}"
            )
        for op in ("add_index_inplace", "add_column_inplace"):
            done: list[Ddl] = [r for r in result.ddl if r.op == op and r.seconds is not None]
            if len(done) != len(result.layout.tables):
                continue
            seconds: float = sum(r.seconds or 0 for r in done)
            rows: int = sum(r.rows for r in done)
            out(
                f"{prefix + ' ' + op + ' s (all tables)':<48}{seconds:>12,.1f}"
                f"{seconds * m1.rows / rows:>12,.1f}{seconds * m2.rows / rows:>12,.1f}"
            )
    out(
        f"rows per long-tail group: loaded {loaded_avg:,.0f}, M1 {m1_avg:,.0f}, M2 {m2_avg:,.0f}; "
        f"XL stays {XL_GROUPS} groups x {config.xl.pairs:,} rows in both"
    )
    out("")


def report_reference(out: Output) -> None:
    out("## compressed scheme (metric items 1,000,000 rows + narrow members), measured by catalog.py")
    for name in ("m1_catalog.txt", "m2_catalog.txt"):
        path: str = os.path.join(ROOT, "results", name)
        out(f"results/{name}: {'present' if os.path.exists(path) else 'missing'}")
    out(
        "same-caliber pairs: mgmt_page1 / mgmt_count / mgmt_offset_10000 / mgmt_page1_update <-> q1.page1 / q1.count / "
        "q1.deep / q1.recent; service_* <-> q3.service; L/XL.group_metrics <-> q5.group; "
        "platform.scan_group500 / scan_pk10000 <-> Q6 group500 / pk10000; DDL <-> Q10"
    )
    out("")


def environment(out: Output, config: Config) -> None:
    conn: pymysql.Connection = connect()
    version: str = execute(conn, "SELECT VERSION()")[0][0]
    variables: dict[str, str] = dict(
        execute(
            conn,
            "SHOW VARIABLES WHERE Variable_name IN ('innodb_buffer_pool_size', 'innodb_redo_log_capacity', "
            "'innodb_flush_log_at_trx_commit', 'log_bin', 'innodb_page_size', 'innodb_flush_method', "
            "'temptable_max_ram', 'tmp_table_size', 'sort_buffer_size', 'character_set_server')",
        )
    )
    conn.close()
    out(
        f"# A explode benchmark: xl={config.xl_groups} x {config.xl.metrics:,} metrics x {config.xl.services} "
        f"services, tail_factor={config.tail_factor}, smoke={config.smoke}"
    )
    out(f"python {platform.python_version()}, pymysql {importlib.metadata.version('pymysql')}, mysql {version}")
    out(
        f"{platform.system()}/{platform.machine()}, {os.cpu_count()} logical cpu, free disk {free_disk() / GIB:.1f} GiB"
    )
    out(", ".join(f"{k}={v}" for k, v in sorted(variables.items())))
    out(
        f"warmup/iterations: light {LIGHT.warmup}/{LIGHT.iterations}, heavy {HEAVY.warmup}/{HEAVY.iterations}, "
        f"bulk {BULK.warmup}/{BULK.iterations}, scan {SCAN.warmup}/{SCAN.iterations}"
        + (f" (smoke overrides all to {SMOKE_BUDGET.warmup}/{SMOKE_BUDGET.iterations})" if config.smoke else "")
    )
    out("")


# ---------------------------------------------------------------- 入口


def clean() -> None:
    if port_in_use(PORT):
        raise SystemExit(f"port {PORT} is in use, stop mysqld before cleaning")
    shutil.rmtree(WORK, ignore_errors=True)
    print(f"removed {WORK}, free disk {free_disk() / GIB:.1f} GiB")


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(dest="command", required=True)
    run: argparse.ArgumentParser = commands.add_parser("run")
    run.add_argument("--smoke", action="store_true")
    run.add_argument("--xl-groups", type=int)
    run.add_argument("--tail-factor", type=float)
    run.add_argument("--layouts", default="single,shard")
    run.add_argument("--out")
    run.add_argument("--buffer-pool")
    run.add_argument("--redo")
    commands.add_parser("clean")
    args: argparse.Namespace = parser.parse_args()
    if args.command == "clean":
        clean()
        return

    config: Config = Config(
        SMOKE_XL if args.smoke else XL,
        args.xl_groups or (3 if args.smoke else XL_GROUPS),
        args.tail_factor if args.tail_factor is not None else (0.005 if args.smoke else 1.0),
        args.smoke,
    )
    redo: str = args.redo or ("16M" if args.smoke else "2G")
    plan: list[Group] = build_plan(config)
    stats: PlanStats = plan_stats(plan)
    os.makedirs(WORK, exist_ok=True)
    need: int = stats.total_rows * EST_ROW_BYTES + parse_bytes(redo) + 2 * GIB - dir_size(WORK)
    if free_disk() - need < DISK_RESERVE:
        raise SystemExit(
            f"need ~{need / GIB:.1f} GiB for {stats.total_rows:,} rows but free disk is {free_disk() / GIB:.1f} GiB "
            f"with {DISK_RESERVE / GIB:.0f} GiB reserve; use --xl-groups 3 and a lower --tail-factor"
        )
    path: str = args.out or (os.path.join(WORK, "smoke.txt") if args.smoke else "results/m1_explode.txt")
    proc: subprocess.Popen[bytes] = start_server(args.buffer_pool or ("1G" if args.smoke else "8G"), redo)
    try:
        with open(os.path.join(ROOT, path), "w", encoding="utf-8") as fp:
            out: Output = Output(fp)
            environment(out, config)
            report_profile(plan, stats, config, out)
            samples: Samples = build_samples(plan)
            results: list[PhaseResult] = []
            for name in args.layouts.split(","):
                results.append(run_phase(LAYOUTS[name], plan, samples, config, out))
            report_compare(results, out)
            report_extrapolation(results, stats, config, out)
            report_reference(out)
            out(f"datadir {mib(dir_size(os.path.join(WORK, 'data')))} MiB, free disk {free_disk() / GIB:.1f} GiB")
    finally:
        stop_server(proc)
        log(f"mysqld stopped, free disk {free_disk() / GIB:.1f} GiB")


if __name__ == "__main__":
    main()
