#!/usr/bin/env python3
"""四个完整方案在 MySQL 5.7 上的端到端对比。

A 现状修补、B 服务展开、C 扩列加成员表、D 独立新表。B、C、D 在同一份数据上跑同一组用例，A 不改表，读取用例即现状：
  check     小数据正确性断言：移入自建分组后的服务视图、按范围例外、元信息先到、Histogram 组族、旧代码读新数据
  swallow   迁移被吞：各方案的新代码跑在旧表结构上
  load      上界规模画像的 1,000,000 个指标项全量装载，成员与 B 的展开行只装载 1 个最大数据源与部分背景数据源
  volume    实测每行字节外推到活跃规模与上界规模
  reads     管理页、服务视图、整组读取、全平台扫描，D 另测定义单独读取（D2）
  writes    bmw Apply 每批 1,000 条上报，B 的逐行刷新
  ddl       已有表加列与回退、并发读写、元数据锁排队
  rollback  有数据时 D 删表、B 展开表删列
  compare   与 REPORT 中 MySQL 9.2 的同名用例对照
  supplement 单独运行：管理页搜索、族视图节点分页与单范围读取，只装载指标项、定义与最大数据源的成员
  supplement2 单独运行：C 按 PLAN 写法（C2）的搜索与节点分页、族视图首页完整步骤、服务视图完整路径
数据画像、建表语句与 Apply 写法复用 catalog.py、explode.py、meta_layout.py 与 compat/compat.py。
脚本自带 Docker 容器（mysql:5.7.44，linux/amd64，端口 33311），结束即删除容器与数据卷。

在本目录执行：
    # 冒烟：最大数据源缩小为 2,000 指标 × 67 服务，指标项 60,000 个，每个用例只跑 1 + 3 次
    uv run --quiet --with 'pymysql==1.1.1' python plans57.py run --smoke
    # 正式
    uv run --quiet --with 'pymysql==1.1.1' python plans57.py run --out results/plans57.txt
    # 复测：原生 arm64 的 5.7 社区构建只跑 A/C/D 的读取与全平台扫描，排除 amd64 模拟的影响
    IMAGE_57=biarms/mysql:5.7 PLATFORM_57=linux/arm64 uv run --quiet --with 'pymysql==1.1.1' python plans57.py run \
        --cross-check --out results/plans57_arm64.txt
    # 补测：管理页搜索、族视图节点分页与单范围读取，arm64 复核换镜像后加 --cross-check
    uv run --quiet --with 'pymysql==1.1.1' python plans57.py run --supplement --out results/plans57_supplement.txt
    uv run --quiet --with 'pymysql==1.1.1' python plans57.py run --supplement2 --out results/plans57_supplement2.txt
    # 删除容器与数据卷
    uv run --quiet --with 'pymysql==1.1.1' python plans57.py clean
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, TextIO

import pymysql
from pymysql.constants import CLIENT
from pymysql.cursors import Cursor

import catalog
import explode
import meta_layout
from bench import Loader, apm_raw_scope, execute, fetch, md5_hex, source_key
from catalog import (
    APPLY_BATCH,
    APPLY_CHANGED,
    APPLY_NEW,
    BASE_VARIANT,
    CREATE_TIME,
    DEEP_OFFSET,
    EXCEPTION_SHARE,
    EXPIRE_BEFORE,
    EXPIRED,
    EXPIRED_SHARE,
    FRESH,
    INFO_COLS,
    L_SAMPLE_GROUPS,
    L_SERVICES,
    LABEL_TO_MEMBER,
    MANAGE_WHERE,
    MIXED_GROUPS,
    NOW,
    OVERRIDE_JSON,
    OVERRIDE_SHARE,
    PAGE,
    PAGE_COLS,
    SERVICE_LABEL,
    STALE_BEFORE,
    STAMPS,
    X1,
    X3,
    XL_SERVICES,
    Case,
    Group,
    GroupIndex,
    Stat,
    Tier,
    Variant,
    defs,
)
from compat import compat as cmp

IMAGE: str = os.environ.get("IMAGE_57", "mysql:5.7.44")
PLATFORM: str = os.environ.get("PLATFORM_57", "linux/amd64")
CONTAINER: str = "cm-plans57"
VOLUME: str = "cm-plans57-data"
PORT: int = 33311
DATABASE: str = "cm_plans57"
OLD_DATABASE: str = "cm_plans57_old"
CHECK_DATABASE: str = "cm_plans57_check"
ROOT: str = os.path.dirname(os.path.abspath(__file__))
GIB: int = 1024**3
MIB: int = 1024**2
MAX_DATADIR: int = 14 * GIB + GIB // 2
MIN_FREE: int = 4 * GIB
SERVER_FLAGS: tuple[str, ...] = (
    "--character-set-server=utf8",
    "--collation-server=utf8_general_ci",
    "--innodb-file-per-table=ON",
    "--innodb-default-row-format=DYNAMIC",
    "--innodb-large-prefix=ON",
    "--innodb-file-format=Barracuda",
    "--innodb-flush-log-at-trx-commit=1",
    "--innodb-buffer-pool-instances=8",
    "--local-infile=ON",
    "--max-allowed-packet=256M",
    "--skip-name-resolve",
    "--performance-schema=ON",
)
SCALE: str = "m2"
SMOKE_SCALE: str = "plans57_smoke"
SMOKE_METRICS: int = 60_000
catalog.TIERS[SMOKE_SCALE] = (Tier("XL", 5, 2_000, 67, 100_000, 10), *catalog.TIERS["m2"][1:])
LOADED_XL: int = 1
LOADED_L: int = 60
LOADED_TAIL_SHARE: float = 0.03
SCHEMES: tuple[str, ...] = ("A", "B", "C", "D")
# D2 是 D 的另一种读法：现状语句不变，定义按指标名、数据源或主键单独读取，不与指标项关联
READ_SCHEMES: tuple[str, ...] = (*SCHEMES, "D2")
VARIANT_OF: dict[str, Variant] = {"A": BASE_VARIANT, "C": X1, "D": X3}
B_TABLE: str = "b_timeseriesmetric"
VALUE_TABLE: str = "metric_meta_value"
NULL: str = r"\N"
SCAN_CHUNK: int = 10_000
SCAN_REPEATS: int = 3
REFRESH_SAMPLE: int = 2_000
BASELINE_SECONDS: float = 3.0
CHANGED_TYPE: str = "summary"

MEMBER_DDL: str = catalog.DDL["report_member"].replace("meta JSON NULL", "meta_value_id BIGINT NOT NULL DEFAULT 0")
VALUE_DDL: str = meta_layout.value_ddl(VALUE_TABLE).replace(
    "meta JSON NULL", "meta JSON NULL, retired_at DATETIME(6) NULL"
)
B_DDL: str = catalog.DDL["x1_timeseriesmetric"].replace("x1_timeseriesmetric", B_TABLE, 1)
# BLACKHOLE 的索引上限为 1,000 B，复测时丢弃 B 的展开行，不建二级索引
B_BLACKHOLE_DDL: str = (
    f"CREATE TABLE {B_TABLE} ({catalog.METRIC_COLUMNS},{catalog.X1_COLUMNS}) DEFAULT CHARSET=utf8mb3 ENGINE=BLACKHOLE"
)
NEW_TABLES: dict[str, str] = {
    "x3_metric_meta": catalog.DDL["x3_metric_meta"],
    VALUE_TABLE: VALUE_DDL,
    "report_scope": catalog.DDL["report_scope"],
    "report_scope_label": catalog.DDL["report_scope_label"],
    "report_member": MEMBER_DDL,
}
SHARED_NEW: list[str] = ["report_scope", "report_scope_label", "report_member", VALUE_TABLE]
B_LOAD: list[str] = catalog.LOAD_COLUMNS["x1_timeseriesmetric"]
B_INSERT: list[str] = B_LOAD[1:]
MEMBER_LOAD: list[str] = ["id", "group_id", "report_scope_id", "ref_id", "last_seen", "meta_value_id", "field_config"]
X1_NEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("original_name", "varchar(255) COLLATE utf8_bin"),
    ("metric_type", "varchar(16)"),
    ("meta", "json"),
    ("meta_fingerprint", "char(32)"),
    ("meta_seen_at", "datetime(6)"),
)


@dataclass(frozen=True)
class Config:
    smoke: bool
    scale: str
    metrics: int
    loaded_l: int
    buffer_pool: str
    log_file: str
    cross_check: bool = False
    supplement: bool = False
    supplement2: bool = False


CONFIG: list[Config] = []
RESULT: dict[str, Any] = {"p50": {}}
OUT: list[TextIO] = []


def cfg() -> Config:
    return CONFIG[0]


def emit(line: str = "") -> None:
    print(line, flush=True)
    for fp in OUT:
        fp.write(line + "\n")
        fp.flush()


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def record(key: str, scheme: str, value: float) -> None:
    RESULT["p50"].setdefault(key, {})[scheme] = value


def marks(count: int) -> str:
    return ", ".join(["%s"] * count)


def mib(value: float) -> str:
    return f"{value / MIB:,.1f}"


# ---------------------------------------------------------------- Docker 与连接


def docker(*args: str, check: bool = True) -> str:
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True).stdout


def remove_server() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    subprocess.run(["docker", "volume", "rm", VOLUME], capture_output=True)


ENCODERS: dict[Any, Any] = {k: v for k, v in pymysql.converters.conversions.items() if not isinstance(k, int)}


def connect(raw: bool = False, database: str | None = DATABASE, autocommit: bool = True) -> pymysql.Connection:
    """raw 连接不做类型转换，与 catalog.py 的计时口径一致；TCP 经 Docker 端口转发。"""
    options: dict[str, Any] = {"conv": ENCODERS} if raw else {}
    return pymysql.connect(
        host="127.0.0.1",
        port=PORT,
        user="root",
        password="",
        database=database,
        local_infile=True,
        autocommit=autocommit,
        charset="utf8mb4",
        client_flag=CLIENT.FOUND_ROWS,
        **options,
    )


@dataclass(frozen=True)
class Server:
    """compat.Workload 与 MdlMonitor 只调用 connect()，默认连到本脚本的库。"""

    def connect(self, database: str | None = DATABASE, autocommit: bool = True) -> pymysql.Connection:
        return connect(database=database, autocommit=autocommit)


SERVER: Server = Server()
cmp.DB = DATABASE


def start_server(config: Config) -> None:
    if explode.port_in_use(PORT):
        raise SystemExit(f"port {PORT} is already in use")
    remove_server()
    docker(
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--platform",
        PLATFORM,
        "-p",
        f"127.0.0.1:{PORT}:3306",
        "-e",
        "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
        "-v",
        f"{VOLUME}:/var/lib/mysql",
        IMAGE,
        *SERVER_FLAGS,
        f"--innodb-buffer-pool-size={config.buffer_pool}",
        f"--innodb-log-file-size={config.log_file}",
    )
    for _ in range(300):
        try:
            conn: pymysql.Connection = connect(database=None)
        except pymysql.err.OperationalError:
            time.sleep(1)
            continue
        for db in (DATABASE, OLD_DATABASE, CHECK_DATABASE):
            execute(conn, f"DROP DATABASE IF EXISTS {db}")
            execute(conn, f"CREATE DATABASE {db} DEFAULT CHARACTER SET utf8")
        execute(
            conn,
            "UPDATE performance_schema.setup_instruments SET ENABLED = 'YES', TIMED = 'YES' "
            "WHERE NAME = 'wait/lock/metadata/sql/mdl' OR NAME LIKE 'stage/innodb/alter%'",
        )
        execute(conn, "UPDATE performance_schema.setup_consumers SET ENABLED = 'YES' WHERE NAME LIKE 'events_stages_%'")
        conn.close()
        return
    raise SystemExit("mysqld did not accept connections within 300 s")


class DiskGuard(threading.Thread):
    """每 10 s 统计容器数据目录与临时目录，越过阈值立即删除容器并退出。"""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.peak_data: int = 0
        self.peak_tmp: int = 0
        self.min_free: int = shutil.disk_usage("/").free

    def sample(self) -> tuple[int, int, int]:
        text: str = docker("exec", CONTAINER, "du", "-sk", "/var/lib/mysql", "/tmp", check=False)
        sizes: dict[str, int] = {}
        for line in text.splitlines():
            kb, path = line.split("\t", 1)
            sizes[path] = int(kb) * 1024
        data, tmp = sizes.get("/var/lib/mysql", 0), sizes.get("/tmp", 0)
        free: int = shutil.disk_usage("/").free
        self.peak_data = max(self.peak_data, data)
        self.peak_tmp = max(self.peak_tmp, tmp)
        self.min_free = min(self.min_free, free)
        return data, tmp, free

    def run(self) -> None:
        while True:
            data, tmp, free = self.sample()
            if data > MAX_DATADIR or free < MIN_FREE:
                log(f"abort: datadir {data / GIB:.1f} GiB, tmp {tmp / GIB:.1f} GiB, host free {free / GIB:.1f} GiB")
                remove_server()
                os._exit(75)
            time.sleep(10)


# ---------------------------------------------------------------- 数据画像与外推口径


@dataclass(frozen=True)
class Subset:
    xl: list[Group]
    large: list[Group]
    tail: list[Group]

    @property
    def groups(self) -> list[Group]:
        return sorted([*self.xl, *self.large, *self.tail], key=lambda g: g.group_id)


def select_subset(groups: Sequence[Group], loaded_l: int) -> Subset:
    """最大档取 group_id 最小的 1 个，大型档抽 60 个（126 个服务），中型、小型、微型各抽 3%。"""
    by_tier: dict[str, list[Group]] = {}
    for g in groups:
        by_tier.setdefault(g.tier.name, []).append(g)
    xl: list[Group] = sorted(by_tier["XL"], key=lambda g: g.group_id)[:LOADED_XL]
    large: list[Group] = random.Random("plans57.L").sample(by_tier["L"], min(loaded_l, len(by_tier["L"])))
    tail: list[Group] = []
    for name in ("M", "S", "XS"):
        pool: list[Group] = by_tier.get(name, [])
        if pool:
            tail.extend(random.Random(f"plans57.{name}").sample(pool, max(1, round(len(pool) * LOADED_TAIL_SHARE))))
    return Subset(xl, sorted(large, key=group_key), sorted(tail, key=group_key))


def group_key(g: Group) -> int:
    return g.group_id


@dataclass
class Targets:
    groups: int = 0
    metrics: int = 0
    definitions: int = 0
    members: int = 0
    scopes: int = 0
    values: float = 0.0
    b_rows: float = 0.0


def targets_of(groups: Sequence[Group]) -> Targets:
    """成员数按 member_lists 的抽样数精确计数；例外取值行与 B 的无成员指标行按各范围的抽样概率求期望。"""
    t: Targets = Targets()
    for g in groups:
        shape: catalog.Shape = g.shape
        pools: dict[str, tuple[int, ...]] = {"default": shape.default, "custom": shape.custom}
        miss: dict[str, float] = {"default": 1.0, "custom": 1.0}
        clean: dict[str, float] = {"default": 1.0, "custom": 1.0}
        members: int = 0
        for j in range(g.tier.services):
            for name in ("default", "custom") if catalog.has_custom(j) else ("default",):
                pool: tuple[int, ...] = pools[name]
                if not pool:
                    continue
                take: int = round(shape.density[j] * len(pool))
                members += take
                miss[name] *= 1 - take / len(pool)
                clean[name] *= 1 - EXCEPTION_SHARE * take / len(pool)
        live: int = len(shape.default) + len(shape.custom)
        t.groups += 1
        t.metrics += g.metrics
        t.definitions += live
        t.members += members
        t.scopes += len(g.scopes())
        t.values += sum(len(pools[k]) * (1 - clean[k]) for k in pools)
        t.b_rows += members + (g.metrics - live) + sum(len(pools[k]) * miss[k] for k in pools)
    return t


# ---------------------------------------------------------------- 装载


def load_base(conn: pymysql.Connection, groups: Sequence[Group]) -> tuple[dict[int, list[int]], float]:
    """直接调用 catalog.load_metrics：指标项、C 的扩列表与 D 的定义表来自同一遍生成，一对一表写入 BLACKHOLE 丢弃。"""
    for table in ("metadata_timeseriesscope", "metadata_timeseriesmetric", "x1_timeseriesmetric", "x3_metric_meta"):
        execute(conn, catalog.DDL[table])
    execute(conn, catalog.DDL["x2_metric_meta"] + " ENGINE=BLACKHOLE")
    start: float = time.perf_counter()
    field_ids, _ = catalog.load_metrics(conn, groups)
    execute(conn, "DROP TABLE x2_metric_meta")
    catalog.analyze(
        conn, ["metadata_timeseriesscope", "metadata_timeseriesmetric", "x1_timeseriesmetric", "x3_metric_meta"]
    )
    return field_ids, time.perf_counter() - start


def page_ids_of(groups: Sequence[Group]) -> dict[int, list[int]]:
    """与 catalog.load_metrics 相同的遍历顺序，复原每个数据源的页面分组 ID。"""
    result: dict[int, list[int]] = {}
    page_id: int = 0
    for g in groups:
        ids: list[int] = []
        for _ in catalog.page_names(g.tier.pages):
            page_id += 1
            ids.append(page_id)
        result[g.group_id] = ids
    return result


MetricInfo = tuple[str, str, str, str, str, str, str, str, str, bool]


def metric_info(g: Group, pages: Sequence[int]) -> list[MetricInfo]:
    """(指标名, 原名, 类型, 定义 JSON, 指纹, tag_list, field_config, 页面分组, table_id, 是否旧指标)，取值与 catalog 一致。"""
    info: list[MetricInfo] = []
    for idx in range(g.metrics):
        name, original = catalog.metric_names(idx)
        legacy: bool = catalog.is_legacy(idx)
        meta: str = NULL if legacy else catalog.definition_meta(g.group_id, idx, name, original)
        info.append(
            (
                name,
                original,
                catalog.metric_kind(idx),
                meta,
                NULL if legacy else md5_hex(meta),
                catalog.tag_list(g.group_id, idx),
                catalog.field_config(g.group_id, idx),
                str(pages[catalog.page_of(idx, g.tier.pages)]),
                f"{g.group_id}_bkmonitor_time_series_{500_000 + g.group_id}.{name}",
                legacy,
            )
        )
    return info


def variant_meta(group_id: int, idx: int, name: str, original: str) -> str:
    """例外取值照 meta_layout.py：旧版 SDK 的上报，description、temporality、interval 与定义不同。"""
    meta: dict[str, Any] = json.loads(catalog.definition_meta(group_id, idx, name, original))
    meta.update(description=meta["description"] + " (legacy sdk)", temporality="delta", interval=30)
    return meta_layout.canonical(meta)


@dataclass
class LoadStat:
    members: int = 0
    scopes: int = 0
    values: int = 0
    b_rows: int = 0


def load_reports(
    conn: pymysql.Connection, groups: Sequence[Group], field_ids: dict[int, list[int]], pages: dict[int, list[int]]
) -> LoadStat:
    """成员的随机序列与 catalog.load_members 相同；C、D 共用范围、标签、成员与例外取值，成员 ref_id 等于定义 ID。
    B 的展开行一个成员一行，元信息取定义或例外取值，没有成员的指标保留一行 field_scope = default。"""
    for ddl in (catalog.DDL["report_scope"], catalog.DDL["report_scope_label"], MEMBER_DDL, VALUE_DDL):
        execute(conn, ddl)
    execute(conn, B_BLACKHOLE_DDL if cfg().cross_check or cfg().supplement or cfg().supplement2 else B_DDL)
    scopes: Loader = Loader(conn, "report_scope", catalog.LOAD_COLUMNS["report_scope"])
    labels: Loader = Loader(conn, "report_scope_label", catalog.LOAD_COLUMNS["report_scope_label"])
    values: Loader = Loader(conn, VALUE_TABLE, ["id", "group_id", "fingerprint", "meta"])
    members: catalog.LineLoader = catalog.LineLoader(conn, "report_member", MEMBER_LOAD)
    rows: catalog.LineLoader = catalog.LineLoader(conn, B_TABLE, B_LOAD)
    stat: LoadStat = LoadStat()
    scope_id = label_id = member_id = value_id = b_id = 0
    tail: float = 1 - EXPIRED_SHARE
    for g in groups:
        gid: str = str(g.group_id)
        ids: list[int] = field_ids[g.group_id]
        info: list[MetricInfo] = metric_info(g, pages[g.group_id])
        first_scope: int = scope_id + 1
        raws: list[str] = []
        for service, scope_name in g.scopes():
            scope_id += 1
            scope_labels: dict[str, str] = {"scope_name": scope_name, "service_name": service}
            raws.append(apm_raw_scope(service, scope_name))
            scopes.add(
                [
                    scope_id,
                    g.group_id,
                    "APM",
                    md5_hex(source_key(scope_labels)),
                    raws[-1],
                    json.dumps(scope_labels),
                    FRESH[(scope_id * 2_654_435_761) % STAMPS],
                ]
            )
            for key in ("scope_name", "service_name"):
                label_id += 1
                labels.add([label_id, g.group_id, key, scope_labels[key], scope_id])
        variants: dict[int, tuple[int, str, str]] = {}
        covered: bytearray = bytearray(g.metrics)
        rng: random.Random = random.Random(g.group_id * 7_919 + 3)
        for offset, picked in g.member_lists():
            sid: str = str(first_scope + offset)
            raw: str = raws[offset]
            for idx in picked:
                member_id += 1
                b_id += 1
                seen: float = rng.random()
                extra: float = rng.random()
                expired: bool = seen < EXPIRED_SHARE
                last_seen: str = (
                    EXPIRED[member_id & 255]
                    if expired
                    else FRESH[min(STAMPS - 1, int((seen - EXPIRED_SHARE) / tail * STAMPS))]
                )
                name, original, kind, meta, fp, tags, config, page, table_id, _ = info[idx]
                ref_value: int = 0
                if extra < EXCEPTION_SHARE:
                    if idx not in variants:
                        value_id += 1
                        text: str = variant_meta(g.group_id, idx, name, original)
                        variants[idx] = (value_id, text, md5_hex(text))
                        values.add([value_id, g.group_id, variants[idx][2], text])
                    ref_value, meta, fp = variants[idx]
                override: str = OVERRIDE_JSON if extra > 1 - OVERRIDE_SHARE else NULL
                members.add_line(f"{member_id}\t{gid}\t{sid}\t{ids[idx]}\t{last_seen}\t{ref_value}\t{override}")
                rows.add_line(
                    "\t".join(
                        (
                            str(b_id),
                            gid,
                            page,
                            table_id,
                            raw,
                            name,
                            tags,
                            config if override == NULL else override,
                            CREATE_TIME,
                            last_seen,
                            "",
                            "0" if expired else "1",
                            "0",
                            original,
                            kind,
                            meta,
                            fp,
                            last_seen,
                        )
                    )
                )
                covered[idx] = 1
        for idx in range(g.metrics):
            if covered[idx]:
                continue
            b_id += 1
            name, original, kind, meta, fp, tags, config, page, table_id, legacy = info[idx]
            when: str = catalog.last_modify(g.group_id, idx)
            tail_cols: tuple[str, ...] = (NULL,) * 5 if legacy else (original, kind, meta, fp, when)
            rows.add_line(
                "\t".join(
                    (str(b_id), gid, page, table_id, "default", name, tags, config, CREATE_TIME, when, "", "1", "0")
                )
                + "\t"
                + "\t".join(tail_cols)
            )
        stat.scopes = scope_id
    for loader in (scopes, labels, values, members, rows):
        loader.flush()
    stat.members, stat.values, stat.b_rows = member_id, value_id, b_id
    catalog.analyze(conn, [*SHARED_NEW, B_TABLE])
    return stat


# ---------------------------------------------------------------- 体积


@dataclass(frozen=True)
class Size:
    rows: int
    data: int
    index: int
    ibd: int

    @property
    def both(self) -> int:
        return self.data + self.index

    @property
    def per_row(self) -> float:
        return self.both / max(1, self.rows)


def table_sizes(conn: pymysql.Connection, tables: Sequence[str], database: str = DATABASE) -> dict[str, Size]:
    sizes: dict[str, Size] = {}
    for table in tables:
        rows: int = execute(conn, f"SELECT COUNT(*) FROM {database}.{table}")[0][0]
        data, index = execute(
            conn,
            "SELECT data_length, index_length FROM information_schema.TABLES WHERE table_schema = %s AND table_name = %s",
            (database, table),
        )[0]
        ibd: tuple[Any, ...] = execute(
            conn,
            "SELECT FILE_SIZE FROM information_schema.INNODB_SYS_TABLESPACES WHERE NAME = %s",
            (f"{database}/{table}",),
        )
        sizes[table] = Size(rows, int(data), int(index), int(ibd[0][0]) if ibd else 0)
    return sizes


def index_sizes(conn: pymysql.Connection, table: str) -> dict[str, int]:
    rows: tuple[Any, ...] = execute(
        conn,
        "SELECT index_name, stat_value FROM mysql.innodb_index_stats "
        "WHERE database_name = %s AND table_name = %s AND stat_name = 'size'",
        (DATABASE, table),
    )
    return {name: int(pages) * 16_384 for name, pages in rows}


def report_volume(conn: pymysql.Connection, loaded: Targets, active: Targets, upper: Targets) -> None:
    tables: list[str] = [
        "metadata_timeseriesscope",
        "metadata_timeseriesmetric",
        "x1_timeseriesmetric",
        "x3_metric_meta",
        *SHARED_NEW,
        B_TABLE,
    ]
    sizes: dict[str, Size] = table_sizes(conn, tables)
    emit("## volume: information_schema after ANALYZE (d+i = data + index), ibd = INNODB_SYS_TABLESPACES.FILE_SIZE")
    emit(f"{'table':<28}{'rows':>12}{'data MiB':>11}{'index MiB':>11}{'d+i MiB':>11}{'ibd MiB':>11}{'d+i B/r':>9}")
    for table in tables:
        s: Size = sizes[table]
        emit(
            f"{table:<28}{s.rows:>12,}{mib(s.data):>11}{mib(s.index):>11}{mib(s.both):>11}{mib(s.ibd):>11}"
            f"{s.per_row:>9,.0f}"
        )
    emit()
    emit("## per-index size (MiB, mysql.innodb_index_stats)")
    for table in ("metadata_timeseriesmetric", "x1_timeseriesmetric", "x3_metric_meta", "report_member", B_TABLE):
        emit(f"{table}: " + ", ".join(f"{k} {mib(v)}" for k, v in index_sizes(conn, table).items()))
    emit()
    emit("## extrapolation targets (members exact from member_lists; values and B rows expected)")
    emit(
        f"{'scale':<10}{'groups':>8}{'metrics':>11}{'defs':>10}{'members':>13}{'scopes':>10}{'values':>10}{'B rows':>13}"
    )
    for name, t in (("loaded", loaded), ("active", active), ("upper", upper)):
        emit(
            f"{name:<10}{t.groups:>8,}{t.metrics:>11,}{t.definitions:>10,}{t.members:>13,}{t.scopes:>10,}"
            f"{t.values:>10,.0f}{t.b_rows:>13,.0f}"
        )
    emit()
    base: Size = sizes["metadata_timeseriesmetric"]
    x1_delta: int = sizes["x1_timeseriesmetric"].both - base.both
    x3: int = sizes["x3_metric_meta"].both

    def shared(t: Targets) -> float:
        return (
            sizes["report_member"].per_row * t.members
            + sizes["report_scope"].per_row * t.scopes
            + sizes["report_scope_label"].per_row * t.scopes * 2
            + sizes[VALUE_TABLE].per_row * t.values
        )

    emit("## new volume per scheme, MiB (B replaces the 1,000,000-row TimeSeriesMetric with expanded rows)")
    emit(f"{'scheme':<8}{'active new':>12}{'upper new':>12}{'active total':>14}{'upper total':>13}")
    for name, t in (("active", active), ("upper", upper)):
        b_total: float = sizes[B_TABLE].per_row * t.b_rows
        RESULT.setdefault("volume", {})[name] = {
            "B": b_total - base.both,
            "C": x1_delta + shared(t),
            "D": x3 + shared(t),
            "members": sizes["report_member"].per_row * t.members,
        }
    for scheme in SCHEMES:
        a: float = RESULT["volume"]["active"].get(scheme, 0.0)
        u: float = RESULT["volume"]["upper"].get(scheme, 0.0)
        emit(f"{scheme:<8}{mib(a):>12}{mib(u):>12}{mib(a + base.both):>14}{mib(u + base.both):>13}")
    emit(
        f"per-row d+i: member {sizes['report_member'].per_row:,.0f} B, scope {sizes['report_scope'].per_row:,.0f} B, "
        f"label {sizes['report_scope_label'].per_row:,.0f} B, value {sizes[VALUE_TABLE].per_row:,.0f} B, "
        f"B row {sizes[B_TABLE].per_row:,.0f} B; X1 delta {mib(x1_delta)} MiB, X3 {mib(x3)} MiB, "
        f"TimeSeriesMetric {mib(base.both)} MiB"
    )
    emit()
    RESULT["sizes"] = sizes


# ---------------------------------------------------------------- 读取用例

B_META: str = ", m.original_name, m.metric_type, m.meta"
B_MGMT_WHERE: str = f"group_id = %s AND {explode.NOT_DISABLED}"
B_IDS_SQL: str = (
    f"SELECT ANY_VALUE(scope_id) FROM {B_TABLE} WHERE {B_MGMT_WHERE} GROUP BY field_name ORDER BY field_name "
    f"LIMIT %s, {PAGE}"
)
B_PAGE_SQL: str = (
    f"SELECT {explode.MGMT_COLUMNS}, ANY_VALUE(original_name), ANY_VALUE(metric_type), ANY_VALUE(meta) FROM {B_TABLE} "
    f"WHERE {B_MGMT_WHERE} GROUP BY field_name ORDER BY field_name LIMIT %s, {PAGE}"
)
B_SERVICE_SQL: str = (
    f"SELECT ts.scope_name, m.field_id, m.field_name, m.tag_list, m.field_config{B_META} FROM {B_TABLE} m "
    "LEFT JOIN metadata_timeseriesscope ts ON ts.id = m.scope_id WHERE m.group_id = %s AND m.field_scope IN (%s, %s) "
    "ORDER BY ts.scope_name, m.field_name"
)
B_GROUP_SQL: str = f"SELECT {INFO_COLS}{B_META} FROM {B_TABLE} m WHERE m.group_id = %s AND m.last_modify_time > %s"
B_SCAN_SQL: str = f"SELECT {INFO_COLS}{B_META} FROM {B_TABLE} m WHERE m.field_id > %s ORDER BY m.field_id LIMIT %s"
SCOPE_LOOKUP: str = "SELECT id, scope_name FROM metadata_timeseriesscope WHERE id IN ({marks}) AND group_id = %s"
GROUP_SCOPES: str = (
    "SELECT id, group_id, scope_name, dimension_config, auto_rules, create_from, last_modify_time "
    "FROM metadata_timeseriesscope WHERE group_id = %s"
)


def member_service_sql(v: Variant) -> str:
    """标签倒排 → 上报范围 → 成员 → 指标项与定义 → 例外取值 → 页面分组，与 catalog q3 相同，成员改为例外引用。"""
    return (
        f"SELECT ts.scope_name, m.field_id, m.field_name, m.tag_list, m.field_config{defs(v)}, mv.meta, s.field_config "
        f"FROM {LABEL_TO_MEMBER} {v.member_join} LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id "
        f"LEFT JOIN metadata_timeseriesscope ts ON ts.id = m.scope_id WHERE {SERVICE_LABEL} "
        "ORDER BY ts.scope_name, m.field_name"
    )


@dataclass(frozen=True)
class Pick:
    group_id: int
    service: str

    @property
    def scopes(self) -> tuple[str, str]:
        return apm_raw_scope(self.service, "default"), apm_raw_scope(self.service, "custom")


@dataclass
class Samples:
    xl: list[int]
    large: list[int]
    xl_services: list[Pick]
    hot: list[Pick]
    l_services: list[Pick]


def build_samples(conn: pymysql.Connection, subset: Subset) -> Samples:
    """与 catalog.build_samples 同量：最大数据源 10 个服务加最热服务，大型档 20 个数据源各 5 个服务。"""
    rng: random.Random = random.Random(23)

    def picks(g: Group, count: int) -> list[Pick]:
        chosen: list[Pick] = []
        for j in rng.sample(range(g.tier.services), min(count, g.tier.services)):
            service: str = catalog.service_name(g.group_id, j)
            if execute(conn, f"SELECT 1 FROM {LABEL_TO_MEMBER} WHERE {SERVICE_LABEL} LIMIT 1", (g.group_id, service)):
                chosen.append(Pick(g.group_id, service))
        return chosen

    large: list[Group] = subset.large[:L_SAMPLE_GROUPS]
    return Samples(
        [g.group_id for g in subset.xl],
        [g.group_id for g in large],
        [p for g in subset.xl for p in picks(g, XL_SERVICES)],
        [Pick(g.group_id, catalog.service_name(g.group_id, 0)) for g in subset.xl],
        [p for g in large for p in picks(g, L_SERVICES)],
    )


def b_request_case(groups: Sequence[int], offset: int) -> Case:
    """B 的管理页请求：按指标名去重的计数、本页页面分组、批量取分组名、本页指标，与 catalog q1 的四条语句对应。"""
    count_sql: str = explode.count_sql(B_TABLE)

    def run(cur: Cursor, g: int) -> int:
        fetch(cur, count_sql, (g,))
        scope_ids: list[Any] = sorted({r[0] for r in fetch(cur, B_IDS_SQL, (g, offset)) if r[0] is not None})
        if scope_ids:
            fetch(cur, SCOPE_LOOKUP.replace("{marks}", marks(len(scope_ids))), (*scope_ids, g))
        return len(fetch(cur, B_PAGE_SQL, (g, offset)))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], B_PAGE_SQL, (groups[0], offset))


def statement_case(sql: str, param_sets: Sequence[tuple[Any, ...]]) -> Case:
    return Case([lambda cur, p=p: len(fetch(cur, sql, p)) for p in param_sets], sql, param_sets[0])


def b_group_case(groups: Sequence[int]) -> Case:
    def run(cur: Cursor, g: int) -> int:
        return len(fetch(cur, B_GROUP_SQL, (g, EXPIRE_BEFORE))) + len(fetch(cur, GROUP_SCOPES, (g,)))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], B_GROUP_SQL, (groups[0], EXPIRE_BEFORE))


DEF_COLS: str = "id, field_name, original_name, metric_type, meta"
DEF_BY_NAMES: str = f"SELECT {DEF_COLS} FROM x3_metric_meta WHERE group_id = %s AND field_name IN ({{marks}})"
DEF_BY_GROUP: str = f"SELECT {DEF_COLS} FROM x3_metric_meta WHERE group_id = %s"
DEF_SCAN: str = f"SELECT {DEF_COLS}, group_id FROM x3_metric_meta WHERE id > %s ORDER BY id LIMIT %s"


def d_split_request_case(groups: Sequence[int], offset: int) -> Case:
    """D 的管理页按 PLAN「定义单独查询」：现状的四条语句不变，再按本页指标名读定义，新表缺失时只影响最后一条。"""
    tail: str = f" ORDER BY m.field_name LIMIT {PAGE} OFFSET {offset}"
    count_sql: str = f"SELECT COUNT(*) FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE}"
    ids_sql: str = f"SELECT m.scope_id FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE}{tail}"
    page_sql: str = f"SELECT {PAGE_COLS} FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE}{tail}"

    def run(cur: Cursor, g: int) -> int:
        fetch(cur, count_sql, (g,))
        scope_ids: list[Any] = sorted({r[0] for r in fetch(cur, ids_sql, (g,)) if r[0] is not None})
        if scope_ids:
            fetch(cur, SCOPE_LOOKUP.replace("{marks}", marks(len(scope_ids))), (*scope_ids, g))
        names: list[Any] = [r[2] for r in fetch(cur, page_sql, (g,))]
        if names:
            fetch(cur, DEF_BY_NAMES.replace("{marks}", marks(len(names))), (g, *names))
        return len(names)

    explain_params: tuple[Any, ...] = (groups[0], catalog.metric_names(3)[0])
    return Case([lambda cur, g=g: run(cur, g) for g in groups], DEF_BY_NAMES.replace("{marks}", "%s"), explain_params)


def d_split_group_case(groups: Sequence[int]) -> Case:
    """D 的整组读取按 PLAN「预取定义」：现状的整组读取不变，再按数据源读全部定义，在客户端合并。"""
    base: Case = catalog.q5_case(BASE_VARIANT, groups)

    def run(cur: Cursor, g: int, base_run: catalog.Run) -> int:
        return base_run(cur) + len(fetch(cur, DEF_BY_GROUP, (g,)))

    return Case(
        [lambda cur, g=g, r=r: run(cur, g, r) for g, r in zip(groups, base.runs, strict=True)],
        DEF_BY_GROUP,
        (groups[0],),
    )


def build_cases(
    tier: str, groups: Sequence[int], services: Sequence[Pick], hot: Sequence[Pick]
) -> dict[str, dict[str, Case]]:
    cases: dict[str, dict[str, Case]] = {
        "page1": {
            "A": catalog.q1_case(BASE_VARIANT, groups, 0, "m.field_name", False),
            "B": b_request_case(groups, 0),
            "C": catalog.q1_case(X1, groups, 0, "m.field_name", False),
            "D": catalog.q1_case(X3, groups, 0, "m.field_name", False),
            "D2": d_split_request_case(groups, 0),
        },
        "count": {
            "A": catalog.q1_count_case(BASE_VARIANT, groups),
            "B": statement_case(explode.count_sql(B_TABLE), [(g,) for g in groups]),
            "C": catalog.q1_count_case(X1, groups),
            "D": catalog.q1_count_case(BASE_VARIANT, groups),
        },
    }
    if tier == "xl":
        cases["deep"] = {
            "A": catalog.q1_case(BASE_VARIANT, groups, DEEP_OFFSET, "m.field_name", False),
            "B": b_request_case(groups, DEEP_OFFSET),
            "C": catalog.q1_case(X1, groups, DEEP_OFFSET, "m.field_name", False),
            "D": catalog.q1_case(X3, groups, DEEP_OFFSET, "m.field_name", False),
            "D2": d_split_request_case(groups, DEEP_OFFSET),
        }
        cases["page1_stmt"] = {"B": statement_case(explode.mgmt_sql(B_TABLE, "name"), [(g, 0) for g in groups])}
        cases["deep_stmt"] = {
            "B": statement_case(explode.mgmt_sql(B_TABLE, "name"), [(g, DEEP_OFFSET) for g in groups])
        }
    service_sets: list[tuple[str, Sequence[Pick]]] = [("service", services)] + ([("hot", hot)] if hot else [])
    for name, picks in service_sets:
        cases[name] = {
            "B": statement_case(B_SERVICE_SQL, [(p.group_id, *p.scopes) for p in picks]),
            "C": statement_case(member_service_sql(X1), [(p.group_id, p.service) for p in picks]),
            "D": statement_case(member_service_sql(X3), [(p.group_id, p.service) for p in picks]),
        }
    cases["group"] = {
        "A": catalog.q5_case(BASE_VARIANT, groups),
        "B": b_group_case(groups),
        "C": catalog.q5_case(X1, groups),
        "D": catalog.q5_case(X3, groups),
        "D2": d_split_group_case(groups),
    }
    return cases


HEAVY_B: frozenset[str] = frozenset({"page1", "count", "deep", "page1_stmt", "deep_stmt", "group"})


def budget(tier: str, name: str, scheme: str) -> tuple[int, int]:
    if cfg().smoke:
        return 1, 3
    if scheme == "B" and tier == "xl" and name in HEAVY_B:
        return 1, 5
    if scheme == "B" and name in HEAVY_B:
        return 10, 100
    if scheme == "B" or (tier == "xl" and name in ("group", "hot")):
        return 5, 50
    return 30, 300


def report_reads(
    conn: pymysql.Connection, raw: pymysql.Connection, tier: str, cases: dict[str, dict[str, Case]]
) -> None:
    emit(f"## reads, tier {tier.upper()}: p50/p95/p99 ms over TCP without type conversion (warmup/runs per line)")
    emit(catalog.STAT_HEADER + f"{'runs':>10}")
    plans: list[str] = []
    for name, by_scheme in cases.items():
        for scheme in READ_SCHEMES:
            case: Case | None = by_scheme.get(scheme)
            if case is None or (scheme == "B" and cfg().cross_check):
                continue
            warmup, runs = budget(tier, name, scheme)
            label: str = f"{tier}.{name}.{scheme}"
            log(f"measure {label}")
            stat: Stat = catalog.measure(label, raw, case.runs, seed=f"{tier}.{name}", warmup=warmup, iterations=runs)
            emit(stat.line() + f"{warmup:>4}/{runs:<5}")
            record(f"{tier}.{name}", scheme, statistics.median(stat.samples))
            plans.append(f"{label}: {catalog.explain(conn, case.sql, case.params)}")
    emit()
    emit("## EXPLAIN (table:key/type~rows[flags]; main statement of each case)")
    for plan in plans:
        emit(plan)
    emit()


def report_counters(conn: pymysql.Connection, xl: int) -> None:
    """单次执行的会话计数：5.7 内部临时表含 BLOB/TEXT 列时直接落盘。"""
    emit("## session counters of one execution on the largest group (FLUSH STATUS; SHOW SESSION STATUS)")
    emit(f"{'statement':<34}{'handler rd':>12}{'sort rows':>11}{'tmp tbl':>9}{'tmp disk':>10}{'ms':>10}")
    items: list[tuple[str, str, tuple[Any, ...]]] = [
        ("B page (explode, no meta)", explode.mgmt_sql(B_TABLE, "name"), (xl, 0)),
        ("B page with meta", B_PAGE_SQL, (xl, 0)),
        (
            "B page without TEXT/JSON",
            f"SELECT field_name, MIN(field_id), COUNT(*), ANY_VALUE(scope_id), MIN(create_time), MAX(last_modify_time) "
            f"FROM {B_TABLE} WHERE {B_MGMT_WHERE} GROUP BY field_name ORDER BY field_name LIMIT %s, {PAGE}",
            (xl, 0),
        ),
        ("B ids", B_IDS_SQL, (xl, 0)),
        ("B count distinct", explode.count_sql(B_TABLE), (xl,)),
        ("C page", catalog.q1_case(X1, [xl], 0, "m.field_name", False).sql, (xl,)),
        ("D page", catalog.q1_case(X3, [xl], 0, "m.field_name", False).sql, (xl,)),
        ("D deep", catalog.q1_case(X3, [xl], DEEP_OFFSET, "m.field_name", False).sql, (xl,)),
        ("C/D count", catalog.q1_count_case(X1, [xl]).sql, (xl,)),
    ]
    for label, sql, params in items:
        start: float = time.perf_counter()
        counters: dict[str, int] = cmp.session_counters(conn, sql, params)
        elapsed: float = (time.perf_counter() - start) * 1000
        emit(
            f"{label:<34}{counters['handler_reads']:>12,}{counters['sort_rows']:>11,}{counters['tmp_tables']:>9}"
            f"{counters['tmp_disk_tables']:>10}{elapsed:>10.1f}"
        )
        RESULT.setdefault("counters", {})[label] = counters
    emit()


# ---------------------------------------------------------------- 全平台扫描


def report_scan(
    conn: pymysql.Connection, raw: pymysql.Connection, b_rows: int, active: Targets, upper: Targets
) -> None:
    emit(
        f"## full scan with metadata, field_id keyset LIMIT {SCAN_CHUNK:,}; A/C/D read 1,000,000 metric items "
        f"({SCAN_REPEATS} passes, median), B reads its loaded expanded rows and extrapolates by rows"
    )
    emit(
        f"{'case':<10}{'total s':>10}{'rows':>12}{'chunks':>8}{'chunk p50':>11}{'chunk p95':>11}{'active s':>10}{'upper s':>10}"
    )
    plans: list[str] = []
    for scheme in READ_SCHEMES:
        repeats: int = 1 if cfg().smoke else SCAN_REPEATS
        if scheme == "B" and cfg().cross_check:
            continue
        if scheme == "B":
            sqls: list[str] = [B_SCAN_SQL]
            repeats = 1
        elif scheme == "D2":
            sqls = [
                f"SELECT {INFO_COLS} FROM {BASE_VARIANT.source} WHERE m.field_id > %s ORDER BY m.field_id LIMIT %s",
                DEF_SCAN,
            ]
        else:
            v: Variant = VARIANT_OF[scheme]
            sqls = [f"SELECT {INFO_COLS}{defs(v)} FROM {v.source} WHERE m.field_id > %s ORDER BY m.field_id LIMIT %s"]
        log(f"scan {scheme}")
        totals: list[float] = []
        chunks: list[float] = []
        rows: int = 0
        with raw.cursor() as cur:
            for _ in range(repeats):
                start: float = time.perf_counter()
                chunks, rows = [], 0
                for sql in sqls:
                    part_chunks, part_rows = catalog.scan_by_keys(cur, sql, SCAN_CHUNK)
                    chunks += part_chunks
                    rows += part_rows
                totals.append(time.perf_counter() - start)
        total: float = statistics.median(totals)
        if scheme == "B":
            per_row: float = total / max(1, rows)
            act, up = per_row * active.b_rows, per_row * upper.b_rows
        else:
            act = up = total
        record("scan", scheme, act)
        record("scan.upper", scheme, up)
        emit(
            f"{scheme:<10}{total:>10.2f}{rows:>12,}{len(chunks):>8}{catalog.percentile(chunks, 0.5):>11.2f}"
            f"{catalog.percentile(chunks, 0.95):>11.2f}{act:>10.1f}{up:>10.1f}"
        )
        plans.append(f"{scheme}: " + " + ".join(catalog.explain(conn, sql, (0, SCAN_CHUNK)) for sql in sqls))
    emit(f"B extrapolation: loaded {b_rows:,} rows, active {active.b_rows:,.0f}, upper {upper.b_rows:,.0f}")
    emit("D2 = metric items keyset (same as A) + definitions keyset on x3_metric_meta.id, merged on the client")
    for plan in plans:
        emit(plan)
    emit()


# ---------------------------------------------------------------- bmw Apply


@dataclass(frozen=True)
class MemberReport:
    group_id: int
    scope_hash: str
    field_name: str
    fingerprint: str
    meta: str | None


MEMBER_PLAN_READ: str = (
    "SELECT s.report_scope_id, s.ref_id, s.last_seen, s.meta_value_id, mv.fingerprint FROM report_member s "
    f"LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id WHERE (s.group_id, s.report_scope_id, s.ref_id) IN ({{tuples}})"
)
VALUE_LOCK: str = (
    f"SELECT id, group_id, fingerprint FROM {VALUE_TABLE} WHERE (group_id, fingerprint) IN ({{tuples}}) FOR UPDATE"
)


def changed_meta(rng: random.Random) -> str:
    return json.dumps(
        {"unit": "ms", "description": f"changed {rng.random():.12f}", "temporality": "delta", "interval": 30}
    )


CURRENT_FINGERPRINT: dict[str, str] = {
    "x1": "SELECT field_id, meta_fingerprint FROM x1_timeseriesmetric WHERE field_id IN ({marks})",
    "x3": "SELECT id, fingerprint FROM x3_metric_meta WHERE id IN ({marks})",
}


def build_member_batch(
    conn: pymysql.Connection,
    variant: str,
    parts: Sequence[tuple[int, int, int]],
    index: dict[int, GroupIndex],
    rng: random.Random,
    taken: set[tuple[int, int, int]],
) -> list[MemberReport]:
    """与 catalog.build_batch 相同的抽样，已有例外的成员重报自己的例外取值，新成员跨批次不重复。
    沿用定义的成员上报当前定义的指纹：catalog 写法会改写定义，不能用装载时的索引。"""
    pairs: list[tuple[int, int, int, str | None]] = []
    for g, count, fresh in parts:
        gi: GroupIndex = index[g]
        ids: list[int] = rng.sample(range(gi.first_member, gi.last_member + 1), count - fresh)
        rows: tuple[Any, ...] = execute(
            conn,
            f"SELECT s.report_scope_id, s.ref_id, mv.fingerprint FROM report_member s LEFT JOIN {VALUE_TABLE} mv "
            f"ON mv.id = s.meta_value_id WHERE s.group_id = %s AND s.id IN ({marks(len(ids))})",
            (g, *ids),
        )
        pairs.extend((g, sid, ref, fp) for sid, ref, fp in rows)
        scope_ids: list[int] = list(gi.scopes)
        meta_ids: list[int] = list(gi.metas)
        added: int = 0
        while added < fresh:
            key: tuple[int, int, int] = (g, rng.choice(scope_ids), rng.choice(meta_ids))
            if key in taken or execute(
                conn, "SELECT 1 FROM report_member WHERE group_id = %s AND report_scope_id = %s AND ref_id = %s", key
            ):
                continue
            taken.add(key)
            pairs.append((*key, None))
            added += 1
    refs: list[int] = sorted({ref for _, _, ref, _ in pairs})
    current: dict[int, str] = dict(
        execute(conn, CURRENT_FINGERPRINT[variant].replace("{marks}", marks(len(refs))), refs)
    )
    reports: list[MemberReport] = [
        MemberReport(g, index[g].scopes[sid], index[g].metas[ref][0], fp or current[ref], None)
        for g, sid, ref, fp in pairs
    ]
    for i in rng.sample(range(len(reports)), APPLY_CHANGED):
        meta: str = changed_meta(rng)
        reports[i] = replace(reports[i], fingerprint=md5_hex(meta), meta=meta)
    return reports


def apply_plan(cur: Cursor, variant: str, batch: Sequence[MemberReport]) -> tuple[int, int]:
    """PLAN 的 Apply：带范围的上报指纹与定义不同时记例外，按指纹取得或新建例外取值（FOR UPDATE），一批一个事务。"""
    scope_keys: list[tuple[int, str]] = sorted({(r.group_id, r.scope_hash) for r in batch})
    scope_rows: tuple[Any, ...] = fetch(
        cur, catalog.apply_sql(catalog.SCOPE_READ, "(%s, %s)", len(scope_keys)), [v for k in scope_keys for v in k]
    )
    scope_of: dict[tuple[int, str], tuple[str, str]] = {(int(r[1]), r[2]): (r[0], r[3]) for r in scope_rows}
    name_keys: list[tuple[int, str]] = sorted({(r.group_id, r.field_name) for r in batch})
    template, tuple_marks = catalog.DEF_READ[variant]
    def_rows: tuple[Any, ...] = fetch(
        cur, catalog.apply_sql(template, tuple_marks, len(name_keys)), [v for k in name_keys for v in k]
    )
    def_of: dict[tuple[int, str], tuple[str, str | None, str | None]] = {
        (int(r[1]), r[2]): (r[0], r[3], r[4]) for r in def_rows
    }
    member_keys: dict[tuple[int, str, str], MemberReport] = {}
    for r in batch:
        member_keys[(r.group_id, scope_of[(r.group_id, r.scope_hash)][0], def_of[(r.group_id, r.field_name)][0])] = r
    member_rows: tuple[Any, ...] = fetch(
        cur, catalog.apply_sql(MEMBER_PLAN_READ, "(%s, %s, %s)", len(member_keys)), [v for k in member_keys for v in k]
    )
    seen: dict[tuple[str, str], tuple[str, str, str | None]] = {(r[0], r[1]): (r[2], r[3], r[4]) for r in member_rows}
    stale_scopes: list[str] = sorted({sid for sid, last in scope_of.values() if last < STALE_BEFORE})
    stale_defs: list[str] = sorted(
        {ref for ref, _, last in def_of.values() if last is not None and last < STALE_BEFORE}
    )
    writes: list[tuple[int, str, str, str | None, str]] = []
    wanted: dict[tuple[int, str], str] = {}
    for (g, sid, ref), r in member_keys.items():
        want: str | None = None if r.fingerprint == def_of[(g, r.field_name)][1] else r.fingerprint
        current: tuple[str, str, str | None] | None = seen.get((sid, ref))
        have: str | None = current[2] if current else None
        if current is not None and want == have and current[0] >= STALE_BEFORE:
            continue
        keep: str = current[1] if current is not None and want == have else "0"
        writes.append((g, sid, ref, want if want != have else None, keep))
        if want is not None and want != have and r.meta is not None:
            wanted[(g, want)] = r.meta
    statements: int = 3
    cur.execute("BEGIN")
    if stale_scopes:
        cur.execute(
            f"UPDATE report_scope SET last_seen = %s WHERE id IN ({marks(len(stale_scopes))})", (NOW, *stale_scopes)
        )
        statements += 1
    ids: dict[tuple[int, str], str] = {}
    if wanted:
        lock_sql: str = catalog.apply_sql(VALUE_LOCK, "(%s, %s)", len(wanted))
        ids = {(int(r[1]), r[2]): r[0] for r in fetch(cur, lock_sql, [v for k in wanted for v in k])}
        statements += 1
        missing: list[tuple[int, str]] = [k for k in wanted if k not in ids]
        if missing:
            cur.execute(
                f"INSERT INTO {VALUE_TABLE} (group_id, fingerprint, meta) VALUES "
                + ", ".join(["(%s, %s, %s)"] * len(missing)),
                [v for g, fp in missing for v in (g, fp, wanted[(g, fp)])],
            )
            again: str = catalog.apply_sql(VALUE_LOCK, "(%s, %s)", len(missing))
            ids.update({(int(r[1]), r[2]): r[0] for r in fetch(cur, again, [v for k in missing for v in k])})
            statements += 2
    if stale_defs:
        cur.execute(catalog.DEF_REFRESH[variant].replace("{marks}", marks(len(stale_defs))), (NOW, *stale_defs))
        statements += 1
    if writes:
        cur.execute(
            "INSERT INTO report_member (group_id, report_scope_id, ref_id, last_seen, meta_value_id) VALUES "
            + ", ".join(["(%s, %s, %s, %s, %s)"] * len(writes))
            + " ON DUPLICATE KEY UPDATE last_seen = VALUES(last_seen), meta_value_id = VALUES(meta_value_id)",
            [
                v
                for g, sid, ref, new, keep in writes
                for v in (g, sid, ref, NOW, ids.get((g, new), keep) if new else keep)
            ],
        )
        statements += 1
    cur.execute("COMMIT")
    return statements, len(stale_scopes) + len(wanted) + len(stale_defs) + len(writes)


@dataclass(frozen=True)
class RowReport:
    group_id: int
    field_scope: str
    field_name: str
    fingerprint: str
    meta: str | None
    row: tuple[Any, ...] | None


@dataclass
class BIndex:
    first: int
    last: int
    raws: list[str]
    info: list[MetricInfo]
    live: list[int]


def b_index(conn: pymysql.Connection, g: Group, pages: Sequence[int]) -> BIndex:
    first, last = execute(
        conn, f"SELECT MIN(field_id), MAX(field_id) FROM {B_TABLE} WHERE group_id = %s", (g.group_id,)
    )[0]
    info: list[MetricInfo] = metric_info(g, pages)
    return BIndex(
        first,
        last,
        [apm_raw_scope(service, scope_name) for service, scope_name in g.scopes()],
        info,
        [idx for idx, item in enumerate(info) if not item[9]],
    )


def build_b_batch(
    conn: pymysql.Connection,
    parts: Sequence[tuple[int, int, int]],
    index: dict[int, BIndex],
    rng: random.Random,
    taken: set[tuple[int, str, str]],
) -> list[RowReport]:
    """已有行按主键随机抽取（只取带元信息的行），新行取不存在的「范围 × 指标」组合，跨批次不重复。"""
    reports: list[RowReport] = []
    for g, count, fresh in parts:
        bi: BIndex = index[g]
        got: list[tuple[Any, ...]] = []
        while len(got) < count - fresh:
            ids: list[int] = rng.sample(range(bi.first, bi.last + 1), count - fresh - len(got))
            got.extend(
                execute(
                    conn,
                    f"SELECT field_scope, field_name, meta_fingerprint FROM {B_TABLE} WHERE group_id = %s "
                    f"AND field_id IN ({marks(len(ids))}) AND meta_fingerprint IS NOT NULL",
                    (g, *ids),
                )
            )
        reports.extend(RowReport(g, scope, name, fp, None, None) for scope, name, fp in got[: count - fresh])
        added: int = 0
        while added < fresh:
            raw: str = rng.choice(bi.raws)
            name, original, kind, meta, fp, tags, config, page, table_id, _ = bi.info[rng.choice(bi.live)]
            key: tuple[int, str, str] = (g, raw, name)
            if key in taken or execute(
                conn, f"SELECT 1 FROM {B_TABLE} WHERE group_id = %s AND field_scope = %s AND field_name = %s", key
            ):
                continue
            taken.add(key)
            row: tuple[Any, ...] = (
                g,
                page,
                table_id,
                raw,
                name,
                tags,
                config,
                CREATE_TIME,
                NOW,
                "",
                1,
                0,
                original,
                kind,
                meta,
                fp,
                NOW,
            )
            reports.append(RowReport(g, raw, name, fp, None, row))
            added += 1
    for i in rng.sample(range(len(reports)), APPLY_CHANGED):
        meta: str = changed_meta(rng)
        reports[i] = replace(reports[i], fingerprint=md5_hex(meta), meta=meta)
    return reports


def apply_b(cur: Cursor, batch: Sequence[RowReport]) -> tuple[int, int]:
    """B 的 Apply：按 (group_id, field_scope, field_name) 读展开行，一批一个事务插入新行、逐行改元信息、批量刷新到期行。"""
    keys: list[tuple[int, str, str]] = sorted({(r.group_id, r.field_scope, r.field_name) for r in batch})
    rows: tuple[Any, ...] = fetch(
        cur,
        f"SELECT field_id, group_id, field_scope, field_name, meta_fingerprint, last_modify_time FROM {B_TABLE} "
        f"WHERE (group_id, field_scope, field_name) IN ({', '.join(['(%s, %s, %s)'] * len(keys))})",
        [v for k in keys for v in k],
    )
    existing: dict[tuple[int, str, str], tuple[str, str | None, str]] = {
        (int(r[1]), r[2], r[3]): (r[0], r[4], r[5]) for r in rows
    }
    inserts: list[tuple[Any, ...]] = [
        r.row for r in batch if r.row is not None and (r.group_id, r.field_scope, r.field_name) not in existing
    ]
    changed: list[tuple[str, RowReport]] = []
    for r in batch:
        hit: tuple[str, str | None, str] | None = existing.get((r.group_id, r.field_scope, r.field_name))
        if r.meta is not None and hit is not None and hit[1] != r.fingerprint:
            changed.append((hit[0], r))
    changed_ids: set[str] = {fid for fid, _ in changed}
    stale: list[str] = sorted(
        {fid for fid, _, last in existing.values() if last < STALE_BEFORE and fid not in changed_ids}
    )
    statements: int = 1
    cur.execute("BEGIN")
    if inserts:
        cur.execute(
            f"INSERT INTO {B_TABLE} ({', '.join(B_INSERT)}) VALUES "
            + ", ".join([f"({marks(len(B_INSERT))})"] * len(inserts)),
            [v for row in inserts for v in row],
        )
        statements += 1
    for fid, r in changed:
        cur.execute(
            f"UPDATE {B_TABLE} SET metric_type = %s, meta = %s, meta_fingerprint = %s, meta_seen_at = %s, "
            "last_modify_time = %s WHERE field_id = %s",
            (CHANGED_TYPE, r.meta, r.fingerprint, NOW, NOW, fid),
        )
        statements += 1
    if stale:
        cur.execute(
            f"UPDATE {B_TABLE} SET last_modify_time = %s, meta_seen_at = %s WHERE field_id IN ({marks(len(stale))})",
            (NOW, NOW, *stale),
        )
        statements += 1
    cur.execute("COMMIT")
    return statements, len(inserts) + len(changed) + len(stale)


def time_batches(
    raw: pymysql.Connection, batches: Sequence[Any], fn: Callable[[Cursor, Any], tuple[int, int]], warmup: int
) -> tuple[list[float], list[int], list[int]]:
    samples: list[float] = []
    statements: list[int] = []
    written: list[int] = []
    with raw.cursor() as cur:
        for i, batch in enumerate(batches):
            start: float = time.perf_counter()
            stmts, rows = fn(cur, batch)
            elapsed: float = (time.perf_counter() - start) * 1000
            if i >= warmup:
                samples.append(elapsed)
                statements.append(stmts)
                written.append(rows)
    return samples, statements, written


def report_apply(
    conn: pymysql.Connection, raw: pymysql.Connection, subset: Subset, pages: dict[int, list[int]]
) -> None:
    warmup, runs = (3, 20) if cfg().smoke else (catalog.WARMUP, catalog.ITERATIONS)
    xl: list[int] = [g.group_id for g in subset.xl]
    mixed_groups: list[Group] = subset.large[:MIXED_GROUPS]
    large: list[int] = [g.group_id for g in mixed_groups]
    emit(
        f"## bmw Apply: {APPLY_BATCH} reports per batch ({APPLY_NEW} new, {APPLY_CHANGED} changed, ~10% due for refresh), "
        f"one transaction per batch, {runs} batches after {warmup} warmup"
    )
    emit("catalog = catalog.apply unchanged (changed reports overwrite definitions, same SQL as REPORT 9.2)")
    emit("plan = PLAN Apply (changed scoped reports become exceptions referencing deduplicated values)")
    emit(f"{'case':<22}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'stmts':>8}{'written':>9}{'reports/s@p50':>15}")
    index: dict[int, GroupIndex] = {g: catalog.group_index(conn, g) for g in [*xl, *large]}
    b_idx: dict[int, BIndex] = {g.group_id: b_index(conn, g, pages[g.group_id]) for g in [*subset.xl, *mixed_groups]}

    def parts_of(shape: str, rng: random.Random) -> list[tuple[int, int, int]]:
        if shape == "xl":
            return [(rng.choice(xl), APPLY_BATCH, APPLY_NEW)]
        chosen: list[int] = rng.sample(large, min(MIXED_GROUPS, len(large)))
        per: int = APPLY_BATCH // len(chosen)
        return [(g, per, 1 if i < APPLY_NEW else 0) for i, g in enumerate(chosen)]

    plans: list[str] = []
    total: int = warmup + runs
    for shape in ("xl", "mixed"):
        jobs: list[tuple[str, str, Callable[[], list[Any]], Callable[[Cursor, Any], tuple[int, int]]]] = []
        for scheme, variant in (("C", "x1"), ("D", "x3")):
            rng_c: random.Random = random.Random(f"{shape}.{variant}")
            jobs.append(
                (
                    f"{shape}.catalog.{scheme}",
                    f"apply.{shape}.catalog",
                    lambda rng=rng_c, shape=shape: [
                        catalog.build_batch(conn, parts_of(shape, rng), index, rng) for _ in range(total)
                    ],
                    lambda cur, batch, variant=variant: catalog.apply(cur, variant, batch),
                )
            )
        for scheme, variant in (("C", "x1"), ("D", "x3")):
            rng_p: random.Random = random.Random(f"{shape}.plan")
            taken: set[tuple[int, int, int]] = set()
            jobs.append(
                (
                    f"{shape}.plan.{scheme}",
                    f"apply.{shape}.plan",
                    lambda rng=rng_p, taken=taken, shape=shape, variant=variant: [
                        build_member_batch(conn, variant, parts_of(shape, rng), index, rng, taken) for _ in range(total)
                    ],
                    lambda cur, batch, variant=variant: apply_plan(cur, variant, batch),
                )
            )
        rng_b: random.Random = random.Random(f"{shape}.b")
        b_taken: set[tuple[int, str, str]] = set()
        jobs.append(
            (
                f"{shape}.B",
                f"apply.{shape}.plan",
                lambda rng=rng_b, taken=b_taken, shape=shape: [
                    build_b_batch(conn, parts_of(shape, rng), b_idx, rng, taken) for _ in range(total)
                ],
                apply_b,
            )
        )
        for label, key, build, fn in jobs:
            log(f"apply {label}")
            batches: list[Any] = build()
            samples, statements, written = time_batches(raw, batches, fn, warmup)
            p50: float = statistics.median(samples)
            record(key, label.rsplit(".", 1)[1], p50)
            emit(
                f"{label:<22}{p50:>10.3f}{catalog.percentile(samples, 0.95):>10.3f}{catalog.percentile(samples, 0.99):>10.3f}"
                f"{statistics.mean(statements):>8.1f}{statistics.mean(written):>9.1f}{APPLY_BATCH / p50 * 1000:>15,.0f}"
            )
        last: list[catalog.Report] = catalog.build_batch(
            conn, parts_of(shape, random.Random("explain")), index, random.Random(1)
        )
        for variant in ("x1", "x3"):
            for name, (sql, params) in zip(("scope", "definition"), catalog.apply_reads(last, variant), strict=True):
                plans.append(f"{shape}.{variant}.{name}: {catalog.explain(conn, sql, params)}")
    emit()
    emit("## EXPLAIN Apply reads")
    for plan in plans:
        emit(plan)
    emit()


def report_refresh(conn: pymysql.Connection, raw: pymysql.Connection, xl: int) -> None:
    """B 的每日刷新沿用 bmw 逐行 UPDATE（自动提交），抽样计时后乘以最大数据源的活跃行数；C、D 按 Apply 每千条换算。"""
    first, last = execute(conn, f"SELECT MIN(field_id), MAX(field_id) FROM {B_TABLE} WHERE group_id = %s", (xl,))[0]
    sample: int = 200 if cfg().smoke else REFRESH_SAMPLE
    ids: list[int] = random.Random("refresh").sample(range(first, last + 1), min(sample, last - first + 1))
    rows: tuple[Any, ...] = execute(
        conn,
        f"SELECT field_id, tag_list, scope_id FROM {B_TABLE} WHERE field_id IN ({marks(len(ids))}) AND is_active = 1",
        ids,
    )
    times: list[float] = []
    with raw.cursor() as cur:
        for field_id, tags, scope_id in rows:
            start: float = time.perf_counter()
            cur.execute(
                f"UPDATE {B_TABLE} SET tag_list = %s, last_modify_time = %s, scope_id = %s WHERE field_id = %s",
                (tags, NOW, scope_id, field_id),
            )
            times.append((time.perf_counter() - start) * 1_000_000)
    active: int = execute(conn, f"SELECT COUNT(*) FROM {B_TABLE} WHERE group_id = %s AND is_active = 1", (xl,))[0][0]
    members: int = execute(conn, "SELECT COUNT(*) FROM report_member WHERE group_id = %s", (xl,))[0][0]
    select_ms: float = RESULT["p50"].get("xl.group", {}).get("B", 0.0)
    b_total: float = (active * statistics.mean(times) / 1_000_000) + select_ms / 1000
    emit("## daily refresh of the largest group, seconds")
    emit(
        f"B: per-row UPDATE mean {statistics.mean(times):,.0f} us, p50 {statistics.median(times):,.0f} us "
        f"({len(times):,} sampled), {active:,} active rows, group read {select_ms:,.0f} ms -> {b_total:,.1f} s"
    )
    record("refresh", "B", b_total)
    for scheme in ("C", "D"):
        p50: float = RESULT["p50"].get("apply.xl.plan", {}).get(scheme, 0.0)
        record("refresh", scheme, p50 * members / APPLY_BATCH / 1000)
        emit(
            f"{scheme}: Apply p50 {p50:.2f} ms per {APPLY_BATCH:,} x {members:,} members -> {p50 * members / APPLY_BATCH / 1000:,.1f} s"
        )
    emit()


# ---------------------------------------------------------------- DDL 与元数据锁


@dataclass
class DdlCase:
    key: str
    title: str
    statements: list[str]
    blocker_hold: float = 0.0
    lock_wait_timeout: int = 0


class Blocker(threading.Thread):
    """开启事务读一行后保持不提交，持有共享元数据锁，与 compat.Blocker 相同但可指定表。"""

    def __init__(self, hold: float, table: str) -> None:
        super().__init__(daemon=True)
        self.hold = hold
        self.table = table

    def run(self) -> None:
        conn: pymysql.Connection = connect(autocommit=False)
        execute(conn, "BEGIN")
        execute(conn, f"SELECT field_id FROM {self.table} ORDER BY field_id LIMIT 1")
        time.sleep(self.hold)
        execute(conn, "COMMIT")
        conn.close()


Workloads = list[tuple[str, str, Callable[[random.Random], Sequence[Any]]]]


def run_ddl_case(case: DdlCase, table: str, workloads: Workloads) -> dict[str, Any]:
    """与 compat.run_alter_case 相同的采样：基线 3 s 后执行语句，并发读写与元数据锁监控贯穿始终。"""
    admin: pymysql.Connection = connect()
    before: dict[str, Any] = cmp.innodb_table_info(admin, table)
    alter_conn: pymysql.Connection = connect()
    alter_id: int = int(execute(alter_conn, "SELECT CONNECTION_ID()")[0][0])
    if case.lock_wait_timeout:
        execute(alter_conn, f"SET SESSION lock_wait_timeout = {case.lock_wait_timeout}")
    threads: list[cmp.Workload] = [cmp.Workload(SERVER, label, sql, params) for label, sql, params in workloads]
    monitor: cmp.MdlMonitor = cmp.MdlMonitor(SERVER, alter_id, table)
    for worker in [*threads, monitor]:
        worker.start()
    time.sleep(1.0 if cfg().smoke else BASELINE_SECONDS)
    blocker: Blocker | None = None
    if case.blocker_hold:
        blocker = Blocker(case.blocker_hold, table)
        blocker.start()
        time.sleep(0.3)
    started: float = time.perf_counter()
    outcomes: list[cmp.Outcome] = []
    for statement in case.statements:
        outcomes.append(cmp.attempt(alter_conn, statement))
        if not outcomes[-1].ok:
            break
    finished: float = time.perf_counter()
    time.sleep(1.0)
    for worker in [*threads, monitor]:
        worker.stop_event.set()
        worker.join()
    if blocker is not None:
        blocker.join()
    after: dict[str, Any] = cmp.innodb_table_info(admin, table)
    admin.close()
    alter_conn.close()
    window: list[cmp.MonitorSample] = [m for m in monitor.samples if started <= m.at <= finished + 0.05]
    result: dict[str, Any] = {
        "key": case.key,
        "title": case.title,
        "elapsed_s": finished - started,
        "outcomes": outcomes,
        "rebuilt": bool(before) and before.get("TABLE_ID") != after.get("TABLE_ID"),
        "mdl_wait_samples": sum(1 for m in window if m.waiting),
        "mdl_wait_max": max((m.waiting for m in window), default=0),
        "stages": cmp.unique_in_order([s for m in window for s in m.stages]),
        "workloads": {w.label: cmp.latency_summary(w.samples, started, finished) for w in threads},
    }
    errors: list[str] = [f"ERROR {o.code}" for o in outcomes if not o.ok]
    emit(f"[{case.key}] {case.title}")
    emit(
        f"  {len(outcomes)}/{len(case.statements)} statements, {result['elapsed_s']:.2f} s"
        f"{' (' + ', '.join(errors) + ')' if errors else ''}; per statement "
        + ", ".join(f"{o.elapsed_ms / 1000:.2f} s" for o in outcomes)
    )
    emit(
        f"  rebuilt: {'yes' if result['rebuilt'] else 'no'} (TABLE_ID {before.get('TABLE_ID')} -> {after.get('TABLE_ID')}); "
        f"stages: {' -> '.join(result['stages']) or 'none'}; MDL wait samples {result['mdl_wait_samples']} "
        f"(max {result['mdl_wait_max']} sessions)"
    )
    for label, stats in result["workloads"].items():
        emit(
            f"  {label}: n={stats['n']} p50={stats['p50']} ms p99={stats['p99']} ms max={stats['max']} ms "
            f"(at +{stats['max_at_s']} s) >100ms={stats['over_100ms']} >500ms={stats['over_500ms']} "
            f"errors={stats['errors'] or 'none'}; baseline p50={stats['baseline_p50']} ms max={stats['baseline_max']} ms"
        )
    RESULT.setdefault("ddl", {})[case.key] = result
    return result


def metric_workloads(table: str, group_ids: Sequence[int], max_id: int) -> Workloads:
    """管理页读（MANAGE_WHERE 首页，随机数据源）与指标同步写（bmw 逐行 UPDATE last_modify_time）。"""
    page: str = f"SELECT {PAGE_COLS} FROM {table} m WHERE {MANAGE_WHERE} ORDER BY m.field_name LIMIT {PAGE}"
    return [
        ("管理页读", page, lambda rng: (rng.choice(group_ids),)),
        (
            "指标同步写",
            f"UPDATE {table} SET last_modify_time = NOW(6) WHERE field_id = %s",
            lambda rng: (rng.randint(1, max_id),),
        ),
    ]


def report_ddl(conn: pymysql.Connection, groups: Sequence[Group]) -> None:
    rows: int = execute(conn, "SELECT COUNT(*) FROM metadata_timeseriesmetric")[0][0]
    max_id: int = execute(conn, "SELECT MAX(field_id) FROM metadata_timeseriesmetric")[0][0]
    emit(f"## DDL on ddl_metric, a copy of metadata_timeseriesmetric ({rows:,} rows), with concurrent reads and writes")
    execute(conn, "DROP TABLE IF EXISTS ddl_metric")
    execute(conn, "CREATE TABLE ddl_metric LIKE metadata_timeseriesmetric")
    start: float = time.perf_counter()
    execute(conn, "INSERT INTO ddl_metric SELECT * FROM metadata_timeseriesmetric")
    copy_s: float = time.perf_counter() - start
    catalog.analyze(conn, ["ddl_metric"])
    emit(
        f"copy {copy_s:.1f} s, tablespace {cmp.tablespace_mib(conn, 'ddl_metric')} MiB; "
        f"workloads loop every {cmp.WORKLOAD_INTERVAL * 1000:.0f} ms"
    )
    group_ids: list[int] = [g.group_id for g in groups]
    workloads: Workloads = metric_workloads("ddl_metric", group_ids, max_id)
    t: str = "ALTER TABLE ddl_metric"
    add_each: list[str] = [f"{t} ADD COLUMN `{name}` {kind} NULL" for name, kind in X1_NEW_COLUMNS]
    drop_each: list[str] = [f"{t} DROP COLUMN `{name}`" for name, _ in X1_NEW_COLUMNS]
    creates: list[str] = [ddl.replace(name, f"ddl_{name}", 1) for name, ddl in NEW_TABLES.items()]
    drops: list[str] = [f"DROP TABLE ddl_{name}" for name in NEW_TABLES]
    cases: list[DdlCase] = [
        DdlCase("add5", "B、C 加 5 列：一条 ALTER，不写 ALGORITHM", [f"{t} {cmp.X1_COLUMNS}"]),
        DdlCase("drop5", "B、C 回退：一条 ALTER 删 5 列", [f"{t} {cmp.X1_DROP_COLUMNS}"]),
        DdlCase("add5_django", "B、C 加 5 列：Django 每个 AddField 一条 ALTER", add_each),
        DdlCase("drop5_django", "B、C 回退：Django 每个 RemoveField 一条 ALTER", drop_each),
        DdlCase("create5", "D 建五张新表", creates),
        DdlCase("dropnew5", "D 回退：删五张空表", drops),
        DdlCase(
            "mdl_add5", "3 s 长事务期间加 5 列，lock_wait_timeout 默认", [f"{t} {cmp.X1_COLUMNS}"], blocker_hold=3.0
        ),
    ]
    for case in cases:
        log(f"ddl {case.key}")
        run_ddl_case(case, "ddl_metric", workloads)
    log("ddl cleanup mdl_add5")
    execute(conn, f"{t} {cmp.X1_DROP_COLUMNS}")
    for case in (
        DdlCase(
            "mdl_add5_lwt1",
            "3 s 长事务期间加 5 列，ALTER 会话 lock_wait_timeout=1",
            [f"{t} {cmp.X1_COLUMNS}"],
            blocker_hold=3.0,
            lock_wait_timeout=1,
        ),
        DdlCase("mdl_create5", "3 s 长事务期间 D 建五张新表", creates, blocker_hold=3.0),
    ):
        log(f"ddl {case.key}")
        run_ddl_case(case, "ddl_metric", workloads)
    for statement in drops:
        cmp.attempt(conn, statement)
    execute(conn, "DROP TABLE ddl_metric")
    emit()


def report_rollback(conn: pymysql.Connection, groups: Sequence[Group], active: Targets, upper: Targets) -> None:
    """有数据时的回退：D 删五张新表（C 共用其中四张），B 在展开表上删 5 列并按行数外推。"""
    emit("## rollback with data")
    max_id: int = execute(conn, "SELECT MAX(field_id) FROM metadata_timeseriesmetric")[0][0]
    sizes: dict[str, Size] = table_sizes(conn, list(NEW_TABLES))
    emit("D tables before drop: " + ", ".join(f"{t} {s.rows:,} rows {mib(s.ibd)} MiB" for t, s in sizes.items()))
    run_ddl_case(
        DdlCase("drop_d_data", "D 回退：删五张有数据的新表", [f"DROP TABLE {name}" for name in NEW_TABLES]),
        "metadata_timeseriesmetric",
        metric_workloads("metadata_timeseriesmetric", [g.group_id for g in groups], max_id),
    )
    execute(conn, "DROP TABLE x1_timeseriesmetric")
    b_rows: int = execute(conn, f"SELECT COUNT(*) FROM {B_TABLE}")[0][0]
    b_max: int = execute(conn, f"SELECT MAX(field_id) FROM {B_TABLE}")[0][0]
    point: Workloads = [
        (
            "展开表点读",
            f"SELECT field_id, field_name, last_modify_time FROM {B_TABLE} WHERE field_id = %s",
            lambda rng: (rng.randint(1, b_max),),
        ),
        (
            "展开表点写",
            f"UPDATE {B_TABLE} SET last_modify_time = NOW(6) WHERE field_id = %s",
            lambda rng: (rng.randint(1, b_max),),
        ),
    ]
    drop: str = "ALTER TABLE " + B_TABLE + " " + ", ".join(f"DROP COLUMN `{name}`" for name, _ in X1_NEW_COLUMNS)
    result: dict[str, Any] = run_ddl_case(
        DdlCase("drop_b_data", f"B 回退：展开表 {b_rows:,} 行删 5 列", [drop]), B_TABLE, point
    )
    per_row: float = result["elapsed_s"] / max(1, b_rows)
    RESULT["rollback_b"] = {
        "rows": b_rows,
        "seconds": result["elapsed_s"],
        "active": per_row * active.b_rows,
        "upper": per_row * upper.b_rows,
    }
    emit(
        f"  B extrapolated by rows: active {active.b_rows:,.0f} rows {per_row * active.b_rows:,.0f} s, "
        f"upper {upper.b_rows:,.0f} rows {per_row * upper.b_rows:,.0f} s"
    )
    emit()


# ---------------------------------------------------------------- 迁移被吞


def report_swallow() -> None:
    """旧表结构只有 TimeSeriesMetric 与 TimeSeriesScope，依次执行各方案新代码的语句并记录错误码。"""
    conn: pymysql.Connection = connect(database=OLD_DATABASE)
    execute(conn, catalog.DDL["metadata_timeseriesscope"])
    execute(conn, catalog.DDL["metadata_timeseriesmetric"])
    execute(
        conn,
        "INSERT INTO metadata_timeseriesscope VALUES (1, 1, 'default', '{}', '[]', 'default', %s)",
        (NOW,),
    )
    columns: str = ", ".join(catalog.METRIC_LOAD)
    for field_id, name in ((1, "request_duration_sum"), (2, "order_total"), (3, "cache_hit_total")):
        execute(
            conn,
            f"INSERT INTO metadata_timeseriesmetric ({columns}) VALUES ({marks(len(catalog.METRIC_LOAD))})",
            (field_id, 1, 1, f"t.{name}", "default", name, "[]", "{}", CREATE_TIME, NOW, "", 1, 0),
        )
    insert_cols: list[str] = catalog.METRIC_LOAD[1:]
    old_row: tuple[Any, ...] = (1, 1, "t.new_metric", "default", "new_metric", "[]", "{}", CREATE_TIME, NOW, "", 1, 0)
    new_cols: list[str] = [name for name, _ in X1_NEW_COLUMNS]
    x1_cols: str = defs(X1) + ", m.meta_fingerprint, m.meta_seen_at"
    page_base: str = (
        f"SELECT {PAGE_COLS} FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE} ORDER BY m.field_name LIMIT {PAGE}"
    )
    page_x1: str = page_base.replace(f"SELECT {PAGE_COLS}", f"SELECT {PAGE_COLS}{defs(X1)}")
    tree_base: str = (
        f"SELECT {INFO_COLS} FROM metadata_timeseriesmetric m WHERE m.group_id = %s AND m.last_modify_time > %s"
    )
    tree_x1: str = tree_base.replace(f"SELECT {INFO_COLS}", f"SELECT {INFO_COLS}{defs(X1)}")
    graph_base: str = f"SELECT {INFO_COLS} FROM metadata_timeseriesmetric m WHERE m.field_id IN (%s, %s)"
    graph_x1: str = graph_base.replace(f"SELECT {INFO_COLS}", f"SELECT {INFO_COLS}{x1_cols}")
    gorm_read: str = "SELECT * FROM metadata_timeseriesmetric WHERE group_id = %s"
    insert_base: str = (
        f"INSERT INTO metadata_timeseriesmetric ({', '.join(insert_cols)}) VALUES ({marks(len(insert_cols))})"
    )
    insert_x1: str = (
        f"INSERT INTO metadata_timeseriesmetric ({', '.join(insert_cols + new_cols)}) "
        f"VALUES ({marks(len(insert_cols) + len(new_cols))})"
    )
    x1_row: tuple[Any, ...] = (
        *old_row[:3],
        "default",
        "new_metric_x1",
        *old_row[5:],
        "new_metric_x1",
        "counter",
        "{}",
        "0" * 32,
        NOW,
    )
    b_mgmt: str = (
        f"SELECT {explode.MGMT_COLUMNS}, ANY_VALUE(original_name), ANY_VALUE(metric_type), ANY_VALUE(meta) "
        f"FROM metadata_timeseriesmetric WHERE {B_MGMT_WHERE} GROUP BY field_name ORDER BY field_name LIMIT %s, {PAGE}"
    )
    b_service: str = f"SELECT {PAGE_COLS}{defs(X1)} FROM metadata_timeseriesmetric m WHERE m.group_id = %s AND m.field_scope IN (%s, %s)"
    member_read: str = catalog.apply_sql(catalog.MEMBER_READ, "(%s, %s, %s)", 1)
    d_page: str = catalog.q1_case(X3, [1], 0, "m.field_name", False).sql
    d_defs: str = "SELECT id, field_name, original_name, metric_type, meta FROM x3_metric_meta WHERE (group_id, field_name) IN ((%s, %s))"
    svc: tuple[str, str] = Pick(1, "checkout").scopes
    statements: list[tuple[str, str, str, str, tuple[Any, ...]]] = [
        ("B", "存量", "管理页（按指标名去重并读元信息）", b_mgmt, (1, 0)),
        ("B", "存量", "指标树与指标缓存（模型含新列）", tree_x1, (1, EXPIRE_BEFORE)),
        ("B", "存量", "图表（按 field_id 取模型）", graph_x1, (1, 2)),
        ("B", "存量", "bmw 指标同步读取（gorm SELECT *）", gorm_read, (1,)),
        ("B", "存量", "指标同步新建（写入新列）", insert_x1, x1_row),
        ("B", "新增", "服务视图（field_scope 按服务）", b_service, (1, *svc)),
        ("C", "存量", "管理页（模型含新列）", page_x1, (1,)),
        ("C", "存量", "指标树与指标缓存（模型含新列）", tree_x1, (1, EXPIRE_BEFORE)),
        ("C", "存量", "图表（按 field_id 取模型）", graph_x1, (1, 2)),
        ("C", "存量", "bmw 指标同步读取（gorm SELECT *）", gorm_read, (1,)),
        ("C", "存量", "指标同步新建（写入新列）", insert_x1, x1_row),
        ("C", "新增", "服务视图（成员表）", member_service_sql(X1), (1, "checkout")),
        ("C", "新增", "bmw Apply 读成员", member_read, (1, 1, 1)),
        ("D", "存量", "管理页（模型不变）", page_base, (1,)),
        ("D", "存量", "指标树与指标缓存（模型不变）", tree_base, (1, EXPIRE_BEFORE)),
        ("D", "存量", "图表（按 field_id 取模型）", graph_base, (1, 2)),
        ("D", "存量", "bmw 指标同步读取（gorm SELECT *）", gorm_read, (1,)),
        ("D", "存量", "指标同步新建（模型不变）", insert_base, old_row),
        ("D", "新增", "管理页关联定义（同一条语句 LEFT JOIN）", d_page, (1,)),
        ("D", "新增", "管理页定义单独查询", d_defs, (1, "request_duration_sum")),
        ("D", "新增", "服务视图（成员表）", member_service_sql(X3), (1, "checkout")),
        ("D", "新增", "bmw Apply 读成员", member_read, (1, 1, 1)),
    ]
    emit("## migration swallowed: new code on the old schema (TimeSeriesMetric and TimeSeriesScope only)")
    emit(f"{'scheme':<8}{'kind':<6}{'result':<12}case")
    summary: dict[str, dict[str, list[str]]] = {}
    for scheme, kind, title, sql, params in statements:
        outcome: cmp.Outcome = cmp.attempt(conn, sql, params)
        status: str = "OK" if outcome.ok else f"ERROR {outcome.code}"
        emit(f"{scheme:<8}{kind:<6}{status:<12}{title}")
        bucket: dict[str, list[str]] = summary.setdefault(
            scheme, {"存量": [], "新增": [], "存量失败": [], "新增失败": []}
        )
        bucket[kind].append(title)
        if not outcome.ok:
            bucket[f"{kind}失败"].append(f"{title} {outcome.code}")
    emit()
    for scheme, bucket in summary.items():
        emit(
            f"{scheme}: existing {len(bucket['存量失败'])}/{len(bucket['存量'])} failed, "
            f"new {len(bucket['新增失败'])}/{len(bucket['新增'])} failed"
        )
    RESULT["swallow"] = summary
    emit()
    conn.close()


# ---------------------------------------------------------------- 正确性抽检


FAMILY_WHERE: str = "group_id = 1 AND original_name = 'http_server_duration' AND metric_type = 'histogram'"


def check_scopes(service: str) -> tuple[str, str]:
    """B 的服务视图要列出该服务的全部 scope_name 才能拼出 field_scope，小数据只有 http 与 custom。"""
    return apm_raw_scope(service, "http"), apm_raw_scope(service, "custom")


def report_check() -> None:
    """小数据断言：checkout、payment、search 在 http 下报 request_duration_sum，search 用旧版 SDK 报 unit=ms；
    checkout 另在 custom 下报 order_total 与 Histogram 族。A 的白名单按 scope_name 建键、按页面分组名查找，在 Python 中模拟。"""
    conn: pymysql.Connection = connect(database=CHECK_DATABASE)
    for ddl in (
        catalog.DDL["metadata_timeseriesscope"],
        catalog.DDL["metadata_timeseriesmetric"],
        catalog.DDL["x1_timeseriesmetric"],
        *NEW_TABLES.values(),
        B_DDL,
        "CREATE TABLE rt_field (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, table_id VARCHAR(128) NOT NULL, "
        "field_name VARCHAR(255) NOT NULL, bk_tenant_id VARCHAR(64) NOT NULL, unit VARCHAR(32) NOT NULL, "
        "UNIQUE KEY uk_field (table_id, field_name, bk_tenant_id)) DEFAULT CHARSET=utf8mb3",
    ):
        execute(conn, ddl)
    for page_id, name in ((1, "http"), (2, "custom"), (3, "my_group")):
        execute(
            conn,
            "INSERT INTO metadata_timeseriesscope VALUES (%s, 1, %s, '{}', '[]', 'data', %s)",
            (page_id, name, NOW),
        )
    metrics: list[tuple[int, str, str, str, int, str]] = [
        (1, "request_duration_sum", "request_duration_sum", "counter", 1, "s"),
        (2, "order_total", "order_total", "counter", 2, "none"),
        (3, "http_server_duration_bucket", "http_server_duration", "histogram", 1, "s"),
        (4, "http_server_duration_sum", "http_server_duration", "histogram", 1, "s"),
        (5, "http_server_duration_count", "http_server_duration", "histogram", 1, "s"),
    ]
    meta_of: dict[int, str] = {m[0]: json.dumps({"unit": m[5], "description": m[1]}) for m in metrics}
    legacy: str = json.dumps({"unit": "ms", "description": "request_duration_sum (legacy sdk)"})
    columns: str = ", ".join(catalog.METRIC_LOAD)
    for field_id, name, original, kind, page, _ in metrics:
        base: tuple[Any, ...] = (
            field_id,
            1,
            page,
            f"t.{name}",
            "default",
            name,
            "[]",
            "{}",
            CREATE_TIME,
            NOW,
            "",
            1,
            0,
        )
        fp: str = md5_hex(meta_of[field_id])
        execute(conn, f"INSERT INTO metadata_timeseriesmetric ({columns}) VALUES ({marks(13)})", base)
        execute(
            conn,
            f"INSERT INTO x1_timeseriesmetric ({', '.join(B_LOAD)}) VALUES ({marks(18)})",
            (*base, original, kind, meta_of[field_id], fp, NOW),
        )
        execute(
            conn,
            "INSERT INTO x3_metric_meta (id, group_id, field_name, original_name, metric_type, meta, fingerprint, seen_at) "
            "VALUES (%s, 1, %s, %s, %s, %s, %s, %s)",
            (field_id, name, original, kind, meta_of[field_id], fp, NOW),
        )
    execute(
        conn,
        f"INSERT INTO {VALUE_TABLE} (id, group_id, fingerprint, meta) VALUES (1, 1, %s, %s)",
        (md5_hex(legacy), legacy),
    )
    scopes: list[tuple[int, str, str]] = [
        (1, "checkout", "http"),
        (2, "payment", "http"),
        (3, "search", "http"),
        (4, "checkout", "custom"),
    ]
    for scope_id, service, scope_name in scopes:
        labels: dict[str, str] = {"scope_name": scope_name, "service_name": service}
        execute(
            conn,
            "INSERT INTO report_scope VALUES (%s, 1, 'APM', %s, %s, %s, %s)",
            (scope_id, md5_hex(source_key(labels)), apm_raw_scope(service, scope_name), json.dumps(labels), NOW),
        )
        for key in ("scope_name", "service_name"):
            execute(
                conn,
                "INSERT INTO report_scope_label (group_id, label_key, label_value, report_scope_id) VALUES (1, %s, %s, %s)",
                (key, labels[key], scope_id),
            )
    members: list[tuple[int, int, int]] = [(1, 1, 0), (2, 1, 0), (3, 1, 1), (4, 2, 0), (1, 3, 0), (1, 4, 0), (1, 5, 0)]
    b_id: int = 0
    for scope_id, ref, value in members:
        execute(
            conn,
            "INSERT INTO report_member (group_id, report_scope_id, ref_id, last_seen, meta_value_id) VALUES (1, %s, %s, %s, %s)",
            (scope_id, ref, NOW, value),
        )
        _, service, scope_name = scopes[scope_id - 1]
        field_id, name, original, kind, page, _ = metrics[ref - 1]
        meta: str = legacy if value else meta_of[ref]
        b_id += 1
        execute(
            conn,
            f"INSERT INTO {B_TABLE} ({', '.join(B_LOAD)}) VALUES ({marks(18)})",
            (
                b_id,
                1,
                page,
                f"t.{name}",
                apm_raw_scope(service, scope_name),
                name,
                "[]",
                "{}",
                CREATE_TIME,
                NOW,
                "",
                1,
                0,
                original,
                kind,
                meta,
                md5_hex(meta),
                NOW,
            ),
        )
    whitelist: dict[str, dict[str, set[str]]] = {"http": {}, "custom": {}}
    for scope_id, ref, _ in members:
        _, service, scope_name = scopes[scope_id - 1]
        whitelist[scope_name].setdefault(metrics[ref - 1][1], set()).add(service)
    page_names: dict[int, str] = {1: "http", 2: "custom", 3: "my_group"}
    page_of_a: dict[str, int] = {m[1]: m[4] for m in metrics}

    def service_view(scheme: str, service: str) -> set[tuple[str, str]]:
        if scheme == "A":
            return {
                (page_names[page_of_a[name]], name)
                for name in page_of_a
                if service in whitelist.get(page_names[page_of_a[name]], {}).get(name, set())
            }
        if scheme == "B":
            return {(r[0], r[2]) for r in execute(conn, B_SERVICE_SQL, (1, *check_scopes(service)))}
        return {(r[0], r[2]) for r in execute(conn, member_service_sql(VARIANT_OF[scheme]), (1, service))}

    def unit_of(scheme: str, service: str) -> str | None:
        if scheme == "B":
            rows = execute(
                conn,
                f"SELECT JSON_UNQUOTE(JSON_EXTRACT(meta, '$.unit')) FROM {B_TABLE} WHERE group_id = 1 "
                "AND field_name = 'request_duration_sum' AND field_scope = %s",
                (check_scopes(service)[0],),
            )
        else:
            v: Variant = VARIANT_OF[scheme]
            rows = execute(
                conn,
                f"SELECT JSON_UNQUOTE(JSON_EXTRACT(COALESCE(mv.meta, {v.d}.meta), '$.unit')) FROM {LABEL_TO_MEMBER} "
                f"{v.member_join} LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id WHERE {SERVICE_LABEL} "
                "AND m.field_name = 'request_duration_sum'",
                (1, service),
            )
        return rows[0][0] if rows else None

    checks: list[tuple[str, dict[str, bool], dict[str, bool], dict[str, str]]] = []

    def add(
        title: str, actual: dict[str, bool], expected: dict[str, bool], notes: dict[str, str] | None = None
    ) -> None:
        checks.append((title, actual, expected, notes or {}))

    before: dict[str, bool] = {s: ("http", "request_duration_sum") in service_view(s, "checkout") for s in SCHEMES}
    add("移入前 checkout 服务视图含 request_duration_sum", before, dict.fromkeys(SCHEMES, True))
    moved: dict[str, int] = {
        "B": cmp.attempt(
            conn, f"UPDATE {B_TABLE} SET scope_id = 3 WHERE group_id = 1 AND field_name = 'request_duration_sum'"
        ).affected,
        "C": cmp.attempt(conn, "UPDATE x1_timeseriesmetric SET scope_id = 3 WHERE field_id = 1").affected,
        "D": cmp.attempt(conn, "UPDATE metadata_timeseriesmetric SET scope_id = 3 WHERE field_id = 1").affected,
    }
    page_of_a["request_duration_sum"] = 3
    after: dict[str, bool] = {s: ("my_group", "request_duration_sum") in service_view(s, "checkout") for s in SCHEMES}
    add(
        "移入自建分组 my_group 后服务视图仍可见",
        after,
        {"A": False, "B": True, "C": True, "D": True},
        {"A": "白名单按页面分组名 my_group 查找未命中", **{s: f"移动改写 {n} 行" for s, n in moved.items()}},
    )
    units: dict[str, tuple[str | None, str | None]] = {s: (unit_of(s, "search"), unit_of(s, "checkout")) for s in "BCD"}
    first: cmp.Outcome = cmp.attempt(
        conn,
        "INSERT INTO rt_field (table_id, field_name, bk_tenant_id, unit) VALUES ('t', 'request_duration_sum', 'system', 's')",
    )
    second: cmp.Outcome = cmp.attempt(
        conn,
        "INSERT INTO rt_field (table_id, field_name, bk_tenant_id, unit) VALUES ('t', 'request_duration_sum', 'system', 'ms')",
    )
    add(
        "按范围例外：search 为 ms，checkout 为 s",
        {"A": first.ok and second.ok, **{s: units[s] == ("ms", "s") for s in "BCD"}},
        {"A": False, "B": True, "C": True, "D": True},
        {
            "A": f"ResultTableField 唯一键第二行 {'OK' if second.ok else f'ERROR {second.code}'}",
            **{s: f"search={u[0]} checkout={u[1]}" for s, u in units.items()},
        },
    )
    early: dict[str, cmp.Outcome] = {
        "A": cmp.attempt(conn, "UPDATE rt_field SET unit = 's' WHERE field_name = 'cache_hit_total'"),
        "B": cmp.attempt(
            conn,
            f"UPDATE {B_TABLE} SET meta = %s WHERE group_id = 1 AND field_name = 'cache_hit_total'",
            ('{"unit": "1"}',),
        ),
        "C": cmp.attempt(
            conn,
            "UPDATE x1_timeseriesmetric SET meta = %s WHERE group_id = 1 AND field_name = 'cache_hit_total'",
            ('{"unit": "1"}',),
        ),
        "D": cmp.attempt(
            conn,
            "INSERT INTO x3_metric_meta (id, group_id, field_name, original_name, metric_type, meta, fingerprint, seen_at) "
            "VALUES (6, 1, 'cache_hit_total', 'cache_hit_total', 'counter', '{\"unit\": \"1\"}', %s, %s)",
            ("0" * 32, NOW),
        ),
    }
    execute(
        conn,
        f"INSERT INTO metadata_timeseriesmetric ({columns}) VALUES ({marks(13)})",
        (6, 1, 1, "t.cache_hit_total", "default", "cache_hit_total", "[]", "{}", CREATE_TIME, NOW, "", 1, 0),
    )
    joined: tuple[Any, ...] = execute(
        conn,
        f"SELECT JSON_UNQUOTE(JSON_EXTRACT(d.meta, '$.unit')) FROM {X3.source} WHERE m.field_id = 6",
    )
    add(
        "元信息先于指标同步到达可以落库",
        {s: o.ok and o.affected > 0 for s, o in early.items()} | {"D": early["D"].ok and joined[0][0] == "1"},
        {"A": False, "B": False, "C": False, "D": True},
        {s: f"写入 {o.affected} 行" for s, o in early.items()}
        | {"D": f"写入 1 行，指标项到达后关联得 unit={joined[0][0]}"},
    )
    family_sql: dict[str, str] = {
        "B": f"SELECT COUNT(DISTINCT field_name) FROM {B_TABLE} WHERE {FAMILY_WHERE}",
        "C": f"SELECT COUNT(*) FROM x1_timeseriesmetric WHERE {FAMILY_WHERE}",
        "D": f"SELECT COUNT(*) FROM x3_metric_meta WHERE {FAMILY_WHERE}",
    }
    a_original: bool = bool(
        execute(
            conn,
            "SELECT 1 FROM information_schema.COLUMNS WHERE table_schema = %s AND table_name = 'rt_field' "
            "AND column_name = 'original_name'",
            (CHECK_DATABASE,),
        )
    )
    families: dict[str, int] = {s: execute(conn, sql)[0][0] for s, sql in family_sql.items()}
    add(
        "Histogram 按原名组族（_bucket、_sum、_count）",
        {"A": a_original, **{s: n == 3 for s, n in families.items()}},
        {"A": False, "B": True, "C": True, "D": True},
        {"A": "ResultTableField 无原名列", **{s: f"族成员 {n} 个" for s, n in families.items()}},
    )
    old_page: str = f"SELECT {PAGE_COLS} FROM {{table}} m WHERE {MANAGE_WHERE} ORDER BY m.field_name LIMIT {PAGE}"
    old_rows: dict[str, int] = {
        "A": len(execute(conn, old_page.format(table="metadata_timeseriesmetric"), (1,))),
        "B": len(execute(conn, old_page.format(table=B_TABLE), (1,))),
        "C": len(execute(conn, old_page.format(table="x1_timeseriesmetric"), (1,))),
        "D": len(execute(conn, old_page.format(table="metadata_timeseriesmetric"), (1,))),
    }
    add(
        "旧代码管理页读改造后数据仍列出全部指标",
        {s: n >= 5 for s, n in old_rows.items()},
        dict.fromkeys(SCHEMES, True) | {"B": False},
        {s: f"返回 {n} 行" for s, n in old_rows.items()},
    )
    emit("## correctness checks on small data (PASS = behavior matches the expectation of the scheme)")
    passed: int = 0
    for title, actual, expected, notes in checks:
        emit(f"- {title}")
        for scheme in SCHEMES:
            ok: bool = actual[scheme] == expected[scheme]
            passed += ok
            emit(
                f"    [{'PASS' if ok else 'FAIL'}] {scheme} {actual[scheme]!s:<5} expected {expected[scheme]!s:<5} {notes.get(scheme, '')}"
            )
    total: int = len(checks) * len(SCHEMES)
    emit(f"assertions: {passed}/{total} passed")
    RESULT["check"] = {title: actual for title, actual, _, _ in checks}
    RESULT["check_passed"] = (passed, total)
    emit()
    conn.close()


# ---------------------------------------------------------------- 与 MySQL 9.2 对照

REF92: tuple[tuple[str, str, dict[str, tuple[float, str]]], ...] = (
    (
        "最大数据源管理页首页",
        "ms",
        {
            "A": (15.444, "xl.page1"),
            "B": (1133.495, "xl.page1_stmt"),
            "C": (16.825, "xl.page1"),
            "D": (15.617, "xl.page1"),
        },
    ),
    (
        "最大数据源管理页计数",
        "ms",
        {"A": (14.599, "xl.count"), "B": (876.142, "xl.count"), "C": (15.758, "xl.count"), "D": (14.599, "xl.count")},
    ),
    (
        "最大数据源 OFFSET 10000",
        "ms",
        {"A": (36.087, "xl.deep"), "B": (1146.210, "xl.deep_stmt"), "C": (39.624, "xl.deep"), "D": (56.659, "xl.deep")},
    ),
    (
        "最大数据源服务视图",
        "ms",
        {"B": (105.421, "xl.service"), "C": (10.982, "xl.service"), "D": (13.456, "xl.service")},
    ),
    ("最大数据源最热服务", "ms", {"C": (112.297, "xl.hot"), "D": (140.226, "xl.hot")}),
    ("126 个服务的数据源服务视图", "ms", {"C": (1.159, "l.service"), "D": (1.426, "l.service")}),
    ("126 个服务的数据源管理页首页", "ms", {"A": (0.868, "l.page1"), "C": (0.974, "l.page1"), "D": (1.033, "l.page1")}),
    (
        "最大数据源整组读取",
        "ms",
        {
            "A": (82.850, "xl.group"),
            "B": (4833.624, "xl.group"),
            "C": (104.319, "xl.group"),
            "D": (107.207, "xl.group"),
        },
    ),
    (
        "全平台扫描，活跃规模",
        "s",
        {"A": (4.38, "scan"), "B": (49.736, "scan"), "C": (5.51, "scan"), "D": (5.47, "scan")},
    ),
    ("Apply 最大数据源，catalog 写法", "ms", {"C": (24.168, "apply.xl.catalog"), "D": (21.898, "apply.xl.catalog")}),
    (
        "Apply 混合数据源，catalog 写法",
        "ms",
        {"C": (22.383, "apply.mixed.catalog"), "D": (19.937, "apply.mixed.catalog")},
    ),
)


def order_of(values: dict[str, float]) -> str:
    ordered: list[tuple[str, float]] = sorted(values.items(), key=lambda kv: kv[1])
    text: str = ordered[0][0]
    for (_, prev), (name, value) in zip(ordered, ordered[1:], strict=False):
        text += (" ≈ " if value <= prev * 1.10 else " < ") + name
    return text


def report_compare() -> None:
    emit("## 5.7 vs 9.2 (REPORT values: m2_catalog.txt for A/C/D, m1_explode.txt for B; 9.2 B has no metadata columns)")
    emit(f"{'case':<32}{'unit':>5}  {'scheme 9.2 -> 5.7 (x)':<64}{'order 9.2':<20}{'order 5.7':<20}same")
    for title, unit, by_scheme in REF92:
        old: dict[str, float] = {}
        new: dict[str, float] = {}
        cells: list[str] = []
        for scheme, (value, key) in by_scheme.items():
            measured: float | None = RESULT["p50"].get(key, {}).get(scheme)
            if measured is None:
                continue
            old[scheme], new[scheme] = value, measured
            cells.append(f"{scheme} {value:,.1f}->{measured:,.1f} ({measured / value:.1f}x)")
        if not new:
            continue
        o92, o57 = order_of(old), order_of(new)
        emit(f"{title:<32}{unit:>5}  {'; '.join(cells):<64}{o92:<20}{o57:<20}{'yes' if o92 == o57 else 'NO'}")
    emit()


# ---------------------------------------------------------------- 汇总


def report_summary(guard: DiskGuard | None, loads: dict[str, float]) -> None:
    p: dict[str, dict[str, float]] = RESULT["p50"]

    def cell(key: str, scheme: str, unit: str = "ms") -> str:
        value: float | None = p.get(key, {}).get(scheme)
        if value is None:
            return "-"
        return f"{value:,.1f} {unit}" if value >= 10 else f"{value:,.2f} {unit}"

    emit("## summary matrix (p50, 5.7)")
    rows: list[tuple[str, str, str]] = [
        ("XL page1 (request)", "xl.page1", "ms"),
        ("XL page1 (single stmt)", "xl.page1_stmt", "ms"),
        ("XL count", "xl.count", "ms"),
        ("XL OFFSET 10000 (request)", "xl.deep", "ms"),
        ("XL OFFSET 10000 (single stmt)", "xl.deep_stmt", "ms"),
        ("XL service", "xl.service", "ms"),
        ("XL hottest service", "xl.hot", "ms"),
        ("L(126) service", "l.service", "ms"),
        ("L(126) page1", "l.page1", "ms"),
        ("XL group read", "xl.group", "ms"),
        ("L(126) group read", "l.group", "ms"),
        ("scan active", "scan", "s"),
        ("scan upper", "scan.upper", "s"),
        ("Apply XL plan", "apply.xl.plan", "ms"),
        ("Apply mixed plan", "apply.mixed.plan", "ms"),
        ("Apply XL catalog", "apply.xl.catalog", "ms"),
        ("daily refresh XL", "refresh", "s"),
    ]
    emit(f"{'row':<32}" + "".join(f"{s:>16}" for s in READ_SCHEMES))
    for title, key, unit in rows:
        emit(f"{title:<32}" + "".join(f"{cell(key, s, unit):>16}" for s in READ_SCHEMES))
    for name in ("active", "upper"):
        vols: dict[str, float] = RESULT.get("volume", {}).get(name, {})
        emit(f"{'new volume ' + name:<32}" + "".join(f"{mib(vols.get(s, 0.0)) + ' MiB':>16}" for s in SCHEMES))
    for key in (
        "add5",
        "add5_django",
        "drop5",
        "drop5_django",
        "create5",
        "dropnew5",
        "mdl_add5",
        "mdl_add5_lwt1",
        "mdl_create5",
        "drop_d_data",
        "drop_b_data",
    ):
        r: dict[str, Any] | None = RESULT.get("ddl", {}).get(key)
        if r is None:
            continue
        worst: float = max(w["max"] for w in r["workloads"].values())
        p99: float = max(w["p99"] for w in r["workloads"].values())
        emit(
            f"{'ddl ' + key:<32}{r['elapsed_s']:>10.2f} s rebuilt={'yes' if r['rebuilt'] else 'no'} "
            f"worst stall {worst:,.0f} ms p99 {p99:,.1f} ms"
        )
    emit("load seconds: " + ", ".join(f"{k} {v:,.0f}" for k, v in loads.items()))
    if guard is not None:
        guard.sample()
        emit(
            f"disk: datadir peak {guard.peak_data / GIB:.2f} GiB, container tmp peak {guard.peak_tmp / GIB:.2f} GiB, "
            f"host min free {guard.min_free / GIB:.1f} GiB (sampled every 10 s)"
        )
    emit()


def environment(subset: Subset, config: Config) -> None:
    conn: pymysql.Connection = connect()
    names: tuple[str, ...] = (
        "version",
        "innodb_buffer_pool_size",
        "innodb_buffer_pool_instances",
        "innodb_log_file_size",
        "innodb_log_files_in_group",
        "innodb_flush_log_at_trx_commit",
        "innodb_flush_method",
        "innodb_default_row_format",
        "innodb_large_prefix",
        "log_bin",
        "character_set_server",
        "tmp_table_size",
        "max_heap_table_size",
        "internal_tmp_disk_storage_engine",
        "sort_buffer_size",
        "innodb_sort_buffer_size",
        "innodb_online_alter_log_max_size",
        "innodb_adaptive_hash_index",
        "lock_wait_timeout",
        "transaction_isolation",
        "innodb_autoinc_lock_mode",
    )
    variables: dict[str, str] = dict(
        execute(conn, f"SHOW GLOBAL VARIABLES WHERE Variable_name IN ({marks(len(names))})", names)
    )
    conn.close()
    arch: str = docker("exec", CONTAINER, "uname", "-m", check=False).strip()
    digest: str = docker(
        "image", "inspect", IMAGE, "--format", "{{index .RepoDigests 0}} {{.Architecture}}", check=False
    ).strip()
    server: str = docker(
        "version", "--format", "{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}", check=False
    ).strip()
    info: str = docker("info", "--format", "cpus={{.NCPU}} mem={{.MemTotal}}", check=False).strip()
    emit(
        f"# plans57: schemes A/B/C/D on MySQL 5.7, scale={config.scale}, metrics={config.metrics:,}, smoke={config.smoke}"
    )
    emit(
        f"python {platform.python_version()}, pymysql {importlib.metadata.version('pymysql')}, "
        f"host {platform.system()}/{platform.machine()} {os.cpu_count()} cpu"
    )
    emit(f"docker {server}, VM {info}; image {digest}; container uname -m = {arch} (platform {PLATFORM})")
    emit(", ".join(f"{k}={variables.get(k, '-')}" for k in names))
    emit(
        f"loaded members and B rows: {len(subset.xl)} XL, {len(subset.large)} L (126 services), "
        f"{len(subset.tail)} of M/S/XS ({LOADED_TAIL_SHARE:.0%} each)"
    )
    emit()


# ---------------------------------------------------------------- 补测：管理页搜索、族视图节点分页、单范围读取

INLINE_TABLE: str = "report_member_inline"
# catalog 的成员表即「定义加内联例外」：成员 meta 只在偏离定义时保存完整 JSON
INLINE_DDL: str = catalog.DDL["report_member"].replace("report_member", INLINE_TABLE, 1)
DEF_SEARCH: str = (
    "SELECT field_name FROM x3_metric_meta WHERE group_id = %s AND (original_name LIKE %s "
    "OR LOWER(JSON_UNQUOTE(JSON_EXTRACT(meta, '$.\"description\"'))) LIKE LOWER(%s))"
)
NODE_ITEMS: str = f"SELECT m.scope_id, m.field_name FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE}"
NODE_DEFS: str = "SELECT field_name, original_name FROM x3_metric_meta WHERE group_id = %s"
NODE_MEMBERS: str = (
    f"SELECT {PAGE_COLS} FROM metadata_timeseriesmetric m "
    "WHERE m.group_id = %s AND m.field_scope = 'default' AND m.field_name IN ({marks})"
)
SCOPE_WHERE: str = "WHERE s.group_id = %s AND s.report_scope_id = %s"
SCOPE_READS: dict[str, str] = {
    "C": (
        "SELECT s.ref_id, COALESCE(mv.meta, m.meta) FROM report_member s JOIN x1_timeseriesmetric m "
        f"ON m.field_id = s.ref_id LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id {SCOPE_WHERE}"
    ),
    "C.inline": (
        f"SELECT s.ref_id, COALESCE(s.meta, m.meta) FROM {INLINE_TABLE} s JOIN x1_timeseriesmetric m "
        f"ON m.field_id = s.ref_id {SCOPE_WHERE}"
    ),
    "D": (
        "SELECT s.ref_id, COALESCE(mv.meta, d.meta) FROM report_member s JOIN x3_metric_meta d ON d.id = s.ref_id "
        f"LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id {SCOPE_WHERE}"
    ),
    "D.inline": (
        f"SELECT s.ref_id, COALESCE(s.meta, d.meta) FROM {INLINE_TABLE} s JOIN x3_metric_meta d "
        f"ON d.id = s.ref_id {SCOPE_WHERE}"
    ),
}
SCOPE_MEMBERS: str = f"SELECT s.ref_id, s.meta_value_id FROM report_member s {SCOPE_WHERE}"
SCOPE_INLINE_MEMBERS: str = f"SELECT s.ref_id, s.meta FROM {INLINE_TABLE} s {SCOPE_WHERE}"
SUPPLEMENT_SCHEMES: tuple[str, ...] = ("A", "C", "C.inline", "D", "D.inline", "D2", "D2.inline", "D2.desc")
# REPORT 的 9.2 同名用例：搜索与节点分页取 m2_catalog.txt，单范围取 meta_layout.txt 的 1% 档（每个范围 20,000 个成员）
REF92_SUPPLEMENT: dict[str, dict[str, float]] = {
    "xl.search": {"A": 23.422, "C": 48.649, "D": 104.515},
    "l.search": {"A": 0.481, "C": 1.376, "D": 2.344},
    "xl.nodes": {"C": 49.149, "D": 120.267},
    "l.nodes": {"C": 1.798, "D": 2.556},
    "xl.scope": {"D": 64.417, "D.inline": 38.719, "D2": 108.778, "D2.inline": 100.847},
}
REF92_SCOPE_MEMBERS: int = 20_000


def load_inline(conn: pymysql.Connection) -> float:
    """按成员表逐行复制，例外引用换成例外取值的完整 JSON，其余为 NULL，成员与主键顺序不变。"""
    start: float = time.perf_counter()
    execute(conn, INLINE_DDL)
    execute(
        conn,
        f"INSERT INTO {INLINE_TABLE} (id, group_id, report_scope_id, ref_id, last_seen, meta, field_config) "
        "SELECT s.id, s.group_id, s.report_scope_id, s.ref_id, s.last_seen, mv.meta, s.field_config "
        f"FROM report_member s LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id ORDER BY s.id",
    )
    catalog.analyze(conn, [INLINE_TABLE])
    return time.perf_counter() - start


def d_search_case(groups: Sequence[int], by_description: bool) -> Case:
    """D2 的搜索：按名称时与现状相同，再按本页指标名读定义；按描述时先在定义表找出命中的指标名，再查指标项。"""
    tail: str = f" ORDER BY m.field_name LIMIT {PAGE}"

    def run(cur: Cursor, g: int) -> int:
        extra: str = " AND m.field_name LIKE %s"
        params: tuple[Any, ...] = (g, catalog.SEARCH)
        if by_description:
            hits: list[Any] = [r[0] for r in fetch(cur, DEF_SEARCH, (g, catalog.SEARCH, catalog.SEARCH))]
            if hits:
                extra = f" AND (m.field_name LIKE %s OR m.field_name IN ({marks(len(hits))}))"
                params = (g, catalog.SEARCH, *hits)
        where: str = MANAGE_WHERE + extra
        fetch(cur, f"SELECT COUNT(*) FROM metadata_timeseriesmetric m WHERE {where}", params)
        scope_ids: list[Any] = sorted(
            {
                r[0]
                for r in fetch(cur, f"SELECT m.scope_id FROM metadata_timeseriesmetric m WHERE {where}{tail}", params)
            }
            - {None}
        )
        if scope_ids:
            fetch(cur, SCOPE_LOOKUP.replace("{marks}", marks(len(scope_ids))), (*scope_ids, g))
        names: list[Any] = [
            r[2] for r in fetch(cur, f"SELECT {PAGE_COLS} FROM metadata_timeseriesmetric m WHERE {where}{tail}", params)
        ]
        if names:
            fetch(cur, DEF_BY_NAMES.replace("{marks}", marks(len(names))), (g, *names))
        return len(names)

    sql: str = DEF_SEARCH if by_description else DEF_BY_NAMES.replace("{marks}", "%s")
    params: tuple[Any, ...] = (
        (groups[0], catalog.SEARCH, catalog.SEARCH) if by_description else (groups[0], catalog.metric_names(3)[0])
    )
    return Case([lambda cur, g=g: run(cur, g) for g in groups], sql, params)


def a_nodes_case(groups: Sequence[int], fill: bool = True) -> Case:
    """现状没有族，节点即指标：与 catalog q2 相同的节点分页、节点总数与取本页指标，节点键为指标名；fill 为假时不取本页指标。"""
    nodes_sql: str = (
        f"SELECT m.scope_id, m.field_name AS node, COUNT(*) FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE} "
        f"GROUP BY m.scope_id, node ORDER BY m.scope_id, node LIMIT {PAGE}"
    )
    total_sql: str = (
        f"SELECT COUNT(*) FROM (SELECT 1 FROM metadata_timeseriesmetric m WHERE {MANAGE_WHERE} "
        "GROUP BY m.scope_id, m.field_name) t"
    )

    def run(cur: Cursor, g: int) -> int:
        names: list[Any] = sorted({r[1] for r in fetch(cur, nodes_sql, (g,))})
        fetch(cur, total_sql, (g,))
        if not fill:
            return len(names)
        return len(fetch(cur, NODE_MEMBERS.replace("{marks}", marks(len(names))), (g, *names)))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], nodes_sql, (groups[0],))


def d_nodes_case(groups: Sequence[int]) -> Case:
    """D2 的节点分页按 PLAN「族在内存中组装」：整组读指标项与定义的原名，客户端归组、排序、分页，再取本页节点的全部族成员。"""

    def run(cur: Cursor, g: int) -> int:
        originals: dict[Any, Any] = dict(fetch(cur, NODE_DEFS, (g,)))
        nodes: dict[tuple[int, str], list[str]] = {}
        for scope_id, name in fetch(cur, NODE_ITEMS, (g,)):
            key: tuple[int, str] = (-1 if scope_id is None else int(scope_id), originals.get(name) or name)
            nodes.setdefault(key, []).append(name)
        page: list[tuple[int, str]] = sorted(nodes)[:PAGE]
        wanted: list[str] = sorted({name for key in page for name in nodes[key]})
        members: tuple[Any, ...] = fetch(cur, NODE_MEMBERS.replace("{marks}", marks(len(wanted))), (g, *wanted))
        fetch(cur, DEF_BY_NAMES.replace("{marks}", marks(len(wanted))), (g, *wanted))
        return len(members)

    return Case([lambda cur, g=g: run(cur, g) for g in groups], NODE_DEFS, (groups[0],))


def scope_split_case(probes: Sequence[tuple[int, int]], inline: bool) -> Case:
    """单范围分两次读：先读成员，再按 ID 列表读定义，引用例外时另读例外取值，与 meta_layout 的 B.in 相同。"""

    def run(cur: Cursor, params: tuple[int, int]) -> int:
        if inline:
            members: tuple[Any, ...] = fetch(cur, SCOPE_INLINE_MEMBERS, params)
            fetch(cur, f"SELECT id, meta FROM x3_metric_meta WHERE id IN ({', '.join(r[0] for r in members)})", None)
            return len(members)
        members = fetch(cur, SCOPE_MEMBERS, params)
        fetch(cur, f"SELECT id, meta FROM x3_metric_meta WHERE id IN ({', '.join(r[0] for r in members)})", None)
        refs: list[str] = sorted({r[1] for r in members if r[1] != "0"})
        if refs:
            fetch(cur, f"SELECT id, meta FROM {VALUE_TABLE} WHERE id IN ({', '.join(refs)})", None)
        return len(members)

    sql: str = SCOPE_INLINE_MEMBERS if inline else SCOPE_MEMBERS
    return Case([lambda cur, p=p: run(cur, p) for p in probes], sql, probes[0])


def scope_probes(
    conn: pymysql.Connection, g: int
) -> tuple[list[tuple[int, int]], list[tuple[int, int]], dict[int, int]]:
    """最大的 10 个范围与随机 50 个范围；9.2 的单范围用例每个范围有 20,000 个成员，按每千成员耗时对照。"""
    sizes: dict[int, int] = dict(
        execute(
            conn,
            "SELECT report_scope_id, COUNT(*) FROM report_member WHERE group_id = %s GROUP BY report_scope_id",
            (g,),
        )
    )
    ordered: list[int] = sorted(sizes, key=lambda s: -sizes[s])
    picked: list[int] = random.Random("plans57.scope").sample(ordered, min(50, len(ordered)))
    return [(g, s) for s in ordered[:10]], [(g, s) for s in picked], sizes


def supplement_budget(tier: str, name: str) -> tuple[int, int]:
    if cfg().smoke:
        return 1, 3
    if tier == "xl" and name in ("search", "nodes"):
        return 10, 100
    if name.startswith("scope"):
        return 5, 50
    return 30, 300


def report_supplement(conn: pymysql.Connection, raw: pymysql.Connection, xl: int, large: Sequence[int]) -> None:
    hot, picked, sizes = scope_probes(conn, xl)
    emit(
        f"## supplement probes: XL group {xl}, {len(sizes):,} scopes, largest scope {max(sizes.values()):,} members, "
        f"median {int(statistics.median(sizes.values())):,}; {len(large)} L groups; search term {catalog.SEARCH!r}"
    )
    emit(
        "A = base (search by name), C/D = REPORT 9.2 SQL (name OR original_name OR description, definitions joined), "
        "D2 = PLAN read (name search, then definitions by page names), D2.desc = definitions searched first"
    )
    emit()
    cases: dict[str, dict[str, Case]] = {}
    for tier, groups in (("xl", [xl]), ("l", list(large))):
        cases[f"{tier}.search"] = {
            "A": catalog.q1_case(BASE_VARIANT, groups, 0, "m.field_name", True),
            "C": catalog.q1_case(X1, groups, 0, "m.field_name", True),
            "D": catalog.q1_case(X3, groups, 0, "m.field_name", True),
            "D2": d_search_case(groups, False),
            "D2.desc": d_search_case(groups, True),
        }
        cases[f"{tier}.nodes"] = {
            "A": a_nodes_case(groups),
            "C": catalog.q2_case(X1, groups),
            "D": catalog.q2_case(X3, groups),
            "D2": d_nodes_case(groups),
        }
    for name, probes in (("xl.scope", hot), ("xl.scope_random", picked)):
        by_scheme: dict[str, Case] = {s: statement_case(sql, probes) for s, sql in SCOPE_READS.items()}
        by_scheme["D2"] = scope_split_case(probes, inline=False)
        by_scheme["D2.inline"] = scope_split_case(probes, inline=True)
        cases[name] = by_scheme
    emit("## supplement reads: p50/p95/p99 ms over TCP without type conversion (warmup/runs per line)")
    emit(catalog.STAT_HEADER + f"{'runs':>10}{'ms/1k rows':>12}")
    plans: list[str] = []
    for key, by_scheme in cases.items():
        tier, name = key.split(".", 1)
        for scheme in SUPPLEMENT_SCHEMES:
            case: Case | None = by_scheme.get(scheme)
            if case is None:
                continue
            warmup, runs = supplement_budget(tier, name)
            label: str = f"{key}.{scheme}"
            log(f"measure {label}")
            stat: Stat = catalog.measure(label, raw, case.runs, seed=key, warmup=warmup, iterations=runs)
            p50: float = statistics.median(stat.samples)
            per_k: float = p50 / max(1.0, statistics.mean(stat.rows)) * 1000
            emit(stat.line() + f"{warmup:>4}/{runs:<5}" + (f"{per_k:>12.2f}" if name.startswith("scope") else ""))
            record(key, scheme, p50)
            record(f"{key}.per_k", scheme, per_k)
            plans.append(f"{label}: {catalog.explain(conn, case.sql, case.params)}")
    emit()
    emit("## EXPLAIN (table:key/type~rows[flags]; main statement of each case)")
    for plan in plans:
        emit(plan)
    emit()
    report_supplement_compare()


def report_supplement_compare() -> None:
    p: dict[str, dict[str, float]] = RESULT["p50"]
    emit(
        "## supplement vs 9.2 (search/nodes: m2_catalog.txt; single scope: meta_layout.txt 1%, 20,000 members per scope)"
    )
    emit(f"{'case':<14}{'scheme':<11}{'9.2 ms':>10}{'5.7 ms':>11}{'x':>7}{'9.2 ms/1k':>11}{'5.7 ms/1k':>11}")
    for key, ref in REF92_SUPPLEMENT.items():
        for scheme, old in ref.items():
            new: float | None = p.get(key, {}).get(scheme)
            if new is None:
                continue
            if key == "xl.scope":
                per_k: float = p[f"{key}.per_k"][scheme]
                old_k: float = old / REF92_SCOPE_MEMBERS * 1000
                emit(f"{key:<14}{scheme:<11}{old:>10.1f}{new:>11.1f}{'-':>7}{old_k:>11.2f}{per_k:>11.2f}")
            else:
                emit(f"{key:<14}{scheme:<11}{old:>10.1f}{new:>11.1f}{new / old:>7.1f}")
    emit()
    emit("## supplement ratios (p50): D/C, D/A, D2/C, D2/A")
    for key in ("xl.search", "l.search", "xl.nodes", "l.nodes", "xl.scope", "xl.scope_random"):
        row: dict[str, float] = p.get(key, {})
        parts: list[str] = []
        for num, den in (
            ("D", "C"),
            ("D", "A"),
            ("D2", "C"),
            ("D2", "A"),
            ("D2.desc", "C"),
            ("D", "D.inline"),
            ("C", "C.inline"),
        ):
            if num in row and den in row:
                parts.append(f"{num}/{den} {row[num] / row[den]:.2f}")
        emit(f"{key:<16}" + ", ".join(parts))
    emit()


def run_supplement(config: Config, groups: Sequence[Group], subset: Subset, guard: DiskGuard) -> None:
    """只装载补测需要的数据：全部指标项、扩列与定义，最大数据源的成员、例外取值与内联例外成员表。"""
    started: float = time.perf_counter()
    conn: pymysql.Connection = connect()
    raw: pymysql.Connection = connect(raw=True)
    loads: dict[str, float] = {}
    log("load metric items, X1 columns and X3 definitions")
    field_ids, loads["metrics + X1 + X3"] = load_base(conn, groups)
    log("load members and values of the largest group")
    start: float = time.perf_counter()
    stat: LoadStat = load_reports(conn, subset.xl, field_ids, page_ids_of(groups))
    loads["XL members + values"] = time.perf_counter() - start
    log("copy members into the inline-exception layout")
    loads["inline members"] = load_inline(conn)
    emit(
        f"loaded: {len(groups):,} groups, {config.metrics:,} metric items; XL members {stat.members:,}, "
        f"values {stat.values:,}, inline members {execute(conn, f'SELECT COUNT(*) FROM {INLINE_TABLE}')[0][0]:,}; load "
        + ", ".join(f"{k} {v:,.0f} s" for k, v in loads.items())
    )
    emit()
    report_supplement(conn, raw, subset.xl[0].group_id, [g.group_id for g in subset.large[:L_SAMPLE_GROUPS]])
    guard.sample()
    emit(
        f"total {time.perf_counter() - started:,.0f} s; disk: datadir peak {guard.peak_data / GIB:.2f} GiB, "
        f"host min free {guard.min_free / GIB:.1f} GiB"
    )
    raw.close()
    conn.close()


# ---------------------------------------------------------------- 补测二：C 按 PLAN 写法（C2）、族视图首页完整步骤、服务视图完整路径

C_NODE_ITEMS: str = f"SELECT m.scope_id, m.field_name, m.original_name FROM x1_timeseriesmetric m WHERE {MANAGE_WHERE}"
C_NODE_MEMBERS: str = (
    f"SELECT {PAGE_COLS}{defs(X1)} FROM x1_timeseriesmetric m "
    "WHERE m.group_id = %s AND m.field_scope = 'default' AND m.field_name IN ({marks})"
)
GROUP_ITEMS: dict[str, str] = {
    "A": f"SELECT {INFO_COLS} FROM metadata_timeseriesmetric m WHERE m.group_id = %s AND m.last_modify_time > %s",
    "C2": f"SELECT {INFO_COLS}{defs(X1)} FROM x1_timeseriesmetric m WHERE m.group_id = %s AND m.last_modify_time > %s",
    "D2": f"SELECT {INFO_COLS} FROM metadata_timeseriesmetric m WHERE m.group_id = %s AND m.last_modify_time > %s",
}
# 指标项与定义已整组读入内存，成员只取范围、引用与例外取值，由客户端按引用过滤指标项
SERVICE_MEMBERS: str = (
    f"SELECT s.report_scope_id, s.ref_id, mv.meta, s.field_config FROM {LABEL_TO_MEMBER} "
    f"LEFT JOIN {VALUE_TABLE} mv ON mv.id = s.meta_value_id WHERE {SERVICE_LABEL}"
)
SUPPLEMENT2_SCHEMES: tuple[str, ...] = ("A", "C2", "D2")
EMPTY_CONFIG: tuple[Any, ...] = ("", 0, [])
FIRST_PAGE_LIMIT_MS: float = 150.0


def assemble(rows: Sequence[tuple[Any, Any, Any]]) -> tuple[list[tuple[int, str]], dict[tuple[int, str], list[str]]]:
    """节点键为 (scope_id, 原名或指标名)，按节点键排序取第一页。"""
    nodes: dict[tuple[int, str], list[str]] = {}
    for scope_id, name, original in rows:
        nodes.setdefault((-1 if scope_id is None else int(scope_id), original or name), []).append(name)
    return sorted(nodes)[:PAGE], nodes


def resolve(configs: Sequence[Any], metas: Sequence[Any]) -> int:
    """本页有效配置：定义的上报值打底，用户配置的非空值覆盖，空串、0 与空列表不覆盖。"""
    keys: int = 0
    for config, meta in zip(configs, metas, strict=True):
        merged: dict[str, Any] = (json.loads(meta) if meta else None) or {}
        overrides: dict[str, Any] = (json.loads(config) if config else None) or {}
        merged.update({k: v for k, v in overrides.items() if v not in EMPTY_CONFIG})
        keys += len(merged)
    return keys


def c_search_case(groups: Sequence[int]) -> Case:
    """C2 的搜索：与 A、D2 相同只按指标名匹配，C 的定义在指标项行上，随本页一并读出。"""
    where: str = MANAGE_WHERE + " AND m.field_name LIKE %s"
    tail: str = f" ORDER BY m.field_name LIMIT {PAGE}"
    page_sql: str = f"SELECT {PAGE_COLS}{defs(X1)} FROM x1_timeseriesmetric m WHERE {where}{tail}"

    def run(cur: Cursor, g: int) -> int:
        params: tuple[Any, ...] = (g, catalog.SEARCH)
        fetch(cur, f"SELECT COUNT(*) FROM x1_timeseriesmetric m WHERE {where}", params)
        scope_ids: list[Any] = sorted(
            {r[0] for r in fetch(cur, f"SELECT m.scope_id FROM x1_timeseriesmetric m WHERE {where}{tail}", params)}
            - {None}
        )
        if scope_ids:
            fetch(cur, SCOPE_LOOKUP.replace("{marks}", marks(len(scope_ids))), (*scope_ids, g))
        return len(fetch(cur, page_sql, params))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], page_sql, (groups[0], catalog.SEARCH))


def memory_nodes_case(groups: Sequence[int], scheme: str, stage: str) -> Case:
    """族视图按 PLAN「族在内存中组装」分三段计时：page 为整组读指标项与原名后在客户端归组、排序、分页，
    fill 再补齐本页节点的全部族成员并读本页定义，full 再取本页页面分组名并解析有效配置。"""

    def run(cur: Cursor, g: int) -> int:
        if scheme == "C2":
            rows: Sequence[tuple[Any, Any, Any]] = fetch(cur, C_NODE_ITEMS, (g,))
        else:
            originals: dict[Any, Any] = dict(fetch(cur, NODE_DEFS, (g,)))
            rows = [(s, n, originals.get(n)) for s, n in fetch(cur, NODE_ITEMS, (g,))]
        page, nodes = assemble(rows)
        if stage == "page":
            return len(page)
        wanted: list[str] = sorted({name for key in page for name in nodes[key]})
        params: tuple[Any, ...] = (g, *wanted)
        if scheme == "C2":
            members: tuple[Any, ...] = fetch(cur, C_NODE_MEMBERS.replace("{marks}", marks(len(wanted))), params)
            metas: list[Any] = [r[-1] for r in members]
        else:
            members = fetch(cur, NODE_MEMBERS.replace("{marks}", marks(len(wanted))), params)
            by_name: dict[Any, Any] = {
                r[1]: r[4] for r in fetch(cur, DEF_BY_NAMES.replace("{marks}", marks(len(wanted))), params)
            }
            metas = [by_name.get(r[2]) for r in members]
        if stage == "full":
            scope_ids: list[Any] = sorted({r[1] for r in members} - {None})
            if scope_ids:
                fetch(cur, SCOPE_LOOKUP.replace("{marks}", marks(len(scope_ids))), (*scope_ids, g))
            resolve([r[4] for r in members], metas)
        return len(members)

    return Case(
        [lambda cur, g=g: run(cur, g) for g in groups], C_NODE_ITEMS if scheme == "C2" else NODE_ITEMS, (groups[0],)
    )


def service_path_case(picks: Sequence[Pick], scheme: str) -> Case:
    """服务视图完整路径：整组读指标项与页面分组（C2 含定义列，D2 另读整组定义），再取该服务的成员，客户端按引用过滤。
    A 只做整组读取，现状按 Redis 白名单过滤不计入。"""
    items_sql: str = GROUP_ITEMS[scheme]

    def run(cur: Cursor, p: Pick) -> int:
        items: tuple[Any, ...] = fetch(cur, items_sql, (p.group_id, EXPIRE_BEFORE))
        fetch(cur, GROUP_SCOPES, (p.group_id,))
        if scheme == "A":
            return len(items)
        if scheme == "D2":
            name_of: dict[Any, Any] = {r[0]: r[1] for r in fetch(cur, DEF_BY_GROUP, (p.group_id,))}
            names: set[Any] = {name_of.get(r[1]) for r in fetch(cur, SERVICE_MEMBERS, (p.group_id, p.service))}
            return sum(1 for r in items if r[2] in names)
        refs: set[Any] = {r[1] for r in fetch(cur, SERVICE_MEMBERS, (p.group_id, p.service))}
        return sum(1 for r in items if r[0] in refs)

    first: Pick = picks[0]
    return Case([lambda cur, p=p: run(cur, p) for p in picks], items_sql, (first.group_id, EXPIRE_BEFORE))


def supplement2_budget(tier: str, name: str) -> tuple[int, int]:
    if cfg().smoke:
        return 1, 3
    if tier == "xl" and name == "service_path":
        return 5, 50
    if tier == "xl":
        return 10, 100
    return 30, 300


def report_supplement2(conn: pymysql.Connection, raw: pymysql.Connection, samples: Samples) -> None:
    emit(
        f"## supplement2 probes: XL group {samples.xl}, {len(samples.xl_services)} XL services; "
        f"{len(samples.large)} L groups, {len(samples.l_services)} L services; search term {catalog.SEARCH!r}"
    )
    emit(
        "search: name only for A, C2, D2 (C2 reads definition columns with the page, D2 then reads page definitions); "
        "nodes_page: whole-group read + client-side grouping/sort/page (A: SQL GROUP BY, metric = node); "
        "nodes_fill: + all family members of the page + page definitions (A: + page metrics); "
        "first_page: + page scope names + effective config (A: current management first page); "
        "service_path: whole-group read + definitions + service members (A: whole-group read only); "
        "service_members: the member statement of service_path alone (shared by C2 and D2)"
    )
    emit()
    cases: dict[str, dict[str, Case]] = {}
    for tier, groups, picks in (
        ("xl", samples.xl, samples.xl_services),
        ("l", samples.large, samples.l_services),
    ):
        cases[f"{tier}.search"] = {
            "A": catalog.q1_case(BASE_VARIANT, groups, 0, "m.field_name", True),
            "C2": c_search_case(groups),
            "D2": d_search_case(groups, False),
        }
        cases[f"{tier}.nodes_page"] = {
            "A": a_nodes_case(groups, fill=False),
            "C2": memory_nodes_case(groups, "C2", "page"),
            "D2": memory_nodes_case(groups, "D2", "page"),
        }
        cases[f"{tier}.nodes_fill"] = {
            "A": a_nodes_case(groups),
            "C2": memory_nodes_case(groups, "C2", "fill"),
            "D2": memory_nodes_case(groups, "D2", "fill"),
        }
        cases[f"{tier}.first_page"] = {
            "A": catalog.q1_case(BASE_VARIANT, groups, 0, "m.field_name", False),
            "C2": memory_nodes_case(groups, "C2", "full"),
            "D2": memory_nodes_case(groups, "D2", "full"),
        }
        cases[f"{tier}.service_path"] = {s: service_path_case(picks, s) for s in SUPPLEMENT2_SCHEMES}
        cases[f"{tier}.service_members"] = {
            "D2": statement_case(SERVICE_MEMBERS, [(p.group_id, p.service) for p in picks])
        }
    emit("## supplement2 reads: p50/p95/p99 ms over TCP without type conversion (warmup/runs per line)")
    emit(catalog.STAT_HEADER + f"{'runs':>10}")
    plans: list[str] = []
    for key, by_scheme in cases.items():
        tier, name = key.split(".", 1)
        for scheme in SUPPLEMENT2_SCHEMES:
            case: Case | None = by_scheme.get(scheme)
            if case is None:
                continue
            warmup, runs = supplement2_budget(tier, name)
            label: str = f"{key}.{scheme}"
            log(f"measure {label}")
            stat: Stat = catalog.measure(label, raw, case.runs, seed=key, warmup=warmup, iterations=runs)
            emit(stat.line() + f"{warmup:>4}/{runs:<5}")
            record(key, scheme, statistics.median(stat.samples))
            plans.append(f"{label}: {catalog.explain(conn, case.sql, case.params)}")
    emit()
    emit("## EXPLAIN (table:key/type~rows[flags]; main statement of each case)")
    for plan in plans:
        emit(plan)
    emit()
    p: dict[str, dict[str, float]] = RESULT["p50"]
    emit("## supplement2 ratios (p50): D2/C2, D2/A, C2/A")
    for key in cases:
        row: dict[str, float] = p.get(key, {})
        parts: list[str] = [
            f"{num}/{den} {row[num] / row[den]:.2f}"
            for num, den in (("D2", "C2"), ("D2", "A"), ("C2", "A"))
            if num in row and den in row
        ]
        if parts:
            emit(f"{key:<22}" + ", ".join(parts))
    emit()
    emit(f"## family view first page (XL, p50) against {FIRST_PAGE_LIMIT_MS:.0f} ms")
    for scheme in ("C2", "D2"):
        value: float = p["xl.first_page"][scheme]
        verdict: str = "below" if value < FIRST_PAGE_LIMIT_MS else "over"
        emit(f"{scheme}: {value:.1f} ms, {verdict} the limit, margin {1 - value / FIRST_PAGE_LIMIT_MS:.0%}")
    emit()


def run_supplement2(config: Config, groups: Sequence[Group], subset: Subset, guard: DiskGuard) -> None:
    """只装载第二轮补测需要的数据：全部指标项、扩列与定义，最大数据源与 20 个大型数据源的成员与例外取值。"""
    started: float = time.perf_counter()
    conn: pymysql.Connection = connect()
    raw: pymysql.Connection = connect(raw=True)
    loads: dict[str, float] = {}
    log("load metric items, X1 columns and X3 definitions")
    field_ids, loads["metrics + X1 + X3"] = load_base(conn, groups)
    log("load members and values of the largest group and the sampled L groups")
    loaded: list[Group] = sorted([*subset.xl, *subset.large[:L_SAMPLE_GROUPS]], key=group_key)
    start: float = time.perf_counter()
    stat: LoadStat = load_reports(conn, loaded, field_ids, page_ids_of(groups))
    loads["members + values"] = time.perf_counter() - start
    emit(
        f"loaded: {len(groups):,} groups, {config.metrics:,} metric items; members of {len(loaded)} groups "
        f"{stat.members:,}, scopes {stat.scopes:,}, values {stat.values:,}; load "
        + ", ".join(f"{k} {v:,.0f} s" for k, v in loads.items())
    )
    emit()
    report_supplement2(conn, raw, build_samples(conn, subset))
    guard.sample()
    emit(
        f"total {time.perf_counter() - started:,.0f} s; disk: datadir peak {guard.peak_data / GIB:.2f} GiB, "
        f"host min free {guard.min_free / GIB:.1f} GiB"
    )
    raw.close()
    conn.close()


# ---------------------------------------------------------------- 入口


def run(config: Config, out_path: str | None) -> None:
    CONFIG.append(config)
    if out_path:
        OUT.append(open(os.path.join(ROOT, out_path), "w", encoding="utf-8"))
    groups: list[Group] = catalog.plan_groups(config.scale, config.metrics)
    subset: Subset = select_subset(groups, config.loaded_l)
    loads: dict[str, float] = {}
    started: float = time.perf_counter()
    guard: DiskGuard = DiskGuard()
    try:
        start_server(config)
        guard.start()
        environment(subset, config)
        if config.supplement:
            run_supplement(config, groups, subset, guard)
            return
        if config.supplement2:
            run_supplement2(config, groups, subset, guard)
            return
        if not config.cross_check:
            report_check()
            report_swallow()
        conn: pymysql.Connection = connect()
        raw: pymysql.Connection = connect(raw=True)
        log("load metric items, X1 columns and X3 definitions")
        field_ids, loads["metrics + X1 + X3"] = load_base(conn, groups)
        pages: dict[int, list[int]] = page_ids_of(groups)
        log("load scopes, labels, members, values and B rows")
        start: float = time.perf_counter()
        stat: LoadStat = load_reports(conn, subset.groups, field_ids, pages)
        loads["scopes + members + values + B"] = time.perf_counter() - start
        emit(
            f"loaded: {len(groups):,} groups, {config.metrics:,} metric items; members {stat.members:,}, scopes {stat.scopes:,}, "
            f"values {stat.values:,}, B rows {stat.b_rows:,}; load "
            + ", ".join(f"{k} {v:,.0f} s" for k, v in loads.items())
        )
        emit()
        active: Targets = targets_of(catalog.plan_groups("m1" if not config.smoke else config.scale, config.metrics))
        upper: Targets = targets_of(groups)
        loaded: Targets = targets_of(subset.groups)
        RESULT["targets"] = {"loaded": loaded, "active": active, "upper": upper}
        if not config.cross_check:
            report_volume(conn, loaded, active, upper)
        samples: Samples = build_samples(conn, subset)
        emit(
            f"samples: XL groups {samples.xl}, {len(samples.xl_services)} XL services, hottest {[p.service for p in samples.hot]}, "
            f"{len(samples.large)} L groups, {len(samples.l_services)} L services"
        )
        emit()
        report_reads(conn, raw, "xl", build_cases("xl", samples.xl, samples.xl_services, samples.hot))
        report_reads(conn, raw, "l", build_cases("l", samples.large, samples.l_services, []))
        if not config.cross_check:
            report_counters(conn, samples.xl[0])
        report_scan(conn, raw, stat.b_rows, active, upper)
        if not config.cross_check:
            report_apply(conn, raw, subset, pages)
            report_refresh(conn, raw, samples.xl[0])
            report_ddl(conn, groups)
            report_rollback(conn, groups, active, upper)
            report_compare()
        loads["total run"] = time.perf_counter() - started
        report_summary(guard, loads)
        raw.close()
        conn.close()
    finally:
        if not os.environ.get("PLANS57_KEEP"):
            remove_server()
            log("container and volume removed")
        for fp in OUT:
            fp.close()


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(dest="command", required=True)
    run_parser: argparse.ArgumentParser = commands.add_parser("run")
    run_parser.add_argument("--smoke", action="store_true")
    run_parser.add_argument("--out")
    run_parser.add_argument("--buffer-pool", default="8G")
    run_parser.add_argument(
        "--cross-check",
        action="store_true",
        help="只装载 A/C/D 并复测读取与全平台扫描，配合 IMAGE_57、PLATFORM_57 换镜像",
    )
    run_parser.add_argument(
        "--supplement", action="store_true", help="补测管理页搜索、族视图节点分页与单范围读取，只装载所需数据"
    )
    run_parser.add_argument(
        "--supplement2",
        action="store_true",
        help="补测 C 按 PLAN 写法（C2）、族视图首页完整步骤与服务视图完整路径，只装载所需数据",
    )
    commands.add_parser("clean")
    args: argparse.Namespace = parser.parse_args()
    if args.command == "clean":
        remove_server()
        print(f"removed container {CONTAINER} and volume {VOLUME}")
        return
    config: Config = Config(
        smoke=args.smoke,
        scale=SMOKE_SCALE if args.smoke else SCALE,
        metrics=SMOKE_METRICS if args.smoke else 1_000_000,
        loaded_l=5 if args.smoke else LOADED_L,
        buffer_pool="1G" if args.smoke else args.buffer_pool,
        log_file="256M" if args.smoke else "1G",
        cross_check=args.cross_check,
        supplement=args.supplement,
        supplement2=args.supplement2,
    )
    run(config, args.out)


if __name__ == "__main__":
    main()
