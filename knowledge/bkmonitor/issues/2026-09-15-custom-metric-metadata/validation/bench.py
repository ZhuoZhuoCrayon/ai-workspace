#!/usr/bin/env python3
"""自定义指标来源存储基准。

按上云环境（bkte）抽样画像生成数据，比较「指标 × 来源」的五种存储方式，以及来源标签（__scope）的五种表示。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import statistics
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import pymysql
from pymysql.cursors import Cursor, DictCursor

BASE_TIME: str = "2026-10-11 00:00:00"
NEXT_DAY: str = "2026-10-12 00:00:00"
APP_COUNT: int = int(os.environ.get("CM_BENCH_APPS", "5000"))
LOAD_CHUNK_ROWS: int = 200_000
EXCEPTION_PERCENT: int = 1
SAMPLE_GROUPS: int = 20
SAMPLES_PER_GROUP: int = 5
WRITE_GROUPS: int = 5
WARMUP: int = 30
ITERATIONS: int = 300
SHARD_COUNT: int = 16
DEFAULT_SCOPE: str = "default"

TAGS: tuple[str, ...] = (
    "app_name",
    "service_name",
    "scope_name",
    "instance",
    "namespace",
    "pod",
    "callee_method",
    "callee_service",
    "caller_service",
    "code",
    "code_type",
    "env",
)
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


@dataclass(frozen=True)
class Profile:
    name: str
    metrics: int
    services: int
    pairs: int

    @property
    def density(self) -> float:
        return self.pairs / (self.metrics * self.services)


# bkte 业务 -4228598 在 2026-10-11 11:57 至 12:12 活跃窗口内的抽样，原始查询见 cloud_scale.txt
PROFILES: tuple[Profile, ...] = (
    Profile("L", 217, 28, 4358),
    Profile("M", 145, 6, 705),
    Profile("S", 83, 4, 218),
    Profile("XS", 111, 2, 111),
)
# 大应用在 APM 服务列表中登记的服务数，作为 30 天过期窗口内的来源上界
LARGE_REGISTERED_SERVICES: int = 126


@dataclass
class App:
    group_id: int
    profile: Profile
    services: list[str]
    metrics: list[tuple[str, str]]
    members: list[tuple[int, int]]

    @property
    def table_prefix(self) -> str:
        return f"space_4228598_bkapm_metric_app{self.group_id:04d}-microservices-production"


def profile_of(group_id: int) -> Profile:
    return PROFILES[(group_id - 1) % len(PROFILES)]


def build_app(group_id: int, scale: str) -> App:
    profile: Profile = profile_of(group_id)
    service_count: int = profile.services
    if scale == "s2" and profile.name == "L":
        service_count = LARGE_REGISTERED_SERVICES
    rng: random.Random = random.Random(group_id)
    services: list[str] = [f"app{group_id:04d}-activities-svc-{j:03d}" for j in range(service_count)]
    metrics: list[tuple[str, str]] = [
        ("default" if i % 2 == 0 else "custom", f"{METRIC_STEMS[i % len(METRIC_STEMS)]}_{i:03d}")
        for i in range(profile.metrics)
    ]
    members: list[tuple[int, int]] = []
    for i in range(profile.metrics):
        chosen: list[int] = [j for j in range(service_count) if rng.random() < profile.density]
        members.extend((i, j) for j in (chosen or [i % service_count]))
    return App(group_id, profile, services, metrics, members)


def large_group_ids() -> list[int]:
    candidates: list[int] = [g for g in range(1, APP_COUNT + 1) if profile_of(g).name == "L"]
    return random.Random(7).sample(candidates, SAMPLE_GROUPS)


def write_group_ids(count: int) -> list[int]:
    """写入用例按方案分配互不重叠的大分组，前 SAMPLE_GROUPS 个与读取样本一致，S2 的 A 只装载这些分组。"""
    chosen: list[int] = large_group_ids()
    taken: set[int] = set(chosen)
    extra: list[int] = [g for g in range(1, APP_COUNT + 1) if profile_of(g).name == "L" and g not in taken]
    return chosen + random.Random(13).sample(extra, max(0, count - len(chosen)))


def report_scope_labels(service: str, scope_name: str) -> dict[str, str]:
    return {"scope_name": scope_name, "service_name": service}


def apm_raw_scope(service: str, scope_name: str) -> str:
    """Collector APM 范围编码：各部分先转义 % 与 -，再用 - 连接。"""

    def escape(part: str) -> str:
        return part.replace("%", "%25").replace("-", "%2D")

    return f"{escape(service)}-{escape(scope_name)}"


def tag_list(metric_idx: int) -> str:
    return json.dumps(list(TAGS[: 8 + metric_idx % 5]))


def meta_json(field_name: str, unit: str) -> str:
    return json.dumps(
        {
            "original_name": field_name,
            "metric_type": "histogram",
            "unit": unit,
            "description": f"{field_name} description",
            "temporality": "delta",
            "interval": None,
            "usage": "sum",
        }
    )


def source_key(labels: dict[str, str]) -> str:
    return "||".join(f"{k}:{labels[k]}" for k in sorted(labels))


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def is_exception(group_id: int, metric_idx: int, service_idx: int) -> bool:
    return (group_id * 7919 + metric_idx * 104729 + service_idx * 1299709) % 100 < EXCEPTION_PERCENT


# ---------------------------------------------------------------- MySQL


def connect(raw: bool = False) -> pymysql.Connection:
    """raw 连接不做类型转换，计时只覆盖服务端执行与传输，不含 Python 解码 datetime、JSON 的开销。"""
    encoders_only: dict[Any, Any] = {k: v for k, v in pymysql.converters.conversions.items() if not isinstance(k, int)}
    options: dict[str, Any] = {"conv": encoders_only} if raw else {}
    return pymysql.connect(
        unix_socket=os.environ["CM_BENCH_SOCKET"],
        user="root",
        database="cm_bench",
        local_infile=True,
        autocommit=True,
        charset="utf8mb4",
        **options,
    )


def reset() -> None:
    conn: pymysql.Connection = connect()
    for (table,) in execute(conn, "SHOW TABLES"):
        execute(conn, f"DROP TABLE IF EXISTS {table}")
    conn.close()


def execute(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None = None) -> tuple[Any, ...]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def fetch(cur: Cursor, sql: str, params: Sequence[Any]) -> tuple[Any, ...]:
    cur.execute(sql, params)
    return cur.fetchall()


class Loader:
    """把行写入临时 TSV，按块执行 LOAD DATA LOCAL INFILE。"""

    def __init__(self, conn: pymysql.Connection, table: str, columns: Sequence[str], set_clause: str = "") -> None:
        self.conn = conn
        self.table = table
        self.columns = columns
        self.set_clause = set_clause
        self.rows: list[str] = []
        self.total: int = 0

    def add(self, row: Sequence[Any]) -> None:
        self.rows.append("\t".join("\\N" if v is None else str(v) for v in row))
        if len(self.rows) >= LOAD_CHUNK_ROWS:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False, encoding="utf-8") as fp:
            fp.write("\n".join(self.rows) + "\n")
            path: str = fp.name
        try:
            execute(
                self.conn,
                f"LOAD DATA LOCAL INFILE %s INTO TABLE {self.table} CHARACTER SET utf8mb4 "
                f"FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' ({', '.join(self.columns)}) {self.set_clause}",
                (path,),
            )
        finally:
            os.unlink(path)
        self.total += len(self.rows)
        self.rows = []


METRIC_COLUMNS: str = """
    field_id INT NOT NULL PRIMARY KEY,
    group_id INT NOT NULL,
    scope_id INT NULL,
    table_id VARCHAR(255) NOT NULL DEFAULT '',
    field_scope VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
    field_name VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
    tag_list LONGTEXT NOT NULL,
    field_config JSON NOT NULL,
    create_time DATETIME(6) NULL,
    last_modify_time DATETIME(6) NOT NULL,
    label VARCHAR(255) NOT NULL DEFAULT '',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    last_index INT NOT NULL DEFAULT 0
"""
METRIC_INDEXES: str = """
    UNIQUE KEY uk_identity (group_id, field_scope, field_name),
    KEY idx_group (group_id),
    KEY idx_scope (scope_id),
    KEY idx_label (label),
    KEY idx_active (is_active),
    KEY idx_group_scope_field (group_id, scope_id, field_name)
"""
SOURCE_COLUMNS: str = """
    source_id INT NOT NULL PRIMARY KEY,
    group_id INT NOT NULL,
    source_hash BINARY(16) NOT NULL,
    source_key VARCHAR(1024) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    labels JSON NOT NULL,
    last_seen DATETIME NOT NULL
"""
TABLE_DDL: dict[str, str] = {
    "a_metric": f"CREATE TABLE a_metric ({METRIC_COLUMNS}, meta JSON NULL, {METRIC_INDEXES}) DEFAULT CHARSET=utf8mb3",
    "b_metric": f"CREATE TABLE b_metric ({METRIC_COLUMNS}, {METRIC_INDEXES}) DEFAULT CHARSET=utf8mb3",
    "b_meta": """CREATE TABLE b_meta (
        id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        field_scope VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
        field_name VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
        source_id INT NOT NULL DEFAULT 0,
        meta JSON NOT NULL,
        fingerprint CHAR(32) NOT NULL,
        seen_at DATETIME NOT NULL,
        UNIQUE KEY uk_meta (group_id, field_scope, field_name, source_id)
    ) DEFAULT CHARSET=utf8mb3""",
    "b_source": f"CREATE TABLE b_source ({SOURCE_COLUMNS}, UNIQUE KEY uk_source (group_id, source_hash))",
    "b_member": """CREATE TABLE b_member (
        group_id INT NOT NULL,
        source_id INT NOT NULL,
        field_id INT NOT NULL,
        last_seen DATETIME NOT NULL,
        field_config JSON NULL,
        PRIMARY KEY (group_id, source_id, field_id),
        KEY idx_field (group_id, field_id)
    )""",
    "c_metric": f"""CREATE TABLE c_metric ({METRIC_COLUMNS}, source_ids JSON NOT NULL, {METRIC_INDEXES},
        KEY idx_sources (group_id, (CAST(source_ids->'$' AS UNSIGNED ARRAY)))) DEFAULT CHARSET=utf8mb3""",
    "d_source": f"""CREATE TABLE d_source ({SOURCE_COLUMNS}, field_ids JSON NOT NULL,
        UNIQUE KEY uk_source (group_id, source_hash),
        KEY idx_fields (group_id, (CAST(field_ids->'$' AS UNSIGNED ARRAY))))""",
    "e_meta": """CREATE TABLE e_meta (
        meta_id INT NOT NULL PRIMARY KEY,
        group_id INT NOT NULL,
        field_name VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
        original_name VARCHAR(255) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin NOT NULL,
        metric_type VARCHAR(16) NOT NULL,
        meta JSON NOT NULL,
        fingerprint CHAR(32) NOT NULL,
        seen_at DATETIME NOT NULL,
        UNIQUE KEY uk_meta (group_id, field_name),
        KEY idx_family (group_id, original_name)
    ) DEFAULT CHARSET=utf8mb3""",
    "e_scope": """CREATE TABLE e_scope (
        scope_id INT NOT NULL PRIMARY KEY,
        group_id INT NOT NULL,
        scope_type VARCHAR(32) NOT NULL,
        scope_hash BINARY(16) NOT NULL,
        raw_scope VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        labels JSON NOT NULL,
        last_seen DATETIME NOT NULL,
        UNIQUE KEY uk_scope (group_id, scope_hash)
    )""",
    "e_label": """CREATE TABLE e_label (
        group_id INT NOT NULL,
        label_key VARCHAR(64) NOT NULL,
        label_value VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        scope_id INT NOT NULL,
        PRIMARY KEY (group_id, label_key, label_value, scope_id)
    )""",
    "e_member": """CREATE TABLE e_member (
        group_id INT NOT NULL,
        scope_id INT NOT NULL,
        meta_id INT NOT NULL,
        last_seen DATETIME NOT NULL,
        meta JSON NULL,
        field_config JSON NULL,
        PRIMARY KEY (group_id, scope_id, meta_id),
        KEY idx_meta (group_id, meta_id)
    )""",
}
SCHEME_TABLES: dict[str, list[str]] = {
    "a": ["a_metric"],
    "b": ["b_metric", "b_meta", "b_source", "b_member"],
    "c": ["c_metric", "b_meta", "b_source"],
    "d": ["b_metric", "b_meta", "d_source"],
    "e": ["b_metric", "e_meta", "e_scope", "e_label", "e_member"],
}
SCHEME_NAMES: dict[str, str] = {
    "a": "A 展开：来源并入 field_scope",
    "b": "B 成员表：来源字典 + 成员行",
    "c": "C 指标侧列表：source_ids JSON",
    "d": "D 来源侧列表：field_ids JSON",
    "e": "E 终版：定义 + 上报范围 + 成员（例外内联）",
}
METRIC_LOAD_COLUMNS: list[str] = [
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


def metric_row(app: App, field_id: int, metric_idx: int, field_scope: str, when: str = BASE_TIME) -> list[Any]:
    name: str = app.metrics[metric_idx][1]
    return [
        field_id,
        app.group_id,
        metric_idx % 7 + 1,
        f"{app.table_prefix}.{name}",
        field_scope,
        name,
        tag_list(metric_idx),
        "{}",
        when,
        when,
        "",
        1,
        0,
    ]


# ---------------------------------------------------------------- 数据装载


def load(scale: str, schemes: Sequence[str], only_groups: set[int] | None = None) -> dict[str, int]:
    conn: pymysql.Connection = connect()
    tables: list[str] = sorted({t for s in schemes for t in SCHEME_TABLES[s]})
    for table in tables:
        execute(conn, f"DROP TABLE IF EXISTS {table}")
        execute(conn, TABLE_DDL[table])
    source_cols: list[str] = ["source_id", "group_id", "@h", "source_key", "labels", "last_seen"]
    columns: dict[str, tuple[list[str], str]] = {
        "a_metric": ([*METRIC_LOAD_COLUMNS, "meta"], ""),
        "b_metric": (METRIC_LOAD_COLUMNS, ""),
        "b_meta": (["group_id", "field_scope", "field_name", "source_id", "meta", "fingerprint", "seen_at"], ""),
        "b_source": (source_cols, "SET source_hash = UNHEX(@h)"),
        "b_member": (["group_id", "source_id", "field_id", "last_seen"], ""),
        "c_metric": ([*METRIC_LOAD_COLUMNS, "source_ids"], ""),
        "d_source": ([*source_cols, "field_ids"], "SET source_hash = UNHEX(@h)"),
        "e_meta": (
            ["meta_id", "group_id", "field_name", "original_name", "metric_type", "meta", "fingerprint", "seen_at"],
            "",
        ),
        "e_scope": (
            ["scope_id", "group_id", "scope_type", "@h", "raw_scope", "labels", "last_seen"],
            "SET scope_hash = UNHEX(@h)",
        ),
        "e_label": (["group_id", "label_key", "label_value", "scope_id"], ""),
        "e_member": (["group_id", "scope_id", "meta_id", "last_seen", "meta"], ""),
    }
    loaders: dict[str, Loader] = {t: Loader(conn, t, *columns[t]) for t in tables}

    a_field_id: int = 0
    field_id: int = 0
    source_id: int = 0
    scope_id: int = 0
    for g in range(1, APP_COUNT + 1):
        if only_groups is not None and g not in only_groups:
            continue
        app: App = build_app(g, scale)
        field_ids: list[int] = list(range(field_id + 1, field_id + 1 + len(app.metrics)))
        source_ids: list[int] = list(range(source_id + 1, source_id + 1 + len(app.services)))
        field_id += len(app.metrics)
        source_id += len(app.services)
        sources_of_metric: dict[int, list[int]] = {}
        metrics_of_source: dict[int, list[int]] = {}
        for metric_idx, service_idx in app.members:
            sources_of_metric.setdefault(metric_idx, []).append(source_ids[service_idx])
            metrics_of_source.setdefault(service_idx, []).append(field_ids[metric_idx])

        for metric_idx, (scope_name, name) in enumerate(app.metrics):
            row: list[Any] = metric_row(app, field_ids[metric_idx], metric_idx, DEFAULT_SCOPE)
            meta: str = meta_json(name, "s")
            if "b_metric" in loaders:
                loaders["b_metric"].add(row)
            if "c_metric" in loaders:
                loaders["c_metric"].add([*row, json.dumps(sources_of_metric[metric_idx])])
            if "b_meta" in loaders:
                loaders["b_meta"].add([g, DEFAULT_SCOPE, name, 0, meta, md5_hex(meta), BASE_TIME])
            if "e_meta" in loaders:
                loaders["e_meta"].add(
                    [field_ids[metric_idx], g, name, name, "histogram", meta, md5_hex(meta), BASE_TIME]
                )

        scope_ids: dict[tuple[int, str], int] = {}
        if "e_scope" in loaders:
            for service_idx, scope_name in sorted({(j, app.metrics[i][0]) for i, j in app.members}):
                scope_id += 1
                scope_ids[(service_idx, scope_name)] = scope_id
                scope_service: str = app.services[service_idx]
                scope_labels: dict[str, str] = report_scope_labels(scope_service, scope_name)
                scope_key: str = source_key(scope_labels)
                loaders["e_scope"].add(
                    [
                        scope_id,
                        g,
                        "APM",
                        md5_hex(scope_key),
                        apm_raw_scope(scope_service, scope_name),
                        json.dumps(scope_labels),
                        BASE_TIME,
                    ]
                )
                for k, v in sorted(scope_labels.items()):
                    loaders["e_label"].add([g, k, v, scope_id])

        for service_idx, service in enumerate(app.services):
            labels: dict[str, str] = {"service_name": service}
            key: str = source_key(labels)
            source_row: list[Any] = [source_ids[service_idx], g, md5_hex(key), key, json.dumps(labels), BASE_TIME]
            if "b_source" in loaders:
                loaders["b_source"].add(source_row)
            if "d_source" in loaders:
                loaders["d_source"].add([*source_row, json.dumps(metrics_of_source.get(service_idx, []))])

        for metric_idx, service_idx in app.members:
            scope_name, name = app.metrics[metric_idx]
            exceptional: bool = is_exception(g, metric_idx, service_idx)
            if "a_metric" in loaders:
                a_field_id += 1
                field_scope: str = f"{scope_name}||{app.services[service_idx]}"
                loaders["a_metric"].add(
                    [
                        *metric_row(app, a_field_id, metric_idx, field_scope),
                        meta_json(name, "ms" if exceptional else "s"),
                    ]
                )
            if "b_member" in loaders:
                loaders["b_member"].add([g, source_ids[service_idx], field_ids[metric_idx], BASE_TIME])
            if "b_meta" in loaders and exceptional:
                meta = meta_json(name, "ms")
                loaders["b_meta"].add([g, DEFAULT_SCOPE, name, source_ids[service_idx], meta, md5_hex(meta), BASE_TIME])
            if "e_member" in loaders:
                loaders["e_member"].add(
                    [
                        g,
                        scope_ids[(service_idx, scope_name)],
                        field_ids[metric_idx],
                        BASE_TIME,
                        meta_json(name, "ms") if exceptional else None,
                    ]
                )

    counts: dict[str, int] = {}
    for table, loader in loaders.items():
        loader.flush()
        counts[table] = loader.total
        execute(conn, f"ANALYZE TABLE {table}")
    conn.close()
    return counts


# ---------------------------------------------------------------- 存储


def table_sizes(conn: pymysql.Connection, tables: Iterable[str]) -> dict[str, dict[str, float]]:
    datadir: str = execute(conn, "SELECT @@datadir")[0][0]
    result: dict[str, dict[str, float]] = {}
    for table in tables:
        rows: int = execute(conn, f"SELECT COUNT(*) FROM {table}")[0][0]
        data, index = execute(
            conn,
            "SELECT data_length, index_length FROM information_schema.TABLES "
            "WHERE table_schema = 'cm_bench' AND table_name = %s",
            (table,),
        )[0]
        ibd: str = os.path.join(datadir, "cm_bench", f"{table}.ibd")
        result[table] = {"rows": rows, "data": data, "index": index, "file": os.path.getsize(ibd)}
    return result


def mib(value: float) -> str:
    return f"{value / 1024 / 1024:,.1f}"


def report_storage(schemes: Sequence[str], out: list[str]) -> None:
    conn: pymysql.Connection = connect()
    tables: list[str] = sorted({t for s in schemes for t in SCHEME_TABLES[s]})
    sizes: dict[str, dict[str, float]] = table_sizes(conn, tables)
    out.append("## table sizes (data/index from information_schema after ANALYZE, ibd = file on disk)")
    out.append(f"{'table':<14}{'rows':>14}{'data MiB':>11}{'index MiB':>11}{'ibd MiB':>11}{'ibd B/row':>11}")
    for table in tables:
        s: dict[str, float] = sizes[table]
        per_row: float = s["file"] / s["rows"] if s["rows"] else 0
        out.append(
            f"{table:<14}{int(s['rows']):>14,}{mib(s['data']):>11}{mib(s['index']):>11}{mib(s['file']):>11}"
            f"{per_row:>11,.0f}"
        )
    out.append("")
    out.append("## scheme totals")
    out.append(f"{'scheme':<36}{'rows':>14}{'ibd MiB':>11}")
    for scheme in schemes:
        rows: int = int(sum(sizes[t]["rows"] for t in SCHEME_TABLES[scheme]))
        file_bytes: float = sum(sizes[t]["file"] for t in SCHEME_TABLES[scheme])
        out.append(f"{SCHEME_NAMES[scheme]:<36}{rows:>14,}{mib(file_bytes):>11}")
    out.append("")
    conn.close()


# ---------------------------------------------------------------- 计时


@dataclass
class Timing:
    name: str
    samples: list[float] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)

    def line(self) -> str:
        ordered: list[float] = sorted(self.samples)

        def pct(p: float) -> float:
            return ordered[min(len(ordered) - 1, int(len(ordered) * p))]

        return (
            f"{self.name:<40}{statistics.median(ordered):>9.3f}{pct(0.95):>9.3f}{pct(0.99):>9.3f}"
            f"{statistics.mean(self.rows):>10.1f}"
        )


TIMING_HEADER: str = f"{'case':<40}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'rows':>10}"
Run = Callable[[Cursor], int]


def run_case(name: str, conn: pymysql.Connection, runs: Sequence[Run], seed: str = "") -> Timing:
    timing: Timing = Timing(name)
    rng: random.Random = random.Random(seed or name)
    with conn.cursor() as cur:
        for i in range(WARMUP + ITERATIONS):
            run: Run = runs[rng.randrange(len(runs))]
            start: float = time.perf_counter()
            rows: int = run(cur)
            elapsed: float = (time.perf_counter() - start) * 1000
            if i >= WARMUP:
                timing.samples.append(elapsed)
                timing.rows.append(rows)
    return timing


def explain(conn: pymysql.Connection, sql: str, params: Sequence[Any]) -> str:
    with conn.cursor(DictCursor) as cur:
        cur.execute("EXPLAIN " + sql, params)
        plans: list[dict[str, Any]] = list(cur.fetchall())
    return "; ".join(f"{p['table']}:{p['key'] or 'ALL'}/{p['type']}" for p in plans)


# ---------------------------------------------------------------- 查询


@dataclass
class Sample:
    group_id: int
    service: str
    service_scopes: tuple[str, str]
    field_name: str
    source_id: int = 0
    field_id: int = 0


def build_samples(conn: pymysql.Connection, scale: str, with_ids: bool) -> list[Sample]:
    """来源与指标 ID 取自 b_source、b_metric，C、D 方案沿用同一套编号。"""
    samples: list[Sample] = []
    for g in large_group_ids():
        app: App = build_app(g, scale)
        rng: random.Random = random.Random(g)
        for _ in range(SAMPLES_PER_GROUP):
            metric_idx, service_idx = app.members[rng.randrange(len(app.members))]
            service: str = app.services[service_idx]
            name: str = app.metrics[metric_idx][1]
            sample: Sample = Sample(g, service, (f"default||{service}", f"custom||{service}"), name)
            if with_ids:
                sample.source_id = execute(
                    conn,
                    "SELECT source_id FROM b_source WHERE group_id = %s AND source_hash = UNHEX(%s)",
                    (g, md5_hex(source_key({"service_name": service}))),
                )[0][0]
                sample.field_id = execute(
                    conn,
                    "SELECT field_id FROM b_metric WHERE group_id = %s AND field_scope = %s AND field_name = %s",
                    (g, DEFAULT_SCOPE, name),
                )[0][0]
            samples.append(sample)
    return samples


DEF_JOIN: str = (
    "LEFT JOIN b_meta d ON d.group_id = m.group_id AND d.field_scope = m.field_scope "
    "AND d.field_name = m.field_name AND d.source_id = 0 "
)


def exc_join(source_expr: str) -> str:
    return (
        "LEFT JOIN b_meta e ON e.group_id = m.group_id AND e.field_scope = m.field_scope "
        f"AND e.field_name = m.field_name AND e.source_id = {source_expr} "
    )


@dataclass
class Case:
    runs: list[Run]
    sql: str
    params: tuple[Any, ...]


def make_case(
    samples: Sequence[Sample],
    fn: Callable[[Cursor, Sample], int],
    sql: str,
    params_of: Callable[[Sample], tuple[Any, ...]],
) -> Case:
    return Case([lambda cur, s=s: fn(cur, s) for s in samples], sql, params_of(samples[0]))


def sql_case(samples: Sequence[Sample], sql: str, params_of: Callable[[Sample], tuple[Any, ...]]) -> Case:
    return make_case(samples, lambda cur, s: len(fetch(cur, sql, params_of(s))), sql, params_of)


def cases_a(samples: Sequence[Sample]) -> dict[str, Case]:
    page: str = (
        "SELECT field_id, field_name, field_scope, tag_list, field_config, meta FROM a_metric "
        "WHERE group_id = %s AND field_scope IN (%s, %s) ORDER BY field_name"
    )
    by_service: Callable[[Sample], tuple[Any, ...]] = lambda s: (s.group_id, *s.service_scopes)
    by_group: Callable[[Sample], tuple[Any, ...]] = lambda s: (s.group_id,)
    return {
        "service_page_50": sql_case(samples, page + " LIMIT 50", by_service),
        "service_all": sql_case(samples, page, by_service),
        "metric_sources": sql_case(
            samples,
            "SELECT field_scope FROM a_metric WHERE group_id = %s AND field_name = %s",
            lambda s: (s.group_id, s.field_name),
        ),
        "group_definitions": sql_case(
            samples,
            "SELECT field_name, field_scope, field_config, meta, tag_list FROM a_metric WHERE group_id = %s",
            by_group,
        ),
        "discovery_read": sql_case(
            samples,
            "SELECT field_id, field_name, field_scope, tag_list, field_config, last_modify_time, is_active, scope_id "
            "FROM a_metric WHERE group_id = %s",
            by_group,
        ),
    }


def discovery_sql(metric_table: str, extra: str = "") -> str:
    return (
        "SELECT field_id, field_name, field_scope, tag_list, field_config, last_modify_time, is_active, scope_id"
        f"{extra} FROM {metric_table} WHERE group_id = %s"
    )


def definitions_case(samples: Sequence[Sample], metric_table: str) -> Case:
    return sql_case(
        samples,
        f"SELECT m.field_name, m.field_scope, m.field_config, d.meta, m.tag_list FROM {metric_table} m {DEF_JOIN}"
        "WHERE m.group_id = %s",
        lambda s: (s.group_id,),
    )


def cases_b(samples: Sequence[Sample], member_table: str = "b_member") -> dict[str, Case]:
    page: str = (
        "SELECT m.field_id, m.field_name, m.field_scope, m.tag_list, m.field_config, s.field_config, d.meta, e.meta "
        f"FROM {member_table} s JOIN b_metric m ON m.field_id = s.field_id {DEF_JOIN}{exc_join('s.source_id')}"
        "WHERE s.group_id = %s AND s.source_id = %s ORDER BY m.field_name"
    )
    by_source: Callable[[Sample], tuple[Any, ...]] = lambda s: (s.group_id, s.source_id)
    disc: str = discovery_sql("b_metric")

    def discovery(cur: Cursor, s: Sample) -> int:
        n: int = len(fetch(cur, disc, (s.group_id,)))
        n += len(
            fetch(cur, f"SELECT source_id, field_id, last_seen FROM {member_table} WHERE group_id = %s", (s.group_id,))
        )
        n += len(fetch(cur, "SELECT source_id, source_hash FROM b_source WHERE group_id = %s", (s.group_id,)))
        return n

    return {
        "service_page_50": sql_case(samples, page + " LIMIT 50", by_source),
        "service_all": sql_case(samples, page, by_source),
        "metric_sources": sql_case(
            samples,
            f"SELECT src.source_key FROM {member_table} s JOIN b_source src ON src.source_id = s.source_id "
            "WHERE s.group_id = %s AND s.field_id = %s",
            lambda s: (s.group_id, s.field_id),
        ),
        "group_definitions": definitions_case(samples, "b_metric"),
        "discovery_read": make_case(samples, discovery, disc, lambda s: (s.group_id,)),
    }


def cases_c(samples: Sequence[Sample]) -> dict[str, Case]:
    page: str = (
        "SELECT m.field_id, m.field_name, m.field_scope, m.tag_list, m.field_config, d.meta, e.meta "
        f"FROM c_metric m {DEF_JOIN}{exc_join('%s')}"
        "WHERE m.group_id = %s AND %s MEMBER OF (m.source_ids->'$') ORDER BY m.field_name"
    )
    by_source: Callable[[Sample], tuple[Any, ...]] = lambda s: (s.source_id, s.group_id, s.source_id)
    disc: str = discovery_sql("c_metric", ", source_ids")

    def metric_sources(cur: Cursor, s: Sample) -> int:
        ids: list[int] = json.loads(
            fetch(cur, "SELECT source_ids FROM c_metric WHERE field_id = %s", (s.field_id,))[0][0]
        )
        marks: str = ", ".join(["%s"] * len(ids))
        return len(fetch(cur, f"SELECT source_key FROM b_source WHERE source_id IN ({marks})", ids))

    def discovery(cur: Cursor, s: Sample) -> int:
        n: int = len(fetch(cur, disc, (s.group_id,)))
        n += len(fetch(cur, "SELECT source_id, source_hash FROM b_source WHERE group_id = %s", (s.group_id,)))
        return n

    return {
        "service_page_50": sql_case(samples, page + " LIMIT 50", by_source),
        "service_all": sql_case(samples, page, by_source),
        "metric_sources": make_case(
            samples, metric_sources, "SELECT source_ids FROM c_metric WHERE field_id = %s", lambda s: (s.field_id,)
        ),
        "group_definitions": definitions_case(samples, "c_metric"),
        "discovery_read": make_case(samples, discovery, disc, lambda s: (s.group_id,)),
    }


def cases_d(samples: Sequence[Sample]) -> dict[str, Case]:
    page_head: str = "SELECT field_ids FROM d_source WHERE source_id = %s"
    page_tail: str = (
        "SELECT m.field_id, m.field_name, m.field_scope, m.tag_list, m.field_config, d.meta, e.meta "
        f"FROM b_metric m {DEF_JOIN}{exc_join('%s')}WHERE m.field_id IN ({{marks}}) ORDER BY m.field_name"
    )
    disc: str = discovery_sql("b_metric")

    def page(cur: Cursor, s: Sample, limit: str) -> int:
        ids: list[int] = json.loads(fetch(cur, page_head, (s.source_id,))[0][0])
        sql: str = page_tail.format(marks=", ".join(["%s"] * len(ids))) + limit
        return len(fetch(cur, sql, (s.source_id, *ids)))

    def discovery(cur: Cursor, s: Sample) -> int:
        n: int = len(fetch(cur, disc, (s.group_id,)))
        n += len(
            fetch(cur, "SELECT source_id, source_hash, field_ids FROM d_source WHERE group_id = %s", (s.group_id,))
        )
        return n

    by_source: Callable[[Sample], tuple[Any, ...]] = lambda s: (s.source_id,)
    return {
        "service_page_50": make_case(samples, lambda cur, s: page(cur, s, " LIMIT 50"), page_head, by_source),
        "service_all": make_case(samples, lambda cur, s: page(cur, s, ""), page_head, by_source),
        "metric_sources": sql_case(
            samples,
            "SELECT source_key FROM d_source WHERE group_id = %s AND %s MEMBER OF (field_ids->'$')",
            lambda s: (s.group_id, s.field_id),
        ),
        "group_definitions": definitions_case(samples, "b_metric"),
        "discovery_read": make_case(samples, discovery, disc, lambda s: (s.group_id,)),
    }


def cases_e(samples: Sequence[Sample], member_table: str = "e_member", label_table: str = "e_label") -> dict[str, Case]:
    """服务视图经标签倒排定位上报范围，成员行引用定义，指标项按自然键关联，例外与按范围覆盖读自成员行。"""
    page: str = (
        "SELECT m.field_id, m.field_name, m.tag_list, m.field_config, s.field_config, d.meta, s.meta "
        f"FROM {label_table} l JOIN {member_table} s ON s.group_id = l.group_id AND s.scope_id = l.scope_id "
        "JOIN e_meta d ON d.meta_id = s.meta_id "
        "JOIN b_metric m ON m.group_id = d.group_id AND m.field_scope = 'default' AND m.field_name = d.field_name "
        "WHERE l.group_id = %s AND l.label_key = 'service_name' AND l.label_value = %s ORDER BY d.field_name"
    )
    by_service: Callable[[Sample], tuple[Any, ...]] = lambda s: (s.group_id, s.service)
    disc: str = discovery_sql("b_metric")

    def discovery(cur: Cursor, s: Sample) -> int:
        n: int = len(fetch(cur, disc, (s.group_id,)))
        n += len(
            fetch(
                cur, "SELECT meta_id, field_name, fingerprint, seen_at FROM e_meta WHERE group_id = %s", (s.group_id,)
            )
        )
        n += len(
            fetch(
                cur,
                f"SELECT scope_id, meta_id, last_seen, meta IS NOT NULL FROM {member_table} WHERE group_id = %s",
                (s.group_id,),
            )
        )
        n += len(fetch(cur, "SELECT scope_id, scope_hash, last_seen FROM e_scope WHERE group_id = %s", (s.group_id,)))
        return n

    return {
        "service_page_50": sql_case(samples, page + " LIMIT 50", by_service),
        "service_all": sql_case(samples, page, by_service),
        "metric_sources": sql_case(
            samples,
            f"SELECT sc.labels FROM e_meta d JOIN {member_table} s ON s.group_id = d.group_id AND s.meta_id = d.meta_id "
            "JOIN e_scope sc ON sc.scope_id = s.scope_id WHERE d.group_id = %s AND d.field_name = %s",
            lambda s: (s.group_id, s.field_name),
        ),
        "group_definitions": sql_case(
            samples,
            "SELECT m.field_name, m.field_config, d.meta, m.tag_list FROM b_metric m "
            "LEFT JOIN e_meta d ON d.group_id = m.group_id AND d.field_name = m.field_name WHERE m.group_id = %s",
            lambda s: (s.group_id,),
        ),
        "discovery_read": make_case(samples, discovery, disc, lambda s: (s.group_id,)),
    }


CASE_BUILDERS: dict[str, Callable[[Sequence[Sample]], dict[str, Case]]] = {
    "a": cases_a,
    "b": cases_b,
    "c": cases_c,
    "d": cases_d,
    "e": cases_e,
}


def report_queries(scale: str, schemes: Sequence[str], out: list[str]) -> None:
    conn: pymysql.Connection = connect()
    raw: pymysql.Connection = connect(raw=True)
    samples: list[Sample] = build_samples(conn, scale, with_ids=any(s != "a" for s in schemes))
    out.append(
        f"## read latency on large groups: {SAMPLE_GROUPS} groups x {SAMPLES_PER_GROUP} samples, "
        f"{ITERATIONS} runs after {WARMUP} warmup, wall time over unix socket without type conversion"
    )
    out.append(TIMING_HEADER)
    plans: list[str] = []
    for scheme in schemes:
        for name, case in CASE_BUILDERS[scheme](samples).items():
            out.append(run_case(f"{scheme}.{name}", raw, case.runs).line())
            plans.append(f"{scheme}.{name}: {explain(conn, case.sql, case.params)}")
    out.append("")
    out.append("## EXPLAIN (table:key/type)")
    out.extend(plans)
    out.append("")
    raw.close()
    conn.close()


# ---------------------------------------------------------------- 写入


def report_writes(scale: str, schemes: Sequence[str], out: list[str]) -> None:
    """每个方案使用互不重叠的大分组，先做一次日常刷新，再做一次 10% 服务替换。"""
    conn: pymysql.Connection = connect()
    groups: list[int] = write_group_ids(WRITE_GROUPS * len(schemes))
    out.append(f"## discovery writes per large group: {WRITE_GROUPS} groups each, autocommit, wall ms")
    out.append(f"{'case':<40}{'median':>10}{'min':>10}{'max':>10}{'statements':>12}{'rows':>10}")
    for offset, scheme in enumerate(schemes):
        chosen: list[int] = groups[offset * WRITE_GROUPS : (offset + 1) * WRITE_GROUPS]
        results: dict[str, list[tuple[float, int, int]]] = {"daily_refresh": [], "churn_10pct_services": []}
        for g in chosen:
            app: App = build_app(g, scale)
            results["daily_refresh"].append(daily_refresh(conn, scheme, app))
            results["churn_10pct_services"].append(churn(conn, scheme, app))
        for label, values in results.items():
            elapsed: list[float] = [v[0] for v in values]
            out.append(
                f"{scheme + '.' + label:<40}{statistics.median(elapsed):>10.1f}{min(elapsed):>10.1f}"
                f"{max(elapsed):>10.1f}{statistics.median(v[1] for v in values):>12,.0f}"
                f"{statistics.median(v[2] for v in values):>10,.0f}"
            )
    out.append("")
    conn.close()


def daily_refresh(conn: pymysql.Connection, scheme: str, app: App) -> tuple[float, int, int]:
    """bmw 每行每 24 h 刷新一次 last_modify_time，指标行逐行 UPDATE；成员行按 1,000 行批量 upsert。"""
    g: int = app.group_id
    metric_table: str = {"a": "a_metric", "c": "c_metric"}.get(scheme, "b_metric")
    with conn.cursor() as cur:
        metrics: tuple[Any, ...] = fetch(
            cur, f"SELECT field_id, tag_list FROM {metric_table} WHERE group_id = %s", (g,)
        )
        member_table: str = {"b": "b_member", "e": "e_member"}.get(scheme, "")
        member_cols: str = "source_id, field_id" if scheme == "b" else "scope_id, meta_id"
        members: tuple[Any, ...] = (
            fetch(cur, f"SELECT {member_cols} FROM {member_table} WHERE group_id = %s", (g,)) if member_table else ()
        )
        sources: tuple[Any, ...] = (
            fetch(cur, "SELECT source_id FROM d_source WHERE group_id = %s", (g,)) if scheme == "d" else ()
        )
        stmts: int = 0
        start: float = time.perf_counter()
        for field_id_, tags in metrics:
            cur.execute(
                f"UPDATE {metric_table} SET tag_list = %s, last_modify_time = %s WHERE field_id = %s",
                (tags, NEXT_DAY, field_id_),
            )
            stmts += 1
        for i in range(0, len(members), 1000):
            batch: tuple[Any, ...] = members[i : i + 1000]
            cur.execute(
                f"INSERT INTO {member_table} (group_id, {member_cols}, last_seen) VALUES "
                + ", ".join(["(%s, %s, %s, %s)"] * len(batch))
                + " ON DUPLICATE KEY UPDATE last_seen = VALUES(last_seen)",
                [v for sid, fid in batch for v in (g, sid, fid, NEXT_DAY)],
            )
            stmts += 1
        for (sid,) in sources:
            cur.execute("UPDATE d_source SET last_seen = %s WHERE source_id = %s", (NEXT_DAY, sid))
            stmts += 1
        scopes: int = 0
        if scheme == "e":
            cur.execute("UPDATE e_scope SET last_seen = %s WHERE group_id = %s", (NEXT_DAY, g))
            scopes = cur.rowcount
            stmts += 1
        elapsed: float = (time.perf_counter() - start) * 1000
    return elapsed, stmts, len(metrics) + len(members) + len(sources) + scopes


def churn(conn: pymysql.Connection, scheme: str, app: App) -> tuple[float, int, int]:
    """替换 10% 服务：新服务上报原服务的全部指标，旧来源由 last_seen 被动过期，C 必须改写列表。"""
    g: int = app.group_id
    replaced: list[int] = list(range(max(1, len(app.services) // 10)))
    metrics_of: dict[int, list[int]] = {j: [] for j in replaced}
    for metric_idx, service_idx in app.members:
        if service_idx in metrics_of:
            metrics_of[service_idx].append(metric_idx)
    new_names: dict[int, str] = {j: f"{app.services[j]}-v2" for j in replaced}
    stmts: int = 0
    rows: int = 0
    with conn.cursor() as cur:
        if scheme == "a":
            next_id: int = fetch(cur, "SELECT MAX(field_id) FROM a_metric", ())[0][0]
            batch: list[list[Any]] = []
            for j in replaced:
                for metric_idx in metrics_of[j]:
                    next_id += 1
                    scope_name, name = app.metrics[metric_idx]
                    batch.append(
                        [
                            *metric_row(app, next_id, metric_idx, f"{scope_name}||{new_names[j]}", NEXT_DAY),
                            meta_json(name, "s"),
                        ]
                    )
            start: float = time.perf_counter()
            for i in range(0, len(batch), 200):
                chunk: list[list[Any]] = batch[i : i + 200]
                cur.execute(
                    f"INSERT INTO a_metric ({', '.join(METRIC_LOAD_COLUMNS)}, meta) VALUES "
                    + ", ".join(["(" + ", ".join(["%s"] * 14) + ")"] * len(chunk)),
                    [v for r in chunk for v in r],
                )
                stmts += 1
            return (time.perf_counter() - start) * 1000, stmts, len(batch)

        if scheme == "e":
            next_scope: int = fetch(cur, "SELECT MAX(scope_id) FROM e_scope", ())[0][0]
            meta_ids: dict[str, int] = {
                name: mid
                for mid, name in fetch(cur, "SELECT meta_id, field_name FROM e_meta WHERE group_id = %s", (g,))
            }
            start = time.perf_counter()
            for j in replaced:
                by_scope: dict[str, list[int]] = {}
                for metric_idx in metrics_of[j]:
                    by_scope.setdefault(app.metrics[metric_idx][0], []).append(metric_idx)
                for scope_name, metric_idxs in sorted(by_scope.items()):
                    next_scope += 1
                    scope_labels: dict[str, str] = report_scope_labels(new_names[j], scope_name)
                    scope_key: str = source_key(scope_labels)
                    cur.execute(
                        "INSERT INTO e_scope (scope_id, group_id, scope_type, scope_hash, raw_scope, labels, last_seen) "
                        "VALUES (%s, %s, 'APM', UNHEX(%s), %s, %s, %s)",
                        (
                            next_scope,
                            g,
                            md5_hex(scope_key),
                            apm_raw_scope(new_names[j], scope_name),
                            json.dumps(scope_labels),
                            NEXT_DAY,
                        ),
                    )
                    cur.execute(
                        "INSERT INTO e_label (group_id, label_key, label_value, scope_id) VALUES "
                        + ", ".join(["(%s, %s, %s, %s)"] * len(scope_labels)),
                        [v for k, val in sorted(scope_labels.items()) for v in (g, k, val, next_scope)],
                    )
                    cur.execute(
                        "INSERT INTO e_member (group_id, scope_id, meta_id, last_seen) VALUES "
                        + ", ".join(["(%s, %s, %s, %s)"] * len(metric_idxs)),
                        [v for m in metric_idxs for v in (g, next_scope, meta_ids[app.metrics[m][1]], NEXT_DAY)],
                    )
                    stmts += 3
                    rows += 1 + len(scope_labels) + len(metric_idxs)
            return (time.perf_counter() - start) * 1000, stmts, rows

        source_table: str = "d_source" if scheme == "d" else "b_source"
        metric_table: str = "c_metric" if scheme == "c" else "b_metric"
        next_sid: int = fetch(cur, f"SELECT MAX(source_id) FROM {source_table}", ())[0][0]
        index_of: dict[str, int] = {name: i for i, (_, name) in enumerate(app.metrics)}
        field_ids: dict[int, int] = {
            index_of[name]: fid
            for fid, name in fetch(cur, f"SELECT field_id, field_name FROM {metric_table} WHERE group_id = %s", (g,))
        }
        old_sids: dict[int, int] = {
            j: fetch(
                cur,
                f"SELECT source_id FROM {source_table} WHERE group_id = %s AND source_hash = UNHEX(%s)",
                (g, md5_hex(source_key({"service_name": app.services[j]}))),
            )[0][0]
            for j in replaced
        }
        lists: dict[int, list[int]] = {}
        if scheme == "c":
            lists = {
                fid: json.loads(ids)
                for fid, ids in fetch(cur, "SELECT field_id, source_ids FROM c_metric WHERE group_id = %s", (g,))
            }
        start = time.perf_counter()
        new_sids: dict[int, int] = {}
        for j in replaced:
            next_sid += 1
            new_sids[j] = next_sid
            labels: dict[str, str] = {"service_name": new_names[j]}
            key: str = source_key(labels)
            fids: list[int] = [field_ids[m] for m in metrics_of[j]]
            head: list[Any] = [next_sid, g, md5_hex(key), key, json.dumps(labels), NEXT_DAY]
            if scheme == "d":
                cur.execute(
                    "INSERT INTO d_source (source_id, group_id, source_hash, source_key, labels, last_seen, field_ids) "
                    "VALUES (%s, %s, UNHEX(%s), %s, %s, %s, %s)",
                    [*head, json.dumps(fids)],
                )
                stmts += 1
                rows += 1
                continue
            cur.execute(
                "INSERT INTO b_source (source_id, group_id, source_hash, source_key, labels, last_seen) "
                "VALUES (%s, %s, UNHEX(%s), %s, %s, %s)",
                head,
            )
            stmts += 1
            rows += 1
            if scheme == "b":
                cur.execute(
                    "INSERT INTO b_member (group_id, source_id, field_id, last_seen) VALUES "
                    + ", ".join(["(%s, %s, %s, %s)"] * len(fids)),
                    [v for fid in fids for v in (g, next_sid, fid, NEXT_DAY)],
                )
                stmts += 1
                rows += len(fids)
        if scheme == "c":
            touched: set[int] = set()
            for j in replaced:
                for m in metrics_of[j]:
                    fid: int = field_ids[m]
                    lists[fid] = [s for s in lists[fid] if s != old_sids[j]] + [new_sids[j]]
                    touched.add(fid)
            for fid in sorted(touched):
                cur.execute("UPDATE c_metric SET source_ids = %s WHERE field_id = %s", (json.dumps(lists[fid]), fid))
                stmts += 1
                rows += 1
        return (time.perf_counter() - start) * 1000, stmts, rows


# ---------------------------------------------------------------- 分表


def report_shard(
    scale: str,
    out: list[str],
    base: str = "e_member",
    builder: Callable[[Sequence[Sample], str], dict[str, Case]] = cases_e,
) -> None:
    conn: pymysql.Connection = connect()
    shards: list[str] = [f"{base}_{k:02d}" for k in range(SHARD_COUNT)]
    for k, table in enumerate(shards):
        execute(conn, f"DROP TABLE IF EXISTS {table}")
        execute(conn, f"CREATE TABLE {table} LIKE {base}")
        execute(conn, f"INSERT INTO {table} SELECT * FROM {base} WHERE group_id % {SHARD_COUNT} = {k}")
        execute(conn, f"ANALYZE TABLE {table}")
    samples: list[Sample] = build_samples(conn, scale, with_ids=True)
    by_shard: dict[int, list[Sample]] = {}
    for s in samples:
        by_shard.setdefault(s.group_id % SHARD_COUNT, []).append(s)
    single: dict[str, Case] = builder(samples, base)
    sharded: dict[str, list[Run]] = {}
    for k, shard_samples in by_shard.items():
        for name, case in builder(shard_samples, shards[k]).items():
            sharded.setdefault(name, []).extend(case.runs)
    out.append(f"## single {base} vs {SHARD_COUNT} tables by group_id % {SHARD_COUNT}")
    out.append(TIMING_HEADER)
    raw: pymysql.Connection = connect(raw=True)
    for name in ("service_page_50", "metric_sources", "discovery_read"):
        out.append(run_case(f"single.{name}", raw, single[name].runs).line())
        out.append(run_case(f"shard.{name}", raw, sharded[name]).line())
    raw.close()
    out.append("")
    shard_rows: dict[str, int] = {t: execute(conn, f"SELECT COUNT(*) FROM {t}")[0][0] for t in shards}
    counts: list[int] = sorted(shard_rows.values())
    out.append(
        f"## shard rows: min {counts[0]:,}, median {int(statistics.median(counts)):,}, max {counts[-1]:,} "
        "(profiles cycle by group_id, so group_id % 16 concentrates large apps in 4 shards)"
    )
    largest: str = max(shard_rows, key=lambda t: shard_rows[t])
    out.append("")
    out.append("## online DDL: ADD INDEX (last_seen), ALGORITHM=INPLACE, LOCK=NONE")
    for table in (base, largest):
        rows: int = execute(conn, f"SELECT COUNT(*) FROM {table}")[0][0]
        start: float = time.perf_counter()
        execute(conn, f"ALTER TABLE {table} ADD INDEX idx_last_seen (last_seen), ALGORITHM=INPLACE, LOCK=NONE")
        elapsed: float = time.perf_counter() - start
        execute(conn, f"ALTER TABLE {table} DROP INDEX idx_last_seen")
        out.append(f"{table:<14}{rows:>14,} rows{elapsed:>10.2f} s")
    out.append("")
    for table in shards:
        execute(conn, f"DROP TABLE IF EXISTS {table}")
    conn.close()


@dataclass(frozen=True)
class Layout:
    table: str
    ddl: str
    columns: str
    order: str


LAYOUTS: dict[str, Layout] = {
    "e_member": Layout(
        "e_member_dj",
        """CREATE TABLE e_member_dj (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        scope_id INT NOT NULL,
        meta_id INT NOT NULL,
        last_seen DATETIME NOT NULL,
        meta JSON NULL,
        field_config JSON NULL,
        UNIQUE KEY uk_member (group_id, scope_id, meta_id),
        KEY idx_meta (group_id, meta_id)
    )""",
        "group_id, scope_id, meta_id, last_seen, meta, field_config",
        "group_id, scope_id, meta_id",
    ),
    "e_label": Layout(
        "e_label_dj",
        """CREATE TABLE e_label_dj (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        label_key VARCHAR(64) NOT NULL,
        label_value VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        scope_id INT NOT NULL,
        UNIQUE KEY uk_label (group_id, label_key, label_value, scope_id)
    )""",
        "group_id, label_key, label_value, scope_id",
        "group_id, label_key, label_value, scope_id",
    ),
}


def report_layout(scale: str, out: list[str]) -> None:
    """Django 4.2 不支持复合主键，成员表与标签表改为自增 id 主键加唯一键，比较体积与读取延迟；复用 scale 套件留下的表。"""
    conn: pymysql.Connection = connect()
    for base, layout in LAYOUTS.items():
        execute(conn, f"DROP TABLE IF EXISTS {layout.table}")
        execute(conn, layout.ddl)
        execute(
            conn,
            f"INSERT INTO {layout.table} ({layout.columns}) SELECT {layout.columns} FROM {base} ORDER BY {layout.order}",
        )
        execute(conn, f"ANALYZE TABLE {layout.table}")
    tables: list[str] = [t for base, layout in LAYOUTS.items() for t in (base, layout.table)]
    sizes: dict[str, dict[str, float]] = table_sizes(conn, tables)
    out.append("## Django layout: AUTO_INCREMENT id + UNIQUE KEY vs composite PRIMARY KEY")
    out.append(f"{'table':<14}{'rows':>14}{'data MiB':>11}{'index MiB':>11}{'ibd MiB':>11}{'ibd B/row':>11}")
    for table in tables:
        s: dict[str, float] = sizes[table]
        out.append(
            f"{table:<14}{int(s['rows']):>14,}{mib(s['data']):>11}{mib(s['index']):>11}{mib(s['file']):>11}"
            f"{s['file'] / s['rows'] if s['rows'] else 0:>11,.0f}"
        )
    out.append("")
    samples: list[Sample] = build_samples(conn, scale, with_ids=True)
    composite: dict[str, Case] = cases_e(samples)
    django: dict[str, Case] = cases_e(samples, "e_member_dj", "e_label_dj")
    out.append(TIMING_HEADER)
    raw: pymysql.Connection = connect(raw=True)
    plans: list[str] = []
    for name in ("service_page_50", "service_all", "metric_sources"):
        out.append(run_case(f"composite.{name}", raw, composite[name].runs, seed=name).line())
        out.append(run_case(f"django.{name}", raw, django[name].runs, seed=name).line())
        plans.append(f"django.{name}: {explain(conn, django[name].sql, django[name].params)}")
    raw.close()
    out.append("")
    out.append("## EXPLAIN (table:key/type)")
    out.extend(plans)
    out.append("")
    for layout in LAYOUTS.values():
        execute(conn, f"DROP TABLE IF EXISTS {layout.table}")
    conn.close()


# ---------------------------------------------------------------- 来源标签表示


SCOPE_DDL: dict[str, str] = {
    "k1_string": """CREATE TABLE k1_string (
        source_id INT NOT NULL PRIMARY KEY, group_id INT NOT NULL,
        source_key VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        UNIQUE KEY uk (group_id, source_key))""",
    "k2_hash": """CREATE TABLE k2_hash (
        source_id INT NOT NULL PRIMARY KEY, group_id INT NOT NULL, source_hash BINARY(16) NOT NULL,
        source_key VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
        UNIQUE KEY uk (group_id, source_hash))""",
    "k3_label": """CREATE TABLE k3_label (
        group_id INT NOT NULL, label_key VARCHAR(64) NOT NULL, label_value VARCHAR(255) NOT NULL, source_id INT NOT NULL,
        PRIMARY KEY (group_id, label_key, label_value, source_id))""",
    "k4_json": """CREATE TABLE k4_json (
        source_id INT NOT NULL PRIMARY KEY, group_id INT NOT NULL, source_hash BINARY(16) NOT NULL,
        source_key VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, labels_kv JSON NOT NULL,
        UNIQUE KEY uk (group_id, source_hash),
        KEY idx_kv (group_id, (CAST(labels_kv->'$' AS CHAR(300) ARRAY))))""",
    "k5_column": """CREATE TABLE k5_column (
        source_id INT NOT NULL PRIMARY KEY, group_id INT NOT NULL, source_hash BINARY(16) NOT NULL,
        source_key VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, labels JSON NOT NULL,
        service_name VARCHAR(255) AS (labels->>'$.service_name') STORED,
        scope_name VARCHAR(255) AS (labels->>'$.scope_name') STORED,
        UNIQUE KEY uk (group_id, source_hash), KEY idx_service (group_id, service_name, scope_name))""",
}
SCOPE_NAMES: dict[str, str] = {
    "k1": "K1 规范串唯一键",
    "k2": "K2 哈希唯一键",
    "k3": "K3 哈希 + 标签倒排",
    "k4": "K4 哈希 + JSON 多值索引",
    "k5": "K5 哈希 + 固定生成列",
}


def scope_sources(large_services: int) -> Iterable[tuple[int, int, dict[str, str]]]:
    """完整 __scope 含 app_name、scope_name、service_name，每个服务两个 scope_name。"""
    source_id: int = 0
    for g in range(1, APP_COUNT + 1):
        profile: Profile = profile_of(g)
        services: int = large_services if profile.name == "L" else profile.services
        for j in range(services):
            for scope_name in ("default", "custom"):
                source_id += 1
                yield (
                    source_id,
                    g,
                    {
                        "app_name": f"app{g:04d}-microservices-production",
                        "scope_name": scope_name,
                        "service_name": f"app{g:04d}-activities-svc-{j:03d}",
                    },
                )


def report_scope(large_services: int, out: list[str]) -> None:
    conn: pymysql.Connection = connect()
    for table, ddl in SCOPE_DDL.items():
        execute(conn, f"DROP TABLE IF EXISTS {table}")
        execute(conn, ddl)
    hashed: str = "SET source_hash = UNHEX(@h)"
    loaders: dict[str, Loader] = {
        "k1_string": Loader(conn, "k1_string", ["source_id", "group_id", "source_key"]),
        "k2_hash": Loader(conn, "k2_hash", ["source_id", "group_id", "@h", "source_key"], hashed),
        "k3_label": Loader(conn, "k3_label", ["group_id", "label_key", "label_value", "source_id"]),
        "k4_json": Loader(conn, "k4_json", ["source_id", "group_id", "@h", "source_key", "labels_kv"], hashed),
        "k5_column": Loader(conn, "k5_column", ["source_id", "group_id", "@h", "source_key", "labels"], hashed),
    }
    for source_id, g, labels in scope_sources(large_services):
        key: str = source_key(labels)
        digest: str = md5_hex(key)
        loaders["k1_string"].add([source_id, g, key])
        loaders["k2_hash"].add([source_id, g, digest, key])
        for k, v in labels.items():
            loaders["k3_label"].add([g, k, v, source_id])
        loaders["k4_json"].add([source_id, g, digest, key, json.dumps([f"{k}={v}" for k, v in sorted(labels.items())])])
        loaders["k5_column"].add([source_id, g, digest, key, json.dumps(labels)])
    for table, loader in loaders.items():
        loader.flush()
        execute(conn, f"ANALYZE TABLE {table}")

    sizes: dict[str, dict[str, float]] = table_sizes(conn, SCOPE_DDL)
    total: int = int(sizes["k1_string"]["rows"])
    out.append(f"## __scope sources = {total:,} (large group services = {large_services}, 2 scope_name each)")
    out.append(f"{'representation':<28}{'rows':>14}{'ibd MiB':>11}{'B/source':>10}")
    storage: dict[str, tuple[int, float]] = {
        "k1": (int(sizes["k1_string"]["rows"]), sizes["k1_string"]["file"]),
        "k2": (int(sizes["k2_hash"]["rows"]), sizes["k2_hash"]["file"]),
        "k3": (int(sizes["k3_label"]["rows"]), sizes["k2_hash"]["file"] + sizes["k3_label"]["file"]),
        "k4": (int(sizes["k4_json"]["rows"]), sizes["k4_json"]["file"]),
        "k5": (int(sizes["k5_column"]["rows"]), sizes["k5_column"]["file"]),
    }
    for name, (rows, file_bytes) in storage.items():
        out.append(f"{SCOPE_NAMES[name]:<28}{rows:>14,}{mib(file_bytes):>11}{file_bytes / total:>10,.0f}")
    out.append("")

    rng: random.Random = random.Random(11)
    picks: list[tuple[int, str, str]] = []
    for g in large_group_ids():
        for _ in range(SAMPLES_PER_GROUP):
            service: str = f"app{g:04d}-activities-svc-{rng.randrange(large_services):03d}"
            labels = {
                "app_name": f"app{g:04d}-microservices-production",
                "scope_name": "custom",
                "service_name": service,
            }
            picks.append((g, service, source_key(labels)))

    def case(sql: str, params_of: Callable[[int, str, str], tuple[Any, ...]]) -> Case:
        return Case([lambda cur, p=p: len(fetch(cur, sql, params_of(*p))) for p in picks], sql, params_of(*picks[0]))

    lookups: dict[str, Case] = {
        "exact.k1": case(
            "SELECT source_id FROM k1_string WHERE group_id = %s AND source_key = %s", lambda g, s, k: (g, k)
        ),
        "exact.k2": case(
            "SELECT source_id FROM k2_hash WHERE group_id = %s AND source_hash = UNHEX(%s)",
            lambda g, s, k: (g, md5_hex(k)),
        ),
        "service_name.k1": case(
            "SELECT source_id FROM k1_string WHERE group_id = %s AND source_key LIKE %s",
            lambda g, s, k: (g, f"%service_name:{s}"),
        ),
        "service_name.k3": case(
            "SELECT source_id FROM k3_label WHERE group_id = %s AND label_key = 'service_name' AND label_value = %s",
            lambda g, s, k: (g, s),
        ),
        "service_name.k4": case(
            "SELECT source_id FROM k4_json WHERE group_id = %s AND %s MEMBER OF (labels_kv->'$')",
            lambda g, s, k: (g, f"service_name={s}"),
        ),
        "service_name.k5": case(
            "SELECT source_id FROM k5_column WHERE group_id = %s AND service_name = %s", lambda g, s, k: (g, s)
        ),
        "distinct.k1": case(
            "SELECT DISTINCT SUBSTRING_INDEX(source_key, 'service_name:', -1) FROM k1_string WHERE group_id = %s",
            lambda g, s, k: (g,),
        ),
        "distinct.k3": case(
            "SELECT DISTINCT label_value FROM k3_label WHERE group_id = %s AND label_key = 'service_name'",
            lambda g, s, k: (g,),
        ),
        "distinct.k4": case(
            "SELECT DISTINCT JSON_UNQUOTE(JSON_EXTRACT(labels_kv, '$[2]')) FROM k4_json WHERE group_id = %s",
            lambda g, s, k: (g,),
        ),
        "distinct.k5": case("SELECT DISTINCT service_name FROM k5_column WHERE group_id = %s", lambda g, s, k: (g,)),
    }
    out.append("## lookups on large groups")
    out.append(TIMING_HEADER)
    plans: list[str] = []
    raw: pymysql.Connection = connect(raw=True)
    for name, c in lookups.items():
        kind, rep = name.split(".")
        out.append(run_case(f"{kind}.{SCOPE_NAMES[rep]}", raw, c.runs).line())
        plans.append(f"{name}: {explain(conn, c.sql, c.params)}")
    raw.close()
    out.append("")
    out.append("## EXPLAIN (table:key/type)")
    out.extend(plans)
    out.append("")
    for table in SCOPE_DDL:
        execute(conn, f"DROP TABLE IF EXISTS {table}")
    conn.close()


# ---------------------------------------------------------------- 入口


def environment(out: list[str]) -> None:
    conn: pymysql.Connection = connect()
    version: str = execute(conn, "SELECT VERSION()")[0][0]
    variables: dict[str, str] = dict(
        execute(
            conn,
            "SHOW VARIABLES WHERE Variable_name IN ('innodb_buffer_pool_size', 'innodb_redo_log_capacity', "
            "'innodb_flush_log_at_trx_commit', 'log_bin', 'innodb_page_size', 'innodb_flush_method')",
        )
    )
    out.append(f"python {platform.python_version()}, pymysql {importlib.metadata.version('pymysql')}, mysql {version}")
    out.append(f"{platform.system()}/{platform.machine()}, {os.cpu_count()} logical cpu")
    out.extend(f"{k}={v}" for k, v in sorted(variables.items()))
    out.append("")
    conn.close()


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=["env", "matrix", "scale", "layout", "scope"])
    parser.add_argument("--scale", default="s1", choices=["s1", "s2"])
    parser.add_argument("--large-services", type=int, default=LARGE_REGISTERED_SERVICES)
    args: argparse.Namespace = parser.parse_args()
    out: list[str] = []
    if args.suite not in ("env", "layout"):
        reset()
    if args.suite == "env":
        environment(out)
    elif args.suite == "matrix":
        schemes: list[str] = ["a", "b", "c", "d", "e"]
        start: float = time.perf_counter()
        counts: dict[str, int] = load(args.scale, schemes)
        out.append(f"# scale={args.scale}, apps={APP_COUNT}, load {time.perf_counter() - start:.0f} s")
        out.append(", ".join(f"{k}={v:,}" for k, v in counts.items()))
        out.append("")
        report_storage(schemes, out)
        report_queries(args.scale, schemes, out)
        report_writes(args.scale, schemes, out)
    elif args.suite == "scale":
        schemes = ["a", "b", "e"]
        start = time.perf_counter()
        counts = load(args.scale, ["b", "e"])
        counts.update(load(args.scale, ["a"], only_groups=set(large_group_ids())))
        out.append(
            f"# scale={args.scale}, apps={APP_COUNT}, load {time.perf_counter() - start:.0f} s, "
            f"a_metric only for {SAMPLE_GROUPS} sampled large groups"
        )
        out.append(", ".join(f"{k}={v:,}" for k, v in counts.items()))
        out.append("")
        report_storage(schemes, out)
        report_queries(args.scale, schemes, out)
        report_writes(args.scale, schemes, out)
        report_shard(args.scale, out)
    elif args.suite == "layout":
        report_layout(args.scale, out)
    else:
        report_scope(args.large_services, out)
    print("\n".join(out), flush=True)


if __name__ == "__main__":
    main()
