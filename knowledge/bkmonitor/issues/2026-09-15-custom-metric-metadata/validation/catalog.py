#!/usr/bin/env python3
"""自定义指标元信息目录基准。

全平台 1,000,000 个指标项，上报成员 M1 约 10,000,000 行、M2 约 40,000,000 行，比较元信息定义的三种存储：
X1 在指标项表加列，X2 按 field_id 一对一扩展表，X3 按 (group_id, field_name) 独立定义表。
上报范围、标签倒排与成员表三者共用一份数据，成员 ref_id 对 X1/X2 是 field_id，对 X3 是定义 id，合成数据中两者相等。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import shutil
import statistics
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from typing import Any

import pymysql
from pymysql.cursors import Cursor, DictCursor

from bench import (
    LOAD_CHUNK_ROWS,
    Loader,
    apm_raw_scope,
    connect,
    environment,
    execute,
    fetch,
    md5_hex,
    mib,
    reset,
    source_key,
    table_sizes,
)

GIB: int = 1024**3
BASE: dt.datetime = dt.datetime(2026, 10, 11)
NOW: str = "2026-10-11 00:00:00.000000"
CREATE_TIME: str = "2026-03-01 00:00:00.000000"
# TIME_SERIES_METRIC_EXPIRED_SECONDS = 30 d，指标项与成员共用同一过期窗口
EXPIRE_BEFORE: str = "2026-09-11 00:00:00"
# 活跃时间均匀分布在最近 24 h，Apply 只刷新早于 21.6 h 的行，约占 10%
STALE_BEFORE: str = "2026-10-10 02:24:00"
STAMPS: int = 4096
WARMUP: int = 30
ITERATIONS: int = 300
PAGE: int = 50
DEEP_OFFSET: int = 10_000
SEARCH: str = "%retry%"
GROUP_CHUNK: int = 500
SCAN_CHUNKS: tuple[int, ...] = (2_000, 10_000)
SCAN_REPEATS: int = 3
APPLY_BATCH: int = 1_000
APPLY_NEW: int = 11
APPLY_CHANGED: int = 5
MIXED_GROUPS: int = 20
COMPACT_BATCH: int = 1_000
COMPACT_SCAN: int = 10_000
L_SAMPLE_GROUPS: int = 20
XL_SERVICES: int = 10
L_SERVICES: int = 5
LEGACY_EVERY: int = 20
LATER_PERCENT: int = 30
CUSTOM_EVERY: int = 4
EXPIRED_SHARE: float = 0.02
EXCEPTION_SHARE: float = 0.01
OVERRIDE_SHARE: float = 0.001
MIN_FREE: int = 3 * GIB
MAX_DATADIR: int = 14 * GIB


@dataclass(frozen=True)
class Tier:
    name: str
    groups: int
    metrics: int
    services: int
    members: int
    pages: int


# L、M、S 取自 bkte 实测，成员 = 指标 × 服务 × 实测密度（0.717、0.810、0.657）；XS 是只有 2 个服务的小应用，groups=0 表示补足剩余指标。
# M1 按 15 min 活跃服务数；M2 按 30 d 登记服务数，L 取实测 126，M、S 翻倍，并提高 L 的占比以达到约 40,000,000 行。
TIERS: dict[str, tuple[Tier, ...]] = {
    "m1": (
        Tier("XL", 5, 20_000, 667, 1_000_000, 40),
        Tier("L", 600, 221, 28, 4_437, 4),
        Tier("M", 2_000, 145, 6, 705, 3),
        Tier("S", 3_000, 83, 4, 218, 2),
        Tier("XS", 0, 111, 2, 111, 1),
    ),
    "m2": (
        Tier("XL", 5, 20_000, 667, 1_000_000, 40),
        Tier("L", 1_550, 221, 126, 19_966, 4),
        Tier("M", 2_000, 145, 12, 1_409, 3),
        Tier("S", 3_000, 83, 8, 436, 2),
        Tier("XS", 0, 111, 2, 111, 1),
    ),
}

DIMENSIONS: tuple[str, ...] = (
    "app_name",
    "service_name",
    "scope_name",
    "instance",
    "namespace",
    "pod",
    "container",
    "node",
    "bcs_cluster_id",
    "bk_target_ip",
    "callee_method",
    "callee_service",
    "callee_server",
    "caller_service",
    "caller_method",
    "caller_server",
    "code",
    "code_type",
    "env",
    "region",
    "zone",
    "version",
    "telemetry_sdk_language",
    "telemetry_sdk_version",
    "service_version",
    "host_name",
    "process_pid",
    "net_peer_name",
    "http_method",
    "http_route",
    "http_status_code",
    "rpc_system",
)
# 搜索词 retry 命中 rpc_client_retry_total 与描述中的 retry，约占指标的 5%
METRIC_STEMS: tuple[str, ...] = (
    "trpc_client_handled_total",
    "trpc_server_handled_total",
    "rpc_client_retry_total",
    "go_memstats_heap_alloc_bytes",
    "process_resident_memory_bytes",
    "process_cpu_seconds_total",
    "ActsLotteryDrawFailTotal",
    "LockFailLoginCount",
    "timer_task_executed_total",
    "kafka_consumer_lag",
    "redis_pool_active_connections",
    "mysql_pool_idle_connections",
    "http_requests_total",
    "grpc_server_started_total",
    "cache_hit_total",
    "cache_miss_total",
    "queue_depth",
    "goroutines",
    "gc_pause_seconds_total",
    "order_created_total",
    "payment_failed_total",
    "login_success_total",
    "reward_claimed_total",
    "match_queue_size",
    "room_online_players",
    "db_slow_query_total",
    "circuit_breaker_open",
    "rate_limit_rejected_total",
)
HISTOGRAM_STEMS: tuple[str, ...] = (
    "trpc_server_handled_seconds",
    "trpc_client_handled_seconds",
    "http_server_request_duration_seconds",
    "db_query_duration_seconds",
    "redis_command_duration_seconds",
    "timer_task_duration_seconds",
    "kafka_produce_latency_seconds",
    "match_wait_seconds",
)
HISTOGRAM_SUFFIXES: tuple[str, ...] = ("_bucket", "_sum", "_count")
DESC_WORDS: tuple[str, ...] = (
    "inbound",
    "outbound",
    "lottery",
    "login",
    "payment",
    "matchmaking",
    "activity",
    "reward",
    "retry",
    "timeout",
    "cache",
    "storage",
    "gateway",
    "backend",
    "frontend",
    "batch",
    "stream",
    "cron",
    "admin",
    "public",
    "internal",
    "mobile",
    "desktop",
    "region",
    "shard",
    "replica",
    "primary",
    "standby",
    "canary",
    "stable",
    "legacy",
    "beta",
    "trial",
    "premium",
    "free",
    "guest",
    "vip",
    "season",
    "event",
    "weekly",
)
UNITS: dict[str, str] = {"histogram": "s", "counter": "1", "gauge": "bytes"}
KIND_TEXT: dict[str, str] = {"histogram": "Latency distribution", "counter": "Total count", "gauge": "Current value"}
USAGES: dict[str, str] = {"histogram": "latency", "counter": "throughput", "gauge": "saturation"}
DIMENSION_CONFIG: str = json.dumps({"service_name": {"common": True}, "instance": {"hidden": False}})
EXCEPTION_JSON: str = json.dumps({"unit": "ms", "description": "reported by legacy sdk in milliseconds"})
OVERRIDE_JSON: str = json.dumps({"unit": "ms", "alias": "按范围覆盖"}, ensure_ascii=False)


def stamp(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S.%f")


FRESH: tuple[str, ...] = tuple(stamp(BASE - dt.timedelta(seconds=86_400 * (i + 0.5) / STAMPS)) for i in range(STAMPS))
EXPIRED: tuple[str, ...] = tuple(stamp(BASE - dt.timedelta(days=40, seconds=97 * i)) for i in range(256))


def emit(line: str = "") -> None:
    print(line, flush=True)


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def marks(count: int) -> str:
    return ", ".join(["%s"] * count)


def percentile(values: Sequence[float], p: float) -> float:
    ordered: list[float] = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


# ---------------------------------------------------------------- 数据画像


def is_legacy(idx: int) -> bool:
    """旧指标：早于新 Collector 发现，没有元信息与成员。"""
    return idx % LEGACY_EVERY == LEGACY_EVERY - 1


def scope_name_of(idx: int) -> str:
    return "custom" if (idx // 10) % CUSTOM_EVERY == CUSTOM_EVERY - 1 else "default"


def metric_kind(idx: int) -> str:
    pos: int = idx % 10
    return "histogram" if pos < 3 else "counter" if pos < 7 else "gauge"


def metric_names(idx: int) -> tuple[str, str]:
    """每 10 个指标中前 3 个是同一 Histogram 拆出的 _bucket、_sum、_count，共用原名，其余原名即指标名。"""
    block, pos = divmod(idx, 10)
    if pos < 3:
        base: str = f"{HISTOGRAM_STEMS[block % len(HISTOGRAM_STEMS)]}_{block:04d}"
        return base + HISTOGRAM_SUFFIXES[pos], base
    name: str = f"{METRIC_STEMS[(block * 7 + pos) % len(METRIC_STEMS)]}_{idx:05d}"
    return name, name


def definition_meta(group_id: int, idx: int, field_name: str, original_name: str) -> str:
    kind: str = metric_kind(idx)
    word: str = DESC_WORDS[(idx * 13 + group_id) % len(DESC_WORDS)]
    meta: dict[str, Any] = {
        "unit": UNITS[kind],
        "description": f"{KIND_TEXT[kind]} of {original_name.replace('_', ' ')} for {word} traffic",
        "temporality": "" if kind == "gauge" else "cumulative",
        "interval": 60,
        "usage": USAGES[kind],
    }
    if kind == "histogram":
        meta["sub_item"] = field_name[len(original_name) + 1 :]
    return json.dumps(meta)


@cache
def tag_list_json(count: int, start: int) -> str:
    return json.dumps([DIMENSIONS[(start + k) % len(DIMENSIONS)] for k in range(count)])


def tag_count(group_id: int, idx: int) -> int:
    """维度数在 10 至 24 之间均匀分布，平均 17 个（bkte 实测）。"""
    return 10 + (idx * 7 + group_id) % 15


def tag_list(group_id: int, idx: int) -> str:
    return tag_list_json(tag_count(group_id, idx), (idx + group_id) % len(DIMENSIONS))


def field_config(group_id: int, idx: int) -> str:
    if (idx * 31 + group_id) % 10:
        return "{}"
    return json.dumps({"unit": "ms", "alias": f"指标{idx}"}, ensure_ascii=False)


def last_modify(group_id: int, idx: int) -> str:
    if (idx * 17 + group_id) % 100 < 3:
        return EXPIRED[idx % len(EXPIRED)]
    return FRESH[(idx * 2_654_435_761 + group_id) % STAMPS]


def page_names(pages: int) -> list[str]:
    return ["default", "custom", *[f"page_{k:02d}" for k in range(2, pages)]][:pages]


def page_of(idx: int, pages: int) -> int:
    """APM 页面分组以 scope_name 命名，custom 指标进入 custom 分组，default 指标分散到 default 与用户分组。"""
    if pages == 1:
        return 0
    if scope_name_of(idx) == "custom":
        return 1
    k: int = (idx // 10) % (pages - 1)
    return 0 if k == 0 else k + 1


def has_custom(service_idx: int) -> bool:
    """每个服务都有 scope_name=default 的上报范围，偶数号服务另有 custom，平均 1.5 个范围。"""
    return service_idx % 2 == 0


def service_name(group_id: int, service_idx: int) -> str:
    return f"app{group_id:05d}-svc-{service_idx:03d}"


@dataclass(frozen=True)
class Shape:
    default: tuple[int, ...]
    custom: tuple[int, ...]
    density: tuple[float, ...]

    def eligible(self, service_idx: int) -> int:
        return len(self.default) + (len(self.custom) if has_custom(service_idx) else 0)


@cache
def shape_of(metrics: int, services: int, members: int) -> Shape:
    """服务按热度排名，上报概率为 c × (0.05 + 1/√rank) 并截断到 1，二分 c 使期望成员数等于目标。"""
    live: list[int] = [i for i in range(metrics) if not is_legacy(i)]
    default: tuple[int, ...] = tuple(i for i in live if scope_name_of(i) == "default")
    custom: tuple[int, ...] = tuple(i for i in live if scope_name_of(i) == "custom")
    weights: list[float] = [0.05 + 1 / math.sqrt(j + 1) for j in range(services)]
    eligible: list[int] = [len(default) + (len(custom) if has_custom(j) else 0) for j in range(services)]
    low: float = 0.0
    high: float = 1e6
    for _ in range(100):
        mid: float = (low + high) / 2
        if sum(min(1.0, mid * w) * e for w, e in zip(weights, eligible)) < members:
            low = mid
        else:
            high = mid
    return Shape(default, custom, tuple(min(1.0, high * w) for w in weights))


@dataclass(frozen=True)
class Group:
    group_id: int
    tier: Tier
    metrics: int
    members: int

    @property
    def shape(self) -> Shape:
        return shape_of(self.metrics, self.tier.services, self.members)

    def scopes(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for j in range(self.tier.services):
            result.append((service_name(self.group_id, j), "default"))
            if has_custom(j):
                result.append((service_name(self.group_id, j), "custom"))
        return result

    def member_lists(self) -> Iterator[tuple[int, list[int]]]:
        """按上报范围顺序给出 (范围序号, 已排序的指标下标)，同一分组每次生成的结果一致。"""
        shape: Shape = self.shape
        rng: random.Random = random.Random(self.group_id * 1_000_003 + 7)
        offset: int = 0
        for j in range(self.tier.services):
            for pool in (shape.default, shape.custom) if has_custom(j) else (shape.default,):
                take: int = round(shape.density[j] * len(pool))
                yield offset, sorted(rng.sample(pool, take)) if take < len(pool) else list(pool)
                offset += 1


def plan_groups(scale: str, total_metrics: int) -> list[Group]:
    factor: float = total_metrics / 1_000_000
    entries: list[tuple[Tier, int]] = []
    fill: Tier | None = None
    for tier in TIERS[scale]:
        if tier.groups == 0:
            fill = tier
            continue
        entries.extend((tier, tier.metrics) for _ in range(max(1, round(tier.groups * factor))))
    rest: int = total_metrics - sum(n for _, n in entries)
    if fill is None or rest < 0:
        raise ValueError(f"--metrics {total_metrics} is too small for scale {scale}")
    full, tail = divmod(rest, fill.metrics)
    entries.extend((fill, fill.metrics) for _ in range(full))
    if tail:
        entries.append((fill, tail))
    random.Random(f"{scale}-groups").shuffle(entries)
    return [Group(i + 1, tier, n, round(tier.members * n / tier.metrics)) for i, (tier, n) in enumerate(entries)]


def metric_order(groups: Sequence[Group]) -> Iterator[tuple[Group, int]]:
    """70% 的指标在分组首次上报时集中创建，其余 30% 之后陆续创建，field_id 与其他分组交错。"""
    later: list[tuple[int, int]] = []
    for pos, g in enumerate(groups):
        for idx in range(g.metrics):
            if (idx * 2_654_435_761 + g.group_id) % 100 < LATER_PERCENT:
                later.append((pos, idx))
            else:
                yield g, idx
    random.Random(17).shuffle(later)
    for pos, idx in later:
        yield groups[pos], idx


# ---------------------------------------------------------------- 表结构


METRIC_COLUMNS: str = """
    field_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    group_id INT NOT NULL,
    scope_id INT NULL,
    table_id VARCHAR(255) NOT NULL,
    field_scope VARCHAR(255) COLLATE utf8mb3_bin NOT NULL,
    field_name VARCHAR(255) COLLATE utf8mb3_bin NOT NULL,
    tag_list LONGTEXT NOT NULL,
    field_config JSON NOT NULL,
    create_time DATETIME(6) NULL,
    last_modify_time DATETIME(6) NOT NULL,
    label VARCHAR(255) NOT NULL,
    is_active TINYINT(1) NOT NULL,
    last_index INT NOT NULL"""
METRIC_INDEXES: str = """
    UNIQUE KEY uk_group_scope_name (group_id, field_scope, field_name),
    KEY idx_group (group_id),
    KEY idx_scope (scope_id),
    KEY idx_label (label),
    KEY idx_active (is_active),
    KEY idx_group_scope_field (group_id, scope_id, field_name)"""
X1_COLUMNS: str = """
    original_name VARCHAR(255) COLLATE utf8mb3_bin NULL,
    metric_type VARCHAR(16) NULL,
    meta JSON NULL,
    meta_fingerprint CHAR(32) NULL,
    meta_seen_at DATETIME(6) NULL"""
META_COLUMNS: str = """
    original_name VARCHAR(255) COLLATE utf8mb3_bin NOT NULL,
    metric_type VARCHAR(16) NOT NULL,
    meta JSON NOT NULL,
    fingerprint CHAR(32) NOT NULL,
    seen_at DATETIME(6) NOT NULL"""
MEMBER_COLUMNS: str = """
    group_id INT NOT NULL,
    report_scope_id BIGINT NOT NULL,
    ref_id BIGINT NOT NULL,
    last_seen DATETIME(6) NOT NULL,
    meta JSON NULL,
    field_config JSON NULL"""
DDL: dict[str, str] = {
    "metadata_timeseriesscope": """CREATE TABLE metadata_timeseriesscope (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        scope_name VARCHAR(255) COLLATE utf8mb3_bin NOT NULL,
        dimension_config JSON NOT NULL,
        auto_rules JSON NOT NULL,
        create_from VARCHAR(10) NOT NULL,
        last_modify_time DATETIME(6) NOT NULL,
        UNIQUE KEY uk_group_scope (group_id, scope_name),
        KEY idx_group (group_id),
        KEY idx_create_from (create_from)
    ) DEFAULT CHARSET=utf8mb3""",
    "metadata_timeseriesmetric": f"""CREATE TABLE metadata_timeseriesmetric ({METRIC_COLUMNS},{METRIC_INDEXES}
    ) DEFAULT CHARSET=utf8mb3""",
    "x1_timeseriesmetric": f"""CREATE TABLE x1_timeseriesmetric ({METRIC_COLUMNS},{X1_COLUMNS},{METRIC_INDEXES},
        KEY idx_group_original (group_id, original_name)
    ) DEFAULT CHARSET=utf8mb3""",
    "x2_metric_meta": f"""CREATE TABLE x2_metric_meta (
        field_id INT NOT NULL PRIMARY KEY,
        group_id INT NOT NULL,{META_COLUMNS},
        KEY idx_group_original (group_id, original_name)
    ) DEFAULT CHARSET=utf8mb3""",
    "x3_metric_meta": f"""CREATE TABLE x3_metric_meta (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        field_name VARCHAR(255) COLLATE utf8mb3_bin NOT NULL,{META_COLUMNS},
        UNIQUE KEY uk_group_name (group_id, field_name),
        KEY idx_group_original (group_id, original_name)
    ) DEFAULT CHARSET=utf8mb3""",
    "report_scope": """CREATE TABLE report_scope (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        scope_type VARCHAR(16) NOT NULL,
        scope_hash CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        raw_scope VARCHAR(512) NOT NULL,
        labels JSON NOT NULL,
        last_seen DATETIME(6) NOT NULL,
        UNIQUE KEY uk_group_hash (group_id, scope_hash)
    ) DEFAULT CHARSET=utf8mb3""",
    "report_scope_label": """CREATE TABLE report_scope_label (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        label_key VARCHAR(64) NOT NULL,
        label_value VARCHAR(255) NOT NULL,
        report_scope_id BIGINT NOT NULL,
        UNIQUE KEY uk_label (group_id, label_key, label_value, report_scope_id)
    ) DEFAULT CHARSET=utf8mb3""",
    "report_member": f"""CREATE TABLE report_member (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,{MEMBER_COLUMNS},
        UNIQUE KEY uk_member (group_id, report_scope_id, ref_id),
        KEY idx_group_ref (group_id, ref_id)
    ) DEFAULT CHARSET=utf8mb3""",
    "report_member_pk": f"""CREATE TABLE report_member_pk ({MEMBER_COLUMNS},
        PRIMARY KEY (group_id, report_scope_id, ref_id),
        KEY idx_group_ref (group_id, ref_id)
    ) DEFAULT CHARSET=utf8mb3""",
}
METRIC_LOAD: list[str] = [
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
META_LOAD: list[str] = ["original_name", "metric_type", "meta", "fingerprint", "seen_at"]
MEMBER_LOAD: list[str] = ["group_id", "report_scope_id", "ref_id", "last_seen", "meta", "field_config"]
LOAD_COLUMNS: dict[str, list[str]] = {
    "metadata_timeseriesscope": [
        "id",
        "group_id",
        "scope_name",
        "dimension_config",
        "auto_rules",
        "create_from",
        "last_modify_time",
    ],
    "metadata_timeseriesmetric": METRIC_LOAD,
    "x1_timeseriesmetric": [*METRIC_LOAD, "original_name", "metric_type", "meta", "meta_fingerprint", "meta_seen_at"],
    "x2_metric_meta": ["field_id", "group_id", *META_LOAD],
    "x3_metric_meta": ["id", "group_id", "field_name", *META_LOAD],
    "report_scope": ["id", "group_id", "scope_type", "scope_hash", "raw_scope", "labels", "last_seen"],
    "report_scope_label": ["id", "group_id", "label_key", "label_value", "report_scope_id"],
    "report_member": ["id", *MEMBER_LOAD],
    "report_member_pk": MEMBER_LOAD,
}
METRIC_TABLES: list[str] = [
    "metadata_timeseriesscope",
    "metadata_timeseriesmetric",
    "x1_timeseriesmetric",
    "x2_metric_meta",
    "x3_metric_meta",
]
SHARED_TABLES: list[str] = ["report_scope", "report_scope_label", "report_member"]
CANDIDATES: dict[str, list[str]] = {
    "X1 列扩展": ["x1_timeseriesmetric", *SHARED_TABLES],
    "X2 一对一扩展表": ["metadata_timeseriesmetric", "x2_metric_meta", *SHARED_TABLES],
    "X3 独立定义表": ["metadata_timeseriesmetric", "x3_metric_meta", *SHARED_TABLES],
}


# ---------------------------------------------------------------- 磁盘看门狗


class DiskGuard(threading.Thread):
    """每 2 s 检查剩余空间与数据目录体积，越过阈值立即退出，由 run.sh 关闭实例。"""

    def __init__(self, datadir: str) -> None:
        super().__init__(daemon=True)
        self.datadir = datadir
        self.peak: int = 0
        self.min_free: int = shutil.disk_usage(datadir).free

    def sample(self) -> tuple[int, int]:
        used: int = 0
        for root, _, files in os.walk(self.datadir):
            for name in files:
                try:
                    used += os.stat(os.path.join(root, name)).st_blocks * 512
                except FileNotFoundError:
                    continue
        free: int = shutil.disk_usage(self.datadir).free
        self.peak = max(self.peak, used)
        self.min_free = min(self.min_free, free)
        return used, free

    def require(self, need: int, what: str) -> None:
        used, free = self.sample()
        if free - need < MIN_FREE or used + need > MAX_DATADIR:
            log(
                f"abort before {what}: need {need / GIB:.1f} GiB, free {free / GIB:.1f} GiB, datadir {used / GIB:.1f} GiB"
            )
            os._exit(75)

    def run(self) -> None:
        while True:
            time.sleep(2)
            used, free = self.sample()
            if free < MIN_FREE or used > MAX_DATADIR:
                log(f"abort: free {free / GIB:.1f} GiB, datadir {used / GIB:.1f} GiB")
                os._exit(75)


# ---------------------------------------------------------------- 装载


class LineLoader(Loader):
    def add_line(self, line: str) -> None:
        self.rows.append(line)
        if len(self.rows) >= LOAD_CHUNK_ROWS:
            self.flush()


@dataclass
class TierStat:
    groups: int = 0
    metrics: int = 0
    scopes: int = 0
    members: int = 0
    largest: int = 0


def load_metrics(conn: pymysql.Connection, groups: Sequence[Group]) -> tuple[dict[int, list[int]], float]:
    """页面分组、指标项、X1 指标项与两种定义表在同一遍生成中装载，返回每个分组按指标下标排列的 field_id 与平均维度数。"""
    loaders: dict[str, Loader] = {t: Loader(conn, t, LOAD_COLUMNS[t]) for t in METRIC_TABLES}
    page_ids: dict[int, list[int]] = {}
    page_id: int = 0
    for g in groups:
        ids: list[int] = []
        for name in page_names(g.tier.pages):
            page_id += 1
            ids.append(page_id)
            create_from: str = "default" if name == "default" else "data"
            loaders["metadata_timeseriesscope"].add(
                [page_id, g.group_id, name, DIMENSION_CONFIG, "[]", create_from, NOW]
            )
        page_ids[g.group_id] = ids
    field_ids: dict[int, list[int]] = {g.group_id: [0] * g.metrics for g in groups}
    field_id: int = 0
    tags: int = 0
    for g, idx in metric_order(groups):
        field_id += 1
        field_ids[g.group_id][idx] = field_id
        field_name, original_name = metric_names(idx)
        tags += tag_count(g.group_id, idx)
        base: list[Any] = [
            field_id,
            g.group_id,
            page_ids[g.group_id][page_of(idx, g.tier.pages)],
            f"{g.group_id}_bkmonitor_time_series_{500_000 + g.group_id}.{field_name}",
            "default",
            field_name,
            tag_list(g.group_id, idx),
            field_config(g.group_id, idx),
            CREATE_TIME,
            last_modify(g.group_id, idx),
            "",
            1,
            0,
        ]
        loaders["metadata_timeseriesmetric"].add(base)
        if is_legacy(idx):
            loaders["x1_timeseriesmetric"].add([*base, None, None, None, None, None])
            continue
        kind: str = metric_kind(idx)
        meta: str = definition_meta(g.group_id, idx, field_name, original_name)
        fingerprint: str = md5_hex(meta)
        seen_at: str = FRESH[(field_id * 2_654_435_761) % STAMPS]
        loaders["x1_timeseriesmetric"].add([*base, original_name, kind, meta, fingerprint, seen_at])
        loaders["x2_metric_meta"].add([field_id, g.group_id, original_name, kind, meta, fingerprint, seen_at])
        loaders["x3_metric_meta"].add(
            [field_id, g.group_id, field_name, original_name, kind, meta, fingerprint, seen_at]
        )
    for loader in loaders.values():
        loader.flush()
    return field_ids, tags / max(1, field_id)


def load_members(
    conn: pymysql.Connection,
    groups: Sequence[Group],
    field_ids: dict[int, list[int]],
    table: str,
    with_scopes: bool,
) -> dict[str, TierStat]:
    """成员按 (group, 范围, 指标) 顺序生成，两次装载的行完全一致；范围与标签只在 with_scopes 时写入。"""
    with_id: bool = table == "report_member"
    members: LineLoader = LineLoader(conn, table, LOAD_COLUMNS[table])
    scopes: Loader = Loader(conn, "report_scope", LOAD_COLUMNS["report_scope"])
    labels: Loader = Loader(conn, "report_scope_label", LOAD_COLUMNS["report_scope_label"])
    stats: dict[str, TierStat] = {}
    scope_id: int = 0
    label_id: int = 0
    member_id: int = 0
    tail: float = 1 - EXPIRED_SHARE
    for g in groups:
        first_scope: int = scope_id + 1
        group_scopes: list[tuple[str, str]] = g.scopes()
        for service, scope_name in group_scopes:
            scope_id += 1
            if not with_scopes:
                continue
            scope_labels: dict[str, str] = {"scope_name": scope_name, "service_name": service}
            scopes.add(
                [
                    scope_id,
                    g.group_id,
                    "APM",
                    md5_hex(source_key(scope_labels)),
                    apm_raw_scope(service, scope_name),
                    json.dumps(scope_labels),
                    FRESH[(scope_id * 2_654_435_761) % STAMPS],
                ]
            )
            for label_key in ("scope_name", "service_name"):
                label_id += 1
                labels.add([label_id, g.group_id, label_key, scope_labels[label_key], scope_id])
        rng: random.Random = random.Random(g.group_id * 7_919 + 3)
        ids: list[int] = field_ids[g.group_id]
        count: int = 0
        for offset, picked in g.member_lists():
            head: str = f"{g.group_id}\t{first_scope + offset}\t"
            for idx in picked:
                member_id += 1
                seen: float = rng.random()
                extra: float = rng.random()
                last_seen: str = (
                    EXPIRED[member_id & 255]
                    if seen < EXPIRED_SHARE
                    else FRESH[min(STAMPS - 1, int((seen - EXPIRED_SHARE) / tail * STAMPS))]
                )
                meta: str = EXCEPTION_JSON if extra < EXCEPTION_SHARE else r"\N"
                config: str = OVERRIDE_JSON if extra > 1 - OVERRIDE_SHARE else r"\N"
                line: str = f"{head}{ids[idx]}\t{last_seen}\t{meta}\t{config}"
                members.add_line(f"{member_id}\t{line}" if with_id else line)
            count += len(picked)
        stat: TierStat = stats.setdefault(g.tier.name, TierStat())
        stat.groups += 1
        stat.metrics += g.metrics
        stat.scopes += len(group_scopes)
        stat.members += count
        stat.largest = max(stat.largest, count)
    for loader in (members, scopes, labels):
        loader.flush()
    return stats


def analyze(conn: pymysql.Connection, tables: Iterable[str]) -> None:
    for table in tables:
        execute(conn, f"ANALYZE TABLE {table}")


def index_sizes(conn: pymysql.Connection, table: str) -> dict[str, int]:
    rows: tuple[Any, ...] = execute(
        conn,
        "SELECT index_name, stat_value FROM mysql.innodb_index_stats "
        "WHERE database_name = 'cm_bench' AND table_name = %s AND stat_name = 'size'",
        (table,),
    )
    return {name: int(pages) * 16_384 for name, pages in rows}


# ---------------------------------------------------------------- 计时与执行计划


Run = Callable[[Cursor], int]


@dataclass
class Stat:
    name: str
    samples: list[float] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)
    reads: int = 0

    def line(self) -> str:
        return (
            f"{self.name:<30}{statistics.median(self.samples):>10.3f}{percentile(self.samples, 0.95):>10.3f}"
            f"{percentile(self.samples, 0.99):>10.3f}{statistics.mean(self.rows):>10.1f}{self.reads:>10,}"
        )


STAT_HEADER: str = f"{'case':<30}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'rows':>10}{'disk rd':>10}"


@dataclass
class Case:
    runs: list[Run]
    sql: str
    params: tuple[Any, ...]


def pool_reads(conn: pymysql.Connection) -> int:
    return int(execute(conn, "SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_reads'")[0][1])


def measure(
    name: str,
    conn: pymysql.Connection,
    runs: Sequence[Run],
    seed: str,
    warmup: int | None = None,
    iterations: int | None = None,
) -> Stat:
    """同一 seed 的各候选使用相同的请求序列；disk rd 为期间缓冲池未命中的页读次数。"""
    warm: int = WARMUP if warmup is None else warmup
    total: int = ITERATIONS if iterations is None else iterations
    stat: Stat = Stat(name)
    rng: random.Random = random.Random(seed)
    before: int = pool_reads(conn)
    with conn.cursor() as cur:
        for i in range(warm + total):
            run: Run = runs[rng.randrange(len(runs))]
            start: float = time.perf_counter()
            rows: int = run(cur)
            elapsed: float = (time.perf_counter() - start) * 1000
            if i >= warm:
                stat.samples.append(elapsed)
                stat.rows.append(rows)
    stat.reads = pool_reads(conn) - before
    return stat


EXTRA_FLAGS: tuple[tuple[str, str], ...] = (
    ("Using filesort", "filesort"),
    ("Using temporary", "temporary"),
    ("Using index condition", "icp"),
    ("Using index for group-by", "group-by-index"),
    ("Using index", "covering"),
    ("Using join buffer", "join-buffer"),
    ("Using union", "union"),
    ("Using sort_union", "sort-union"),
    ("Using MRR", "mrr"),
)


def explain(conn: pymysql.Connection, sql: str, params: Sequence[Any]) -> str:
    """table:key/type~rows[flags]，key 为 ALL 表示全表扫描。"""
    with conn.cursor(DictCursor) as cur:
        cur.execute("EXPLAIN " + sql, params)
        plans: list[dict[str, Any]] = list(cur.fetchall())
    parts: list[str] = []
    for p in plans:
        flags: list[str] = []
        for token in (p.get("Extra") or "").split("; "):
            for prefix, flag in EXTRA_FLAGS:
                if token.startswith(prefix):
                    flags.append(flag)
                    break
        suffix: str = f"[{','.join(flags)}]" if flags else ""
        parts.append(f"{p['table']}:{p['key'] or 'ALL'}/{p['type']}~{p['rows']}{suffix}")
    return "; ".join(parts)


# ---------------------------------------------------------------- 查询


@dataclass(frozen=True)
class Variant:
    """source 中指标项别名 m，定义别名 d（X1 定义在 m 上）；member_join 从成员 s 关联到 m 与 d。"""

    name: str
    metric: str
    source: str
    d: str = ""
    ref: str = ""
    member_join: str = ""
    family: str = ""
    ref_from: str = ""
    ref_col: str = ""
    ref_where: str = ""
    node: str = ""


BY_NAME: str = "r.group_id = %s AND r.field_scope = 'default' AND r.field_name = %s"
BASE_VARIANT: Variant = Variant("base", "metadata_timeseriesmetric", "metadata_timeseriesmetric m")
X1: Variant = Variant(
    "x1",
    "x1_timeseriesmetric",
    "x1_timeseriesmetric m",
    "m",
    "m.field_id",
    "JOIN x1_timeseriesmetric m ON m.field_id = s.ref_id",
    "SELECT field_name FROM x1_timeseriesmetric WHERE group_id = %s AND original_name IN ({marks})",
    "x1_timeseriesmetric r",
    "r.field_id",
    BY_NAME,
)
X2: Variant = Variant(
    "x2",
    "metadata_timeseriesmetric",
    "metadata_timeseriesmetric m LEFT JOIN x2_metric_meta d ON d.field_id = m.field_id",
    "d",
    "m.field_id",
    "JOIN metadata_timeseriesmetric m ON m.field_id = s.ref_id LEFT JOIN x2_metric_meta d ON d.field_id = m.field_id",
    "SELECT m.field_name FROM x2_metric_meta d JOIN metadata_timeseriesmetric m ON m.field_id = d.field_id "
    "WHERE d.group_id = %s AND d.original_name IN ({marks})",
    "metadata_timeseriesmetric r",
    "r.field_id",
    BY_NAME,
)
X3: Variant = Variant(
    "x3",
    "metadata_timeseriesmetric",
    "metadata_timeseriesmetric m LEFT JOIN x3_metric_meta d ON d.group_id = m.group_id AND d.field_name = m.field_name",
    "d",
    "d.id",
    "JOIN x3_metric_meta d ON d.id = s.ref_id JOIN metadata_timeseriesmetric m ON m.group_id = d.group_id "
    "AND m.field_scope = 'default' AND m.field_name = d.field_name",
    "SELECT field_name FROM x3_metric_meta WHERE group_id = %s AND original_name IN ({marks})",
    "x3_metric_meta r",
    "r.id",
    "r.group_id = %s AND r.field_name = %s",
)
VARIANTS: tuple[Variant, ...] = (BASE_VARIANT, X1, X2, X3)

# QueryTimeSeriesMetricResource：filter(group_id).exclude(scope_id=0)，管理页强制 field_scope
MANAGE_WHERE: str = "m.group_id = %s AND NOT (m.scope_id = 0 AND m.scope_id IS NOT NULL) AND m.field_scope = 'default'"
PAGE_COLS: str = (
    "m.field_id, m.scope_id, m.field_name, m.tag_list, m.field_config, m.field_scope, m.create_time, m.last_modify_time"
)
INFO_COLS: str = (
    "m.field_id, m.group_id, m.field_name, m.field_scope, m.tag_list, m.field_config, m.create_time, "
    "m.last_modify_time, m.label, m.is_active, m.scope_id"
)
SERVICE_LABEL: str = "l.group_id = %s AND l.label_key = 'service_name' AND l.label_value = %s"
LABEL_TO_MEMBER: str = (
    "report_scope_label l JOIN report_member s ON s.group_id = l.group_id AND s.report_scope_id = l.report_scope_id"
)


def defs(v: Variant) -> str:
    return f", {v.d}.original_name, {v.d}.metric_type, {v.d}.meta" if v.d else ""


def search_where(v: Variant) -> tuple[str, tuple[str, ...]]:
    """Django icontains：field_name 是 utf8_bin 时为 LIKE，JSON 键为 LOWER(JSON_UNQUOTE(...)) LIKE LOWER(...)。"""
    if not v.d:
        return " AND m.field_name LIKE %s", (SEARCH,)
    description: str = f"LOWER(JSON_UNQUOTE(JSON_EXTRACT({v.d}.meta, '$.\"description\"')))"
    return (
        f" AND (m.field_name LIKE %s OR {v.d}.original_name LIKE %s OR {description} LIKE LOWER(%s))",
        (SEARCH, SEARCH, SEARCH),
    )


def q1_case(v: Variant, groups: Sequence[int], offset: int, order: str, search: bool) -> Case:
    """count、取本页 scope_id、批量取页面分组、取本页指标，与资源实现的四条语句一致；count 不带 select_related。"""
    extra, terms = search_where(v) if search else ("", ())
    where: str = MANAGE_WHERE + extra
    plain: str = v.source if search else f"{v.metric} m"
    tail: str = f" ORDER BY {order} LIMIT {PAGE} OFFSET {offset}"
    count_sql: str = f"SELECT COUNT(*) FROM {plain} WHERE {where}"
    ids_sql: str = f"SELECT m.scope_id FROM {plain} WHERE {where}{tail}"
    page_sql: str = f"SELECT {PAGE_COLS}{defs(v)} FROM {v.source} WHERE {where}{tail}"

    def run(cur: Cursor, g: int) -> int:
        params: tuple[Any, ...] = (g, *terms)
        fetch(cur, count_sql, params)
        scope_ids: list[Any] = sorted({r[0] for r in fetch(cur, ids_sql, params) if r[0] is not None})
        if scope_ids:
            fetch(
                cur,
                f"SELECT id, scope_name FROM metadata_timeseriesscope WHERE id IN ({marks(len(scope_ids))}) "
                "AND group_id = %s",
                (*scope_ids, g),
            )
        return len(fetch(cur, page_sql, params))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], page_sql, (groups[0], *terms))


def q1_count_case(v: Variant, groups: Sequence[int]) -> Case:
    """管理页 count 单独计时；exclude(scope_id=0) 不在唯一键内，需要逐行回表。"""
    sql: str = f"SELECT COUNT(*) FROM {v.metric} m WHERE {MANAGE_WHERE}"
    return Case([lambda cur, g=g: len(fetch(cur, sql, (g,))) for g in groups], sql, (groups[0],))


def q2_case(v: Variant, groups: Sequence[int]) -> Case:
    """节点 = (scope_id, COALESCE(original_name, field_name))：节点分页、节点总数，再按原名与指标名取本页节点的全部指标。"""
    node: str = v.node or f"COALESCE({v.d}.original_name, m.field_name)"
    nodes_sql: str = (
        f"SELECT m.scope_id, {node} AS node, COUNT(*) FROM {v.source} WHERE {MANAGE_WHERE} "
        f"GROUP BY m.scope_id, node ORDER BY m.scope_id, node LIMIT {PAGE}"
    )
    total_sql: str = (
        f"SELECT COUNT(*) FROM (SELECT 1 FROM {v.source} WHERE {MANAGE_WHERE} GROUP BY m.scope_id, {node}) t"
    )
    members_sql: str = (
        f"SELECT {PAGE_COLS}{defs(v)} FROM {v.source} "
        "WHERE m.group_id = %s AND m.field_scope = 'default' AND m.field_name IN ({marks})"
    )

    def run(cur: Cursor, g: int) -> int:
        names: list[str] = sorted({r[1] for r in fetch(cur, nodes_sql, (g,))})
        fetch(cur, total_sql, (g,))
        family: set[str] = {r[0] for r in fetch(cur, v.family.replace("{marks}", marks(len(names))), (g, *names))}
        wanted: list[str] = sorted(family | set(names))
        return len(fetch(cur, members_sql.replace("{marks}", marks(len(wanted))), (g, *wanted)))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], nodes_sql, (groups[0],))


@dataclass(frozen=True)
class Sample:
    group_id: int
    service: str
    field_ids: tuple[int, ...]
    field_name: str


def q3_case(v: Variant, samples: Sequence[Sample]) -> Case:
    """标签倒排 → 上报范围 → 成员 → 指标项与定义 → 页面分组，返回服务的全部指标。"""
    sql: str = (
        f"SELECT ts.scope_name, m.field_id, m.field_name, m.tag_list, m.field_config{defs(v)}, s.meta, s.field_config "
        f"FROM {LABEL_TO_MEMBER} {v.member_join} LEFT JOIN metadata_timeseriesscope ts ON ts.id = m.scope_id "
        f"WHERE {SERVICE_LABEL} ORDER BY ts.scope_name, m.field_name"
    )
    return Case(
        [lambda cur, s=s: len(fetch(cur, sql, (s.group_id, s.service))) for s in samples],
        sql,
        (samples[0].group_id, samples[0].service),
    )


def q4_case(v: Variant, samples: Sequence[Sample]) -> Case:
    """一页指标的定义，再取命中服务范围的成员 meta 与 field_config；X3 的成员引用来自第一步的定义 id。"""

    def def_sql(count: int) -> str:
        return (
            f"SELECT m.field_id, m.field_name, m.field_config{defs(v)}, {v.ref} FROM {v.source} "
            f"WHERE m.field_id IN ({marks(count)})"
        )

    def member_sql(count: int) -> str:
        return (
            f"SELECT s.report_scope_id, s.ref_id, s.meta, s.field_config FROM {LABEL_TO_MEMBER} "
            f"WHERE {SERVICE_LABEL} AND s.ref_id IN ({marks(count)})"
        )

    def run(cur: Cursor, s: Sample) -> int:
        rows: tuple[Any, ...] = fetch(cur, def_sql(len(s.field_ids)), s.field_ids)
        refs: list[Any] = [r[-1] for r in rows if r[-1] is not None]
        return len(rows) + len(fetch(cur, member_sql(len(refs)), (s.group_id, s.service, *refs)))

    first: Sample = samples[0]
    return Case(
        [lambda cur, s=s: run(cur, s) for s in samples],
        member_sql(len(first.field_ids)),
        (first.group_id, first.service, *first.field_ids),
    )


def q5_case(v: Variant, groups: Sequence[int]) -> Case:
    """get_metric_info_list：分组内未过期指标项与定义，加页面分组。"""
    sql: str = f"SELECT {INFO_COLS}{defs(v)} FROM {v.source} WHERE m.group_id = %s AND m.last_modify_time > %s"
    scope_sql: str = (
        "SELECT id, group_id, scope_name, dimension_config, auto_rules, create_from, last_modify_time "
        "FROM metadata_timeseriesscope WHERE group_id = %s"
    )

    def run(cur: Cursor, g: int) -> int:
        return len(fetch(cur, sql, (g, EXPIRE_BEFORE))) + len(fetch(cur, scope_sql, (g,)))

    return Case([lambda cur, g=g: run(cur, g) for g in groups], sql, (groups[0], EXPIRE_BEFORE))


def q7_case(v: Variant, samples: Sequence[Sample], by_service: bool) -> Case:
    """按 (group, 指标名) 定位引用，成员 (group, ref) → 范围 → labels；by_service 时经标签倒排限定服务。"""
    label_join: str = (
        "JOIN report_scope_label l ON l.group_id = s.group_id AND l.label_key = 'service_name' "
        "AND l.label_value = %s AND l.report_scope_id = s.report_scope_id "
        if by_service
        else ""
    )
    sql: str = (
        f"SELECT sc.id, sc.labels FROM {v.ref_from} JOIN report_member s ON s.group_id = r.group_id "
        f"AND s.ref_id = {v.ref_col} {label_join}JOIN report_scope sc ON sc.id = s.report_scope_id WHERE {v.ref_where}"
    )

    def params_of(s: Sample) -> tuple[Any, ...]:
        return ((s.service,) if by_service else ()) + (s.group_id, s.field_name)

    return Case([lambda cur, s=s: len(fetch(cur, sql, params_of(s))) for s in samples], sql, params_of(samples[0]))


CASE_ORDER: tuple[str, ...] = (
    "q1.page1",
    "q1.count",
    "q1.deep",
    "q1.search",
    "q1.recent",
    "q2.nodes",
    "q3.service",
    "q3.hot",
    "q4.prefetch",
    "q5.group",
    "q7.service",
    "q7.all",
)


@dataclass
class TierSamples:
    name: str
    groups: list[int]
    services: list[Sample]
    hot: list[Sample]


def read_cases(v: Variant, ts: TierSamples) -> dict[str, Case]:
    cases: dict[str, Case] = {
        "q1.page1": q1_case(v, ts.groups, 0, "m.field_name", False),
        "q1.search": q1_case(v, ts.groups, 0, "m.field_name", True),
        "q1.recent": q1_case(v, ts.groups, 0, "m.last_modify_time DESC", False),
        "q5.group": q5_case(v, ts.groups),
    }
    if ts.hot:
        cases["q1.deep"] = q1_case(v, ts.groups, DEEP_OFFSET, "m.field_name", False)
    if v.name in ("base", "x1"):
        cases["q1.count"] = q1_count_case(v, ts.groups)
    if v.d:
        cases["q2.nodes"] = q2_case(v, ts.groups)
        cases["q3.service"] = q3_case(v, ts.services)
        cases["q4.prefetch"] = q4_case(v, ts.services)
        cases["q7.service"] = q7_case(v, ts.services, True)
        cases["q7.all"] = q7_case(v, ts.services, False)
        if ts.hot:
            cases["q3.hot"] = q3_case(v, ts.hot)
    return cases


def service_sample(conn: pymysql.Connection, g: Group, service_idx: int, rng: random.Random) -> Sample | None:
    service: str = service_name(g.group_id, service_idx)
    refs: list[int] = [
        r[0]
        for r in execute(conn, f"SELECT s.ref_id FROM {LABEL_TO_MEMBER} WHERE {SERVICE_LABEL}", (g.group_id, service))
    ]
    if not refs:
        return None
    page: tuple[int, ...] = tuple(sorted(rng.sample(refs, min(PAGE, len(refs)))))
    name: str = execute(
        conn, "SELECT field_name FROM metadata_timeseriesmetric WHERE field_id = %s", (rng.choice(refs),)
    )[0][0]
    return Sample(g.group_id, service, page, name)


def build_samples(conn: pymysql.Connection, groups: Sequence[Group]) -> list[TierSamples]:
    rng: random.Random = random.Random(23)
    xl: list[Group] = [g for g in groups if g.tier.name == "XL"]
    large: list[Group] = [g for g in groups if g.tier.name == "L"]
    large = sorted(rng.sample(large, min(L_SAMPLE_GROUPS, len(large))), key=lambda g: g.group_id)
    result: list[TierSamples] = []
    for name, chosen, per_group in (("xl", xl, XL_SERVICES), ("l", large, L_SERVICES)):
        services: list[Sample] = []
        hot: list[Sample] = []
        for g in chosen:
            for j in rng.sample(range(g.tier.services), min(per_group, g.tier.services)):
                sample: Sample | None = service_sample(conn, g, j, rng)
                if sample is not None:
                    services.append(sample)
            if name == "xl":
                top: Sample | None = service_sample(conn, g, 0, rng)
                if top is not None:
                    hot.append(top)
        result.append(TierSamples(name, [g.group_id for g in chosen], services, hot))
    return result


def report_reads(conn: pymysql.Connection, raw: pymysql.Connection, ts: TierSamples) -> None:
    emit(
        f"## Q1-Q5, Q7 read latency, tier {ts.name.upper()}: {len(ts.groups)} groups, {len(ts.services)} services"
        + (f", {len(ts.hot)} hottest services" if ts.hot else "")
        + f"; {ITERATIONS} runs after {WARMUP} warmup, unix socket, no type conversion"
    )
    emit(STAT_HEADER)
    built: dict[str, dict[str, Case]] = {v.name: read_cases(v, ts) for v in VARIANTS}
    plans: list[str] = []
    for name in CASE_ORDER:
        for v in VARIANTS:
            case: Case | None = built[v.name].get(name)
            if case is None:
                continue
            label: str = f"{ts.name}.{name}.{v.name}"
            log(f"measure {label}")
            emit(measure(label, raw, case.runs, seed=f"{ts.name}.{name}").line())
            plans.append(f"{label}: {explain(conn, case.sql, case.params)}")
    emit()
    emit("## EXPLAIN (table:key/type~rows[flags]; main statement of each case)")
    for plan in plans:
        emit(plan)
    emit()


NODE_COLUMN: str = (
    "ALTER TABLE x1_timeseriesmetric ADD COLUMN node_name VARCHAR(255) COLLATE utf8mb3_bin "
    "AS (COALESCE(original_name, field_name)) VIRTUAL, ALGORITHM=INSTANT"
)
NODE_INDEX: str = (
    "ALTER TABLE x1_timeseriesmetric ADD INDEX idx_group_scope_node (group_id, field_scope, scope_id, node_name), "
    "ALGORITHM=INPLACE, LOCK=NONE"
)


def report_node_index(conn: pymysql.Connection, raw: pymysql.Connection, tiers: Sequence[TierSamples]) -> None:
    """X1 的节点键可做成虚拟生成列并建索引，分组与排序走索引顺序；X2/X3 的 scope_id 与原名分属两表，无法建同样的索引。"""
    column: str = timed(conn, NODE_COLUMN)
    index: str = timed(conn, NODE_INDEX)
    analyze(conn, ["x1_timeseriesmetric"])
    size: int = index_sizes(conn, "x1_timeseriesmetric").get("idx_group_scope_node", 0)
    rows: int = execute(conn, "SELECT COUNT(*) FROM x1_timeseriesmetric")[0][0]
    emit(
        "## Q2 on X1 with node_name = COALESCE(original_name, field_name) VIRTUAL and "
        "KEY (group_id, field_scope, scope_id, node_name)"
    )
    emit(
        f"ADD COLUMN VIRTUAL INSTANT {column}, ADD INDEX INPLACE {index}, index {mib(size)} MiB "
        f"({size / rows:.1f} B/row); dropped again after this section"
    )
    emit(STAT_HEADER)
    variant: Variant = replace(X1, name="x1_node_idx", node="m.node_name")
    plans: list[str] = []
    for ts in tiers:
        case: Case = q2_case(variant, ts.groups)
        label: str = f"{ts.name}.q2.nodes.x1_node_idx"
        log(f"measure {label}")
        emit(measure(label, raw, case.runs, seed=f"{ts.name}.q2.nodes").line())
        plans.append(f"{label}: {explain(conn, case.sql, case.params)}")
        total_sql: str = (
            f"SELECT COUNT(*) FROM (SELECT 1 FROM x1_timeseriesmetric m WHERE {MANAGE_WHERE} "
            "GROUP BY m.scope_id, m.node_name) t"
        )
        plans.append(f"{label}.total: {explain(conn, total_sql, (ts.groups[0],))}")
    execute(conn, "ALTER TABLE x1_timeseriesmetric DROP INDEX idx_group_scope_node, ALGORITHM=INPLACE, LOCK=NONE")
    execute(conn, "ALTER TABLE x1_timeseriesmetric DROP COLUMN node_name, ALGORITHM=INSTANT")
    emit()
    emit("## EXPLAIN Q2 with node index")
    for plan in plans:
        emit(plan)
    emit()


# ---------------------------------------------------------------- Q6 全平台扫描


def scan_by_groups(cur: Cursor, sql: str, group_ids: Sequence[int]) -> tuple[list[float], int]:
    chunks: list[float] = []
    rows: int = 0
    for i in range(0, len(group_ids), GROUP_CHUNK):
        chunk: Sequence[int] = group_ids[i : i + GROUP_CHUNK]
        start: float = time.perf_counter()
        rows += len(fetch(cur, sql.replace("{marks}", marks(len(chunk))), (*chunk, EXPIRE_BEFORE)))
        chunks.append((time.perf_counter() - start) * 1000)
    return chunks, rows


def scan_by_keys(cur: Cursor, sql: str, size: int) -> tuple[list[float], int]:
    chunks: list[float] = []
    rows: int = 0
    last: int = 0
    while True:
        start: float = time.perf_counter()
        result: tuple[Any, ...] = fetch(cur, sql, (last, size))
        chunks.append((time.perf_counter() - start) * 1000)
        if not result:
            return chunks, rows
        rows += len(result)
        last = int(result[-1][0])


def report_scan(conn: pymysql.Connection, raw: pymysql.Connection, groups: Sequence[Group]) -> None:
    group_ids: list[int] = sorted(g.group_id for g in groups)
    emit(
        f"## Q6 full scan of all metric items + definitions, median of {SCAN_REPEATS} passes "
        f"(group500 = group_id IN 500 ids AND last_modify_time > 30 d, pkN = field_id keyset LIMIT N)"
    )
    emit(f"{'case':<20}{'total s':>10}{'rows':>12}{'chunks':>8}{'chunk p50':>11}{'chunk p95':>11}{'disk rd':>10}")
    plans: list[str] = []
    for v in VARIANTS:
        group_sql: str = (
            f"SELECT {INFO_COLS}{defs(v)} FROM {v.source} WHERE m.group_id IN ({{marks}}) AND m.last_modify_time > %s"
        )
        key_sql: str = f"SELECT {INFO_COLS}{defs(v)} FROM {v.source} WHERE m.field_id > %s ORDER BY m.field_id LIMIT %s"
        methods: dict[str, Callable[[Cursor], tuple[list[float], int]]] = {
            "group500": lambda cur, sql=group_sql: scan_by_groups(cur, sql, group_ids),
        }
        for size in SCAN_CHUNKS:
            methods[f"pk{size}"] = lambda cur, size=size, sql=key_sql: scan_by_keys(cur, sql, size)
        for method, fn in methods.items():
            log(f"scan {v.name}.{method}")
            totals: list[float] = []
            chunks: list[float] = []
            rows: int = 0
            before: int = pool_reads(raw)
            with raw.cursor() as cur:
                for _ in range(SCAN_REPEATS):
                    start: float = time.perf_counter()
                    chunks, rows = fn(cur)
                    totals.append(time.perf_counter() - start)
            emit(
                f"{v.name + '.' + method:<20}{statistics.median(totals):>10.2f}{rows:>12,}{len(chunks):>8}"
                f"{percentile(chunks, 0.5):>11.2f}{percentile(chunks, 0.95):>11.2f}{pool_reads(raw) - before:>10,}"
            )
        plans.append(
            f"{v.name}.group500: "
            + explain(conn, group_sql.replace("{marks}", marks(GROUP_CHUNK)), (*group_ids[:GROUP_CHUNK], EXPIRE_BEFORE))
        )
        plans.append(f"{v.name}.pk: " + explain(conn, key_sql, (0, SCAN_CHUNKS[-1])))
    emit()
    emit("## EXPLAIN Q6")
    for plan in plans:
        emit(plan)
    emit()


# ---------------------------------------------------------------- Q8 bmw Apply


@dataclass(frozen=True)
class Report:
    group_id: int
    scope_hash: str
    field_name: str
    original_name: str
    metric_type: str
    fingerprint: str
    meta: str | None


@dataclass
class GroupIndex:
    scopes: dict[int, str]
    metas: dict[int, tuple[str, str, str, str]]
    first_member: int
    last_member: int


def group_index(conn: pymysql.Connection, g: int) -> GroupIndex:
    scopes: dict[int, str] = dict(execute(conn, "SELECT id, scope_hash FROM report_scope WHERE group_id = %s", (g,)))
    metas: dict[int, tuple[str, str, str, str]] = {
        r[0]: (r[1], r[2], r[3], r[4])
        for r in execute(
            conn,
            "SELECT id, field_name, original_name, metric_type, fingerprint FROM x3_metric_meta WHERE group_id = %s",
            (g,),
        )
    }
    first, last = execute(conn, "SELECT MIN(id), MAX(id) FROM report_member WHERE group_id = %s", (g,))[0]
    return GroupIndex(scopes, metas, first, last)


def build_batch(
    conn: pymysql.Connection, parts: Sequence[tuple[int, int, int]], index: dict[int, GroupIndex], rng: random.Random
) -> list[Report]:
    """parts 为 (group, 条数, 新成员数)：已有成员按主键随机抽取，新成员取该分组中不存在的 (范围, 指标) 组合。"""
    pairs: list[tuple[int, int, int]] = []
    for g, count, fresh in parts:
        gi: GroupIndex = index[g]
        ids: list[int] = rng.sample(range(gi.first_member, gi.last_member + 1), count - fresh)
        pairs.extend(
            (g, sid, ref)
            for sid, ref in execute(
                conn,
                f"SELECT report_scope_id, ref_id FROM report_member WHERE group_id = %s AND id IN ({marks(len(ids))})",
                (g, *ids),
            )
        )
        scope_ids: list[int] = list(gi.scopes)
        meta_ids: list[int] = list(gi.metas)
        added: int = 0
        while added < fresh:
            sid: int = rng.choice(scope_ids)
            ref: int = rng.choice(meta_ids)
            if not execute(
                conn,
                "SELECT 1 FROM report_member WHERE group_id = %s AND report_scope_id = %s AND ref_id = %s",
                (g, sid, ref),
            ):
                pairs.append((g, sid, ref))
                added += 1
    reports: list[Report] = []
    for g, sid, ref in pairs:
        name, original, kind, fingerprint = index[g].metas[ref]
        reports.append(Report(g, index[g].scopes[sid], name, original, kind, fingerprint, None))
    for i in rng.sample(range(len(reports)), APPLY_CHANGED):
        r: Report = reports[i]
        meta: str = json.dumps(
            {"unit": "ms", "description": f"changed {rng.random():.12f}", "temporality": "delta", "interval": 30}
        )
        reports[i] = Report(r.group_id, r.scope_hash, r.field_name, r.original_name, "summary", md5_hex(meta), meta)
    return reports


DEF_READ: dict[str, tuple[str, str]] = {
    "x1": (
        (
            "SELECT field_id, group_id, field_name, meta_fingerprint, meta_seen_at FROM x1_timeseriesmetric "
            "WHERE (group_id, field_scope, field_name) IN ({tuples})"
        ),
        "(%s, 'default', %s)",
    ),
    "x2": (
        (
            "SELECT m.field_id, m.group_id, m.field_name, d.fingerprint, d.seen_at FROM metadata_timeseriesmetric m "
            "LEFT JOIN x2_metric_meta d ON d.field_id = m.field_id "
            "WHERE (m.group_id, m.field_scope, m.field_name) IN ({tuples})"
        ),
        "(%s, 'default', %s)",
    ),
    "x3": (
        (
            "SELECT id, group_id, field_name, fingerprint, seen_at FROM x3_metric_meta "
            "WHERE (group_id, field_name) IN ({tuples})"
        ),
        "(%s, %s)",
    ),
}
DEF_REFRESH: dict[str, str] = {
    "x1": "UPDATE x1_timeseriesmetric SET meta_seen_at = %s WHERE field_id IN ({marks})",
    "x2": "UPDATE x2_metric_meta SET seen_at = %s WHERE field_id IN ({marks})",
    "x3": "UPDATE x3_metric_meta SET seen_at = %s WHERE id IN ({marks})",
}
DEF_UPSERT_TAIL: str = (
    " ON DUPLICATE KEY UPDATE original_name = VALUES(original_name), metric_type = VALUES(metric_type), "
    "meta = VALUES(meta), fingerprint = VALUES(fingerprint), seen_at = VALUES(seen_at)"
)
SCOPE_READ: str = (
    "SELECT id, group_id, scope_hash, last_seen FROM report_scope WHERE (group_id, scope_hash) IN ({tuples})"
)
MEMBER_READ: str = "SELECT report_scope_id, ref_id, last_seen FROM report_member WHERE (group_id, report_scope_id, ref_id) IN ({tuples})"


def apply_sql(template: str, tuple_marks: str, count: int) -> str:
    return template.replace("{tuples}", ", ".join([tuple_marks] * count))


def apply_reads(batch: Sequence[Report], variant: str) -> list[tuple[str, tuple[Any, ...]]]:
    """Apply 的三条批量读取语句，供 EXPLAIN 使用；成员读取以批次中的已有组合为例。"""
    scope_keys: list[tuple[int, str]] = sorted({(r.group_id, r.scope_hash) for r in batch})
    name_keys: list[tuple[int, str]] = sorted({(r.group_id, r.field_name) for r in batch})
    template, tuple_marks = DEF_READ[variant]
    return [
        (apply_sql(SCOPE_READ, "(%s, %s)", len(scope_keys)), tuple(v for k in scope_keys for v in k)),
        (apply_sql(template, tuple_marks, len(name_keys)), tuple(v for k in name_keys for v in k)),
    ]


def apply(cur: Cursor, variant: str, batch: Sequence[Report]) -> tuple[int, int]:
    """按 (group, scope_hash) 取范围、按指标名取定义、按 (group, 范围, ref) 取成员，再在一个事务中写入变化行。"""
    scope_keys: list[tuple[int, str]] = sorted({(r.group_id, r.scope_hash) for r in batch})
    scope_rows: tuple[Any, ...] = fetch(
        cur, apply_sql(SCOPE_READ, "(%s, %s)", len(scope_keys)), [v for k in scope_keys for v in k]
    )
    scope_of: dict[tuple[int, str], tuple[str, str]] = {(int(r[1]), r[2]): (r[0], r[3]) for r in scope_rows}
    name_keys: list[tuple[int, str]] = sorted({(r.group_id, r.field_name) for r in batch})
    template, tuple_marks = DEF_READ[variant]
    def_rows: tuple[Any, ...] = fetch(
        cur, apply_sql(template, tuple_marks, len(name_keys)), [v for k in name_keys for v in k]
    )
    def_of: dict[tuple[int, str], tuple[str, str | None, str | None]] = {
        (int(r[1]), r[2]): (r[0], r[3], r[4]) for r in def_rows
    }
    member_keys: dict[tuple[int, str, str], None] = {}
    for r in batch:
        member_keys[(r.group_id, scope_of[(r.group_id, r.scope_hash)][0], def_of[(r.group_id, r.field_name)][0])] = None
    member_rows: tuple[Any, ...] = fetch(
        cur, apply_sql(MEMBER_READ, "(%s, %s, %s)", len(member_keys)), [v for k in member_keys for v in k]
    )
    seen: dict[tuple[str, str], str] = {(r[0], r[1]): r[2] for r in member_rows}

    stale_scopes: list[str] = sorted({sid for sid, last in scope_of.values() if last < STALE_BEFORE})
    changed: dict[tuple[int, str], Report] = {}
    for r in batch:
        key: tuple[int, str] = (r.group_id, r.field_name)
        if r.meta is not None and def_of[key][1] != r.fingerprint:
            changed[key] = r
    stale_defs: list[str] = sorted(
        {
            ref
            for key, (ref, _, last) in def_of.items()
            if key not in changed and last is not None and last < STALE_BEFORE
        }
    )
    upserts: list[tuple[int, str, str]] = [
        k for k in member_keys if (k[1], k[2]) not in seen or seen[(k[1], k[2])] < STALE_BEFORE
    ]
    statements: int = 3
    cur.execute("BEGIN")
    if stale_scopes:
        cur.execute(
            f"UPDATE report_scope SET last_seen = %s WHERE id IN ({marks(len(stale_scopes))})", (NOW, *stale_scopes)
        )
        statements += 1
    if changed and variant == "x1":
        for key, r in changed.items():
            cur.execute(
                "UPDATE x1_timeseriesmetric SET original_name = %s, metric_type = %s, meta = %s, meta_fingerprint = %s, "
                "meta_seen_at = %s WHERE field_id = %s",
                (r.original_name, r.metric_type, r.meta, r.fingerprint, NOW, def_of[key][0]),
            )
            statements += 1
    elif changed and variant == "x2":
        cur.execute(
            "INSERT INTO x2_metric_meta (field_id, group_id, original_name, metric_type, meta, fingerprint, seen_at) "
            "VALUES " + ", ".join(["(%s, %s, %s, %s, %s, %s, %s)"] * len(changed)) + DEF_UPSERT_TAIL,
            [
                v
                for key, r in changed.items()
                for v in (def_of[key][0], r.group_id, r.original_name, r.metric_type, r.meta, r.fingerprint, NOW)
            ],
        )
        statements += 1
    elif changed:
        cur.execute(
            "INSERT INTO x3_metric_meta (group_id, field_name, original_name, metric_type, meta, fingerprint, seen_at) "
            "VALUES " + ", ".join(["(%s, %s, %s, %s, %s, %s, %s)"] * len(changed)) + DEF_UPSERT_TAIL,
            [
                v
                for r in changed.values()
                for v in (r.group_id, r.field_name, r.original_name, r.metric_type, r.meta, r.fingerprint, NOW)
            ],
        )
        statements += 1
    if stale_defs:
        cur.execute(DEF_REFRESH[variant].replace("{marks}", marks(len(stale_defs))), (NOW, *stale_defs))
        statements += 1
    if upserts:
        cur.execute(
            "INSERT INTO report_member (group_id, report_scope_id, ref_id, last_seen) VALUES "
            + ", ".join(["(%s, %s, %s, %s)"] * len(upserts))
            + " ON DUPLICATE KEY UPDATE last_seen = VALUES(last_seen)",
            [v for k in upserts for v in (*k, NOW)],
        )
        statements += 1
    cur.execute("COMMIT")
    return statements, len(stale_scopes) + len(changed) + len(stale_defs) + len(upserts)


def report_apply(conn: pymysql.Connection, raw: pymysql.Connection, xl: Sequence[int], large: Sequence[int]) -> None:
    emit(
        f"## Q8 bmw Apply: {APPLY_BATCH} reports per batch ({APPLY_NEW} new members, {APPLY_CHANGED} changed "
        f"definitions, ~10% members/definitions/scopes due for last_seen refresh), one transaction per batch, "
        f"{ITERATIONS} batches after {WARMUP} warmup"
    )
    emit(
        f"{'case':<20}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}{'stmts':>8}{'written':>9}{'reports/s@p50':>15}"
        f"{'disk rd':>10}"
    )
    index: dict[int, GroupIndex] = {g: group_index(conn, g) for g in [*xl, *large]}
    plans: list[str] = []
    for shape in ("xl", "mixed"):
        for variant in ("x1", "x2", "x3"):
            log(f"apply {shape}.{variant}")
            rng: random.Random = random.Random(f"{shape}.{variant}")
            batches: list[list[Report]] = []
            for _ in range(WARMUP + ITERATIONS):
                if shape == "xl":
                    parts: list[tuple[int, int, int]] = [(rng.choice(list(xl)), APPLY_BATCH, APPLY_NEW)]
                else:
                    chosen: list[int] = rng.sample(list(large), min(MIXED_GROUPS, len(large)))
                    per: int = APPLY_BATCH // len(chosen)
                    parts = [(g, per, 1 if i < APPLY_NEW else 0) for i, g in enumerate(chosen)]
                batches.append(build_batch(conn, parts, index, rng))
            samples: list[float] = []
            statements: list[int] = []
            written: list[int] = []
            before: int = pool_reads(raw)
            with raw.cursor() as cur:
                for i, batch in enumerate(batches):
                    start: float = time.perf_counter()
                    stmts, rows = apply(cur, variant, batch)
                    elapsed: float = (time.perf_counter() - start) * 1000
                    if i >= WARMUP:
                        samples.append(elapsed)
                        statements.append(stmts)
                        written.append(rows)
            p50: float = statistics.median(samples)
            emit(
                f"{shape + '.' + variant:<20}{p50:>10.3f}{percentile(samples, 0.95):>10.3f}"
                f"{percentile(samples, 0.99):>10.3f}{statistics.mean(statements):>8.1f}{statistics.mean(written):>9.1f}"
                f"{len(batches[0]) / p50 * 1000:>15,.0f}{pool_reads(raw) - before:>10,}"
            )
            for label, (sql, params) in zip(("scope", "definition"), apply_reads(batches[-1], variant)):
                plans.append(f"{shape}.{variant}.{label}: {explain(conn, sql, params)}")
    keys: list[tuple[int, int, int]] = [
        (g, sid, ref)
        for g, sid, ref in execute(
            conn, "SELECT group_id, report_scope_id, ref_id FROM report_member WHERE group_id = %s LIMIT 1000", (xl[0],)
        )
    ]
    plans.append(
        "member: " + explain(conn, apply_sql(MEMBER_READ, "(%s, %s, %s)", len(keys)), tuple(v for k in keys for v in k))
    )
    emit()
    emit("## EXPLAIN Q8")
    for plan in plans:
        emit(plan)
    emit()


# ---------------------------------------------------------------- Q9 bmw Compact


@dataclass
class Compaction:
    name: str
    batches: list[float] = field(default_factory=list)
    scans: list[float] = field(default_factory=list)
    totals: list[float] = field(default_factory=list)
    deleted: int = 0

    def line(self) -> str:
        scans: str = f"{percentile(self.scans, 0.5):>10.2f}" if self.scans else f"{'-':>10}"
        return (
            f"{self.name:<30}{self.deleted:>9,}{statistics.median(self.totals):>10.2f}{max(self.totals):>9.2f}"
            f"{len(self.batches):>8}{percentile(self.batches, 0.5):>10.2f}{percentile(self.batches, 0.95):>10.2f}"
            f"{max(self.batches):>10.2f}{scans}"
        )


COMPACT_HEADER: str = (
    f"{'case':<30}{'deleted':>9}{'group s':>10}{'max s':>9}{'batches':>8}{'del p50':>10}{'del p95':>10}"
    f"{'del max':>10}{'scan p50':>10}"
)
DELETE_SQL: str = "DELETE FROM report_member WHERE group_id = %s AND last_seen < %s LIMIT %s"
KEYSET_SQL: str = (
    "SELECT id, report_scope_id, ref_id, last_seen FROM report_member WHERE group_id = %s "
    "AND (report_scope_id > %s OR (report_scope_id = %s AND ref_id > %s)) ORDER BY report_scope_id, ref_id LIMIT %s"
)
EXCEPTION_SQL: str = (
    "SELECT id, report_scope_id, ref_id, meta, field_config FROM report_member "
    "WHERE group_id = %s AND (meta IS NOT NULL OR field_config IS NOT NULL)"
)


def compact_delete(cur: Cursor, groups: Sequence[int], name: str) -> Compaction:
    result: Compaction = Compaction(name)
    for g in groups:
        start: float = time.perf_counter()
        while True:
            batch_start: float = time.perf_counter()
            cur.execute(DELETE_SQL, (g, EXPIRE_BEFORE, COMPACT_BATCH))
            result.batches.append((time.perf_counter() - batch_start) * 1000)
            result.deleted += cur.rowcount
            if cur.rowcount < COMPACT_BATCH:
                break
        result.totals.append(time.perf_counter() - start)
    return result


def delete_ids(cur: Cursor, ids: Sequence[Any], result: Compaction) -> None:
    start: float = time.perf_counter()
    cur.execute(f"DELETE FROM report_member WHERE id IN ({marks(len(ids))})", ids)
    result.batches.append((time.perf_counter() - start) * 1000)
    result.deleted += cur.rowcount


def compact_keyset(cur: Cursor, groups: Sequence[int], name: str) -> Compaction:
    """沿唯一键分块扫描分组，挑出过期行后按主键批量删除，不依赖额外索引。"""
    result: Compaction = Compaction(name)
    for g in groups:
        start: float = time.perf_counter()
        scope: int = 0
        ref: int = 0
        expired: list[Any] = []
        while True:
            scan_start: float = time.perf_counter()
            rows: tuple[Any, ...] = fetch(cur, KEYSET_SQL, (g, scope, scope, ref, COMPACT_SCAN))
            result.scans.append((time.perf_counter() - scan_start) * 1000)
            if not rows:
                break
            scope, ref = int(rows[-1][1]), int(rows[-1][2])
            expired.extend(r[0] for r in rows if r[3] < EXPIRE_BEFORE)
            while len(expired) >= COMPACT_BATCH:
                delete_ids(cur, expired[:COMPACT_BATCH], result)
                del expired[:COMPACT_BATCH]
        if expired:
            delete_ids(cur, expired, result)
        result.totals.append(time.perf_counter() - start)
    return result


def remark(cur: Cursor, groups: Sequence[int], residue: int) -> int:
    """把 2% 的成员改为过期，供下一种清理方式使用。"""
    total: int = 0
    for g in groups:
        cur.execute(
            "UPDATE report_member SET last_seen = %s WHERE group_id = %s AND MOD(id, 50) = %s", (EXPIRED[0], g, residue)
        )
        total += cur.rowcount
    return total


def report_compact(conn: pymysql.Connection, raw: pymysql.Connection, xl: Sequence[int], large: Sequence[int]) -> None:
    emit(
        f"## Q9 bmw Compact on {len(xl)} XL groups: expired = last_seen older than 30 d, "
        f"batches of {COMPACT_BATCH}, autocommit"
    )
    emit(STAT_HEADER)
    exception_runs: list[Run] = [lambda cur, g=g: len(fetch(cur, EXCEPTION_SQL, (g,))) for g in xl]
    log("compact exception scan")
    emit(measure("xl.q9.exceptions", raw, exception_runs, seed="q9.xl", warmup=2, iterations=20).line())
    large_runs: list[Run] = [lambda cur, g=g: len(fetch(cur, EXCEPTION_SQL, (g,))) for g in large]
    emit(measure("l.q9.exceptions", raw, large_runs, seed="q9.l").line())
    emit()
    plans: list[str] = [
        f"exceptions: {explain(conn, EXCEPTION_SQL, (xl[0],))}",
        f"delete without index: {explain(conn, DELETE_SQL, (xl[0], EXPIRE_BEFORE, COMPACT_BATCH))}",
        f"keyset scan: {explain(conn, KEYSET_SQL, (xl[0], 0, 0, 0, COMPACT_SCAN))}",
    ]
    results: list[Compaction] = []
    with raw.cursor() as cur:
        log("compact delete limit without index")
        results.append(compact_delete(cur, xl, "delete_limit.no_index"))
        log("compact remark")
        remark(cur, xl, 7)
        log("compact keyset without index")
        results.append(compact_keyset(cur, xl, "keyset_scan.no_index"))
        log("compact add index")
        start: float = time.perf_counter()
        execute(
            conn,
            "ALTER TABLE report_member ADD INDEX idx_group_last_seen (group_id, last_seen), ALGORITHM=INPLACE, LOCK=NONE",
        )
        add_seconds: float = time.perf_counter() - start
        analyze(conn, ["report_member"])
        sizes: dict[str, int] = index_sizes(conn, "report_member")
        remark(cur, xl, 11)
        plans.append(f"delete with index: {explain(conn, DELETE_SQL, (xl[0], EXPIRE_BEFORE, COMPACT_BATCH))}")
        log("compact delete limit with index")
        results.append(compact_delete(cur, xl, "delete_limit.idx_last_seen"))
        start = time.perf_counter()
        execute(conn, "ALTER TABLE report_member DROP INDEX idx_group_last_seen, ALGORITHM=INPLACE, LOCK=NONE")
        drop_seconds: float = time.perf_counter() - start
    emit(COMPACT_HEADER)
    for result in results:
        emit(result.line())
    emit()
    rows: int = execute(conn, "SELECT COUNT(*) FROM report_member")[0][0]
    extra: int = sizes.get("idx_group_last_seen", 0)
    emit(
        f"KEY idx_group_last_seen (group_id, last_seen): ADD INDEX INPLACE/LOCK=NONE {add_seconds:.2f} s on {rows:,} rows, "
        f"size {mib(extra)} MiB ({extra / rows:.1f} B/row), DROP INDEX {drop_seconds:.2f} s"
    )
    emit("index sizes with idx_group_last_seen (MiB): " + ", ".join(f"{k} {mib(v)}" for k, v in sizes.items()))
    emit()
    emit("## EXPLAIN Q9")
    for plan in plans:
        emit(plan)
    emit()


# ---------------------------------------------------------------- Q10 DDL


X1_ADD: str = (
    "ADD COLUMN original_name VARCHAR(255) COLLATE utf8mb3_bin NULL, ADD COLUMN metric_type VARCHAR(16) NULL, "
    "ADD COLUMN meta JSON NULL, ADD COLUMN meta_fingerprint CHAR(32) NULL, ADD COLUMN meta_seen_at DATETIME(6) NULL"
)
X1_DROP: str = (
    "DROP COLUMN original_name, DROP COLUMN metric_type, DROP COLUMN meta, DROP COLUMN meta_fingerprint, "
    "DROP COLUMN meta_seen_at"
)
BACKFILL_CHUNK: int = 10_000


def timed(conn: pymysql.Connection, sql: str) -> str:
    start: float = time.perf_counter()
    try:
        execute(conn, sql)
    except pymysql.err.MySQLError as exc:
        return f"error {exc.args[0]}: {str(exc.args[1])[:90]}"
    return f"{time.perf_counter() - start:.2f} s"


def backfill(conn: pymysql.Connection, sql: str, last_id: int) -> str:
    chunks: list[float] = []
    start: float = time.perf_counter()
    for low in range(0, last_id, BACKFILL_CHUNK):
        chunk_start: float = time.perf_counter()
        execute(conn, sql, (low, low + BACKFILL_CHUNK))
        chunks.append((time.perf_counter() - chunk_start) * 1000)
    return (
        f"{time.perf_counter() - start:.2f} s ({len(chunks)} chunks of {BACKFILL_CHUNK:,}, "
        f"p50 {percentile(chunks, 0.5):.1f} ms, p95 {percentile(chunks, 0.95):.1f} ms)"
    )


def report_ddl(conn: pymysql.Connection, guard: DiskGuard) -> None:
    rows: int = execute(conn, "SELECT COUNT(*) FROM metadata_timeseriesmetric")[0][0]
    last_id: int = execute(conn, "SELECT MAX(field_id) FROM metadata_timeseriesmetric")[0][0]
    guard.require(3 * GIB, "Q10")
    emit(f"## Q10 DDL on a copy of metadata_timeseriesmetric ({rows:,} rows), autocommit, buffer pool warm")
    steps: list[tuple[str, str]] = []
    execute(conn, "DROP TABLE IF EXISTS ddl_metric")
    execute(conn, "CREATE TABLE ddl_metric LIKE metadata_timeseriesmetric")
    steps.append(
        ("copy rows (INSERT ... SELECT)", timed(conn, "INSERT INTO ddl_metric SELECT * FROM metadata_timeseriesmetric"))
    )
    analyze(conn, ["ddl_metric"])
    steps.append(
        ("X1 ADD COLUMN x5, ALGORITHM=INSTANT", timed(conn, f"ALTER TABLE ddl_metric {X1_ADD}, ALGORITHM=INSTANT"))
    )
    steps.append(
        (
            "X1 ADD INDEX (group_id, original_name), all NULL, INPLACE",
            timed(
                conn,
                "ALTER TABLE ddl_metric ADD INDEX idx_group_original (group_id, original_name), "
                "ALGORITHM=INPLACE, LOCK=NONE",
            ),
        )
    )
    steps.append(
        (
            "ADD INDEX with ALGORITHM=INSTANT",
            timed(conn, "ALTER TABLE ddl_metric ADD INDEX idx_probe (group_id, metric_type), ALGORITHM=INSTANT"),
        )
    )
    steps.append(
        (
            "DROP INDEX, INPLACE",
            timed(conn, "ALTER TABLE ddl_metric DROP INDEX idx_group_original, ALGORITHM=INPLACE, LOCK=NONE"),
        )
    )
    steps.append(
        ("X1 DROP COLUMN x5, ALGORITHM=INSTANT", timed(conn, f"ALTER TABLE ddl_metric {X1_DROP}, ALGORITHM=INSTANT"))
    )
    steps.append(
        (
            "X1 ADD COLUMN x5, INPLACE rebuild (5.7 path)",
            timed(conn, f"ALTER TABLE ddl_metric {X1_ADD}, ALGORITHM=INPLACE, LOCK=NONE"),
        )
    )
    steps.append(
        (
            "X1 backfill UPDATE by field_id range",
            backfill(
                conn,
                "UPDATE ddl_metric t JOIN x1_timeseriesmetric x ON x.field_id = t.field_id "
                "SET t.original_name = x.original_name, t.metric_type = x.metric_type, t.meta = x.meta, "
                "t.meta_fingerprint = x.meta_fingerprint, t.meta_seen_at = x.meta_seen_at "
                "WHERE t.field_id > %s AND t.field_id <= %s AND x.original_name IS NOT NULL",
                last_id,
            ),
        )
    )
    steps.append(
        (
            "X1 ADD INDEX (group_id, original_name), filled, INPLACE",
            timed(
                conn,
                "ALTER TABLE ddl_metric ADD INDEX idx_group_original (group_id, original_name), "
                "ALGORITHM=INPLACE, LOCK=NONE",
            ),
        )
    )
    analyze(conn, ["ddl_metric"])
    after: dict[str, float] = table_sizes(conn, ["ddl_metric"])["ddl_metric"]
    execute(conn, "DROP TABLE ddl_metric")
    for table, key in (("x2_metric_meta", "field_id"), ("x3_metric_meta", "id")):
        scratch: str = f"ddl_{table}"
        execute(conn, f"DROP TABLE IF EXISTS {scratch}")
        steps.append((f"{table[:2].upper()} CREATE TABLE", timed(conn, DDL[table].replace(table, scratch, 1))))
        steps.append(
            (
                f"{table[:2].upper()} backfill INSERT ... SELECT by {key} range",
                backfill(
                    conn, f"INSERT INTO {scratch} SELECT * FROM {table} WHERE {key} > %s AND {key} <= %s", last_id
                ),
            )
        )
        execute(conn, f"DROP TABLE {scratch}")
    for name, result in steps:
        emit(f"{name:<58}{result}")
    emit(
        f"X1 table after rebuild + backfill + index: data {mib(after['data'])} MiB, index {mib(after['index'])} MiB, "
        f"ibd {mib(after['file'])} MiB"
    )
    emit()


# ---------------------------------------------------------------- 体积与画像


def report_profile(groups: Sequence[Group], stats: dict[str, TierStat], scale: str, avg_tags: float) -> None:
    emit(f"## data profile (scale={scale})")
    emit(
        f"{'tier':<5}{'groups':>8}{'metrics/g':>11}{'services':>10}{'scopes/g':>10}{'target/g':>11}"
        f"{'metrics':>11}{'members':>13}{'fanout':>8}{'max/g':>11}"
    )
    total: TierStat = TierStat()
    for tier in TIERS[scale]:
        s: TierStat = stats.get(tier.name, TierStat())
        if not s.groups:
            continue
        emit(
            f"{tier.name:<5}{s.groups:>8,}{tier.metrics:>11,}{tier.services:>10,}{s.scopes / s.groups:>10.1f}"
            f"{tier.members:>11,}{s.metrics:>11,}{s.members:>13,}{s.members / s.metrics:>8.1f}{s.largest:>11,}"
        )
        total.groups += s.groups
        total.metrics += s.metrics
        total.scopes += s.scopes
        total.members += s.members
    emit(
        f"{'all':<5}{total.groups:>8,}{'':>11}{'':>10}{'':>10}{'':>11}{total.metrics:>11,}{total.members:>13,}"
        f"{total.members / total.metrics:>8.1f}"
    )
    emit(f"report scopes {total.scopes:,}, labels {total.scopes * 2:,}, average tag_list size {avg_tags:.1f}")
    for name in ("XL", "L"):
        g: Group | None = next((x for x in groups if x.tier.name == name), None)
        if g is None:
            continue
        shape: Shape = g.shape
        per_service: list[int] = sorted(
            (round(p * shape.eligible(j)) for j, p in enumerate(shape.density)), reverse=True
        )
        density: list[float] = sorted(shape.density, reverse=True)
        emit(
            f"{name} shape: {g.tier.services} services / {len(g.scopes())} scopes, live metrics "
            f"{len(shape.default) + len(shape.custom):,} (default {len(shape.default):,}, custom {len(shape.custom):,}), "
            f"report probability top {density[0]:.3f} median {statistics.median(density):.3f} min {density[-1]:.3f}, "
            f"members per service top {per_service[0]:,} median {int(statistics.median(per_service)):,} "
            f"min {per_service[-1]:,}"
        )
    emit()


def report_member_stats(conn: pymysql.Connection) -> None:
    total, meta, config, expired, stale = execute(
        conn,
        "SELECT COUNT(*), SUM(meta IS NOT NULL), SUM(field_config IS NOT NULL), SUM(last_seen < %s), "
        "SUM(last_seen >= %s AND last_seen < %s) FROM report_member",
        (EXPIRE_BEFORE, EXPIRE_BEFORE, STALE_BEFORE),
    )[0]
    emit(
        f"report_member: {total:,} rows, meta exception {meta:,} ({meta / total:.2%}), field_config override "
        f"{config:,} ({config / total:.3%}), expired {expired:,} ({expired / total:.2%}), "
        f"due for refresh {stale:,} ({stale / total:.2%})"
    )
    emit()


def size_line(table: str, s: dict[str, float]) -> str:
    rows: int = int(s["rows"])
    both: float = s["data"] + s["index"]
    return (
        f"{table:<27}{rows:>12,}{mib(s['data']):>11}{mib(s['index']):>11}{mib(both):>11}{mib(s['file']):>11}"
        f"{both / rows if rows else 0:>9,.0f}{s['file'] / rows if rows else 0:>9,.0f}"
    )


SIZE_HEADER: str = (
    f"{'table':<27}{'rows':>12}{'data MiB':>11}{'index MiB':>11}{'d+i MiB':>11}{'ibd MiB':>11}{'d+i B/r':>9}"
    f"{'ibd B/r':>9}"
)


def report_storage(conn: pymysql.Connection, layout: dict[str, float], layout_indexes: dict[str, int]) -> None:
    tables: list[str] = [*METRIC_TABLES, *SHARED_TABLES]
    sizes: dict[str, dict[str, float]] = table_sizes(conn, tables)
    emit("## table sizes (information_schema after ANALYZE; d+i = data + index; ibd = file on disk)")
    emit(SIZE_HEADER)
    for table in tables:
        emit(size_line(table, sizes[table]))
    emit()
    emit("## per-index size (MiB, mysql.innodb_index_stats)")
    for table in tables:
        emit(f"{table}: " + ", ".join(f"{k} {mib(v)}" for k, v in index_sizes(conn, table).items()))
    emit()
    emit("## candidate totals (TimeSeriesScope excluded, identical for all)")
    emit(f"{'candidate':<20}{'rows':>14}{'d+i MiB':>11}{'ibd MiB':>11}{'meta delta d+i MiB':>20}{'delta B/metric':>16}")
    base: dict[str, float] = sizes["metadata_timeseriesmetric"]
    base_both: float = base["data"] + base["index"]
    metrics: int = int(base["rows"])
    deltas: dict[str, float] = {
        "X1 列扩展": sizes["x1_timeseriesmetric"]["data"] + sizes["x1_timeseriesmetric"]["index"] - base_both,
        "X2 一对一扩展表": sizes["x2_metric_meta"]["data"] + sizes["x2_metric_meta"]["index"],
        "X3 独立定义表": sizes["x3_metric_meta"]["data"] + sizes["x3_metric_meta"]["index"],
    }
    for name, members in CANDIDATES.items():
        rows: int = int(sum(sizes[t]["rows"] for t in members))
        both: float = sum(sizes[t]["data"] + sizes[t]["index"] for t in members)
        file_bytes: float = sum(sizes[t]["file"] for t in members)
        emit(
            f"{name:<17}{rows:>14,}{mib(both):>11}{mib(file_bytes):>11}{mib(deltas[name]):>20}"
            f"{deltas[name] / metrics:>16,.0f}"
        )
    emit()
    member: dict[str, float] = sizes["report_member"]
    emit(
        "## member layout: Django AUTO_INCREMENT id + UNIQUE KEY vs composite PRIMARY KEY (same rows, same load order)"
    )
    emit(SIZE_HEADER)
    emit(size_line("report_member_pk", layout))
    emit(size_line("report_member", member))
    composite: float = layout["data"] + layout["index"]
    django: float = member["data"] + member["index"]
    emit(
        f"Django vs composite: d+i {django / composite - 1:+.1%}, ibd {member['file'] / layout['file'] - 1:+.1%} "
        "(previous round with INT ids and DATETIME: +34%)"
    )
    emit("composite indexes (MiB): " + ", ".join(f"{k} {mib(v)}" for k, v in layout_indexes.items()))
    emit("django indexes (MiB): " + ", ".join(f"{k} {mib(v)}" for k, v in index_sizes(conn, "report_member").items()))
    emit()


# ---------------------------------------------------------------- 入口


def main() -> None:
    global WARMUP, ITERATIONS
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("scale", choices=sorted(TIERS))
    parser.add_argument("--metrics", type=int, default=1_000_000)
    parser.add_argument("--quick", action="store_true", help="冒烟：预热 3 次、计 20 次")
    parser.add_argument("--ddl", action="store_true", help="执行 Q10，指标项表与成员规模无关，只需跑一次")
    args: argparse.Namespace = parser.parse_args()
    if args.quick:
        WARMUP, ITERATIONS = 3, 20
    env: list[str] = []
    environment(env)
    for line in env:
        emit(line)
    reset()
    conn: pymysql.Connection = connect()
    raw: pymysql.Connection = connect(raw=True)
    guard: DiskGuard = DiskGuard(execute(conn, "SELECT @@datadir")[0][0])
    guard.start()
    groups: list[Group] = plan_groups(args.scale, args.metrics)
    target: int = sum(g.members for g in groups)
    emit(
        f"# catalog scale={args.scale}, metrics={sum(g.metrics for g in groups):,}, groups={len(groups):,}, "
        f"member target={target:,}, warmup={WARMUP}, iterations={ITERATIONS}"
    )
    for table in METRIC_TABLES + ["report_scope", "report_scope_label"]:
        execute(conn, DDL[table])

    start: float = time.perf_counter()
    log("load metrics")
    guard.require(4 * GIB, "metric load")
    field_ids, avg_tags = load_metrics(conn, groups)
    analyze(conn, METRIC_TABLES)
    metric_seconds: float = time.perf_counter() - start

    start = time.perf_counter()
    log("load composite member layout")
    guard.require(target * 120, "composite members")
    execute(conn, DDL["report_member_pk"])
    load_members(conn, groups, field_ids, "report_member_pk", with_scopes=True)
    analyze(conn, ["report_scope", "report_scope_label", "report_member_pk"])
    layout: dict[str, float] = table_sizes(conn, ["report_member_pk"])["report_member_pk"]
    layout_indexes: dict[str, int] = index_sizes(conn, "report_member_pk")
    execute(conn, "DROP TABLE report_member_pk")
    layout_seconds: float = time.perf_counter() - start

    start = time.perf_counter()
    log("load django member layout")
    guard.require(target * 160, "members")
    execute(conn, DDL["report_member"])
    stats: dict[str, TierStat] = load_members(conn, groups, field_ids, "report_member", with_scopes=False)
    analyze(conn, ["report_member"])
    member_seconds: float = time.perf_counter() - start
    emit(
        f"load: metrics {metric_seconds:.0f} s, composite members + scopes {layout_seconds:.0f} s, "
        f"django members {member_seconds:.0f} s"
    )
    emit()

    report_profile(groups, stats, args.scale, avg_tags)
    report_member_stats(conn)
    report_storage(conn, layout, layout_indexes)

    log("build samples")
    tiers: list[TierSamples] = build_samples(conn, groups)
    for ts in tiers:
        report_reads(conn, raw, ts)
    report_node_index(conn, raw, tiers)
    report_scan(conn, raw, groups)
    xl: list[int] = tiers[0].groups
    large: list[int] = tiers[1].groups
    report_apply(conn, raw, xl, large)
    report_compact(conn, raw, xl, large)
    if args.ddl:
        log("ddl")
        report_ddl(conn, guard)
    used, _ = guard.sample()
    emit(
        f"## disk: datadir peak {guard.peak / GIB:.2f} GiB, final {used / GIB:.2f} GiB, "
        f"min free {guard.min_free / GIB:.2f} GiB (sampled every 2 s, excludes unlinked sort files in tmpdir)"
    )
    raw.close()
    conn.close()


if __name__ == "__main__":
    main()
