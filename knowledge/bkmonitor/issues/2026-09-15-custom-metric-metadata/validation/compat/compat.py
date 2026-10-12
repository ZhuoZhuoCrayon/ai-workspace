#!/usr/bin/env python3
"""MySQL 5.7 / 8.0 兼容性与执行计划验证。

由 compat.sh 在 Docker 容器中启动对应版本后调用，依次执行：
  env       版本与关键变量
  ddl       候选表结构在项目字符集（库默认 utf8，列 utf8_bin / utf8mb4_bin / ascii_bin）下能否创建
  online    1,000,000 行指标表上的 X1 在线 DDL，期间并发 UPDATE / SELECT 并采样元数据锁
  plans     2,000 分组、200,000 指标、2,000,000 成员上的 EXPLAIN、删除与批量 upsert
  features  5.7 不支持、方案可能误用的特性
另有 diff 子命令，对比两个版本输出的 JSON。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import random
import statistics
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import pymysql
from pymysql.constants import CLIENT
from pymysql.cursors import DictCursor

DB: str = "cm_compat"
DDL_DB: str = "cm_ddl"
BASE_TIME: str = "2026-10-11 00:00:00"
EXPIRE_BEFORE: str = "2026-09-11 00:00:00"
EXPIRED_AT: str = "2026-08-31 00:00:00"
LOAD_CHUNK_ROWS: int = 200_000

ONLINE_GROUPS: int = 5_000
ONLINE_METRICS_PER_GROUP: int = 200
BASELINE_SECONDS: float = 3.0
WORKLOAD_INTERVAL: float = 0.02

XL_GROUP: int = 1
SAMPLE_GROUP: int = 1001
PLAN_GROUPS: int = 2_000
REGULAR_METRICS: int = 90
XL_METRICS: int = 20_000
REGULAR_TS_SCOPES: int = 5
XL_TS_SCOPES: int = 50
REGULAR_REPORT_SCOPES: int = 10
XL_REPORT_SCOPES: int = 200
XL_SCOPES_PER_METRIC: int = 10
UPSERT_BATCH: int = 1_000
ROW_IN_TUPLES: int = 1_000

STEMS: tuple[str, ...] = (
    "rpc_server_handled",
    "rpc_client_handled",
    "http_server_request",
    "db_client_query",
    "cache_hit",
    "mq_consume",
    "process_cpu",
    "go_memstats_heap",
)
TAG_NAMES: tuple[str, ...] = (
    "app_name",
    "bk_biz_id",
    "bk_target_ip",
    "bk_target_cloud_id",
    "callee_method",
    "callee_server",
    "callee_service",
    "caller_server",
    "caller_service",
    "code",
    "code_type",
    "env",
    "instance",
    "namespace",
    "pod",
    "scope_name",
    "service_name",
    "target",
    "container_name",
)

# 与 Django 4.2 对 metadata 模型生成的 DDL 同形：未写字符集的列继承库默认 utf8，db_collation 生成 COLLATE 子句
BASE_METRIC_DDL: str = """CREATE TABLE `metadata_timeseriesmetric` (
  `field_id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `table_id` varchar(255) NOT NULL,
  `field_name` varchar(255) COLLATE utf8_bin NOT NULL,
  `tag_list` longtext NOT NULL,
  `last_modify_time` datetime(6) NOT NULL,
  `label` varchar(255) NOT NULL,
  `last_index` integer NOT NULL,
  `create_time` datetime(6) NULL,
  `field_config` json NOT NULL,
  `field_scope` varchar(255) COLLATE utf8_bin NOT NULL DEFAULT 'default',
  `scope_id` integer NULL,
  `is_active` bool NOT NULL,
  UNIQUE KEY `uniq_group_scope_field` (`group_id`, `field_scope`, `field_name`),
  KEY `idx_group` (`group_id`),
  KEY `idx_scope` (`scope_id`),
  KEY `idx_label` (`label`),
  KEY `idx_active` (`is_active`),
  KEY `idx_group_scope_field` (`group_id`, `scope_id`, `field_name`)
)"""
SCOPE_DDL: str = """CREATE TABLE `metadata_timeseriesscope` (
  `id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `scope_name` varchar(255) COLLATE utf8_bin NOT NULL,
  `dimension_config` json NOT NULL,
  `auto_rules` json NOT NULL,
  `create_from` varchar(10) NOT NULL DEFAULT 'data',
  `last_modify_time` datetime(6) NOT NULL,
  UNIQUE KEY `uniq_group_scope_name` (`group_id`, `scope_name`),
  KEY `idx_group` (`group_id`),
  KEY `idx_create_from` (`create_from`)
)"""
X1_COLUMNS: str = (
    "ADD COLUMN `original_name` varchar(255) COLLATE utf8_bin NULL, "
    "ADD COLUMN `metric_type` varchar(16) NULL, "
    "ADD COLUMN `meta` json NULL, "
    "ADD COLUMN `meta_fingerprint` char(32) NULL, "
    "ADD COLUMN `meta_seen_at` datetime(6) NULL"
)
X1_DROP_COLUMNS: str = (
    "DROP COLUMN `original_name`, DROP COLUMN `metric_type`, DROP COLUMN `meta`, "
    "DROP COLUMN `meta_fingerprint`, DROP COLUMN `meta_seen_at`"
)
X1_INDEX: str = "ADD INDEX `idx_group_original` (`group_id`, `original_name`)"
X2_DDL: str = """CREATE TABLE `metric_meta_x2` (
  `field_id` integer NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `original_name` varchar(255) COLLATE utf8_bin NOT NULL,
  `metric_type` varchar(16) NOT NULL,
  `meta` json NOT NULL,
  `fingerprint` char(32) NOT NULL,
  `seen_at` datetime(6) NOT NULL,
  KEY `idx_group_original` (`group_id`, `original_name`)
)"""
X3_DDL: str = """CREATE TABLE `metric_meta_x3` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `field_name` varchar(255) COLLATE utf8_bin NOT NULL,
  `original_name` varchar(255) COLLATE utf8_bin NOT NULL,
  `metric_type` varchar(16) NOT NULL,
  `meta` json NOT NULL,
  `fingerprint` char(32) NOT NULL,
  `seen_at` datetime(6) NOT NULL,
  UNIQUE KEY `uniq_group_field` (`group_id`, `field_name`),
  KEY `idx_group_original` (`group_id`, `original_name`)
)"""
REPORT_SCOPE_DDL: str = """CREATE TABLE `report_scope` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `scope_type` varchar(16) NOT NULL,
  `scope_hash` char(32) COLLATE ascii_bin NOT NULL,
  `raw_scope` varchar(512) COLLATE utf8mb4_bin NOT NULL,
  `labels` json NOT NULL,
  `last_seen` datetime(6) NOT NULL,
  UNIQUE KEY `uniq_group_hash` (`group_id`, `scope_hash`)
)"""
LABEL_DDL: str = """CREATE TABLE `report_scope_label` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `label_key` varchar(64) NOT NULL,
  `label_value` varchar(255) COLLATE utf8mb4_bin NOT NULL,
  `report_scope_id` bigint NOT NULL,
  UNIQUE KEY `uniq_group_key_value_scope` (`group_id`, `label_key`, `label_value`, `report_scope_id`)
)"""
MEMBER_DDL: str = """CREATE TABLE `report_member` (
  `id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  `group_id` integer NOT NULL,
  `report_scope_id` bigint NOT NULL,
  `ref_id` bigint NOT NULL,
  `last_seen` datetime(6) NOT NULL,
  `meta` json NULL,
  `field_config` json NULL,
  UNIQUE KEY `uniq_group_scope_ref` (`group_id`, `report_scope_id`, `ref_id`),
  KEY `idx_group_ref` (`group_id`, `ref_id`)
)"""

VARIABLES: tuple[str, ...] = (
    "version",
    "version_comment",
    "character_set_server",
    "collation_server",
    "innodb_file_per_table",
    "innodb_default_row_format",
    "innodb_large_prefix",
    "innodb_file_format",
    "innodb_page_size",
    "innodb_strict_mode",
    "sql_mode",
    "transaction_isolation",
    "tx_isolation",
    "innodb_autoinc_lock_mode",
    "innodb_buffer_pool_size",
    "innodb_online_alter_log_max_size",
    "lock_wait_timeout",
    "innodb_lock_wait_timeout",
    "range_optimizer_max_mem_size",
    "eq_range_index_dive_limit",
    "log_bin",
    "local_infile",
    "performance_schema",
    "innodb_log_file_size",
    "innodb_redo_log_capacity",
    "default_authentication_plugin",
)
OPTIMIZER_FLAGS: tuple[str, ...] = (
    "index_merge",
    "mrr",
    "batched_key_access",
    "block_nested_loop",
    "derived_merge",
    "skip_scan",
    "hash_join",
    "subquery_to_derived",
)

RESULT: dict[str, Any] = {}


def out(text: str = "") -> None:
    print(text, flush=True)


@dataclass(frozen=True)
class Server:
    host: str
    port: int

    def connect(self, database: str | None = DB, autocommit: bool = True) -> pymysql.Connection:
        """与 Django 一致：utf8mb4 连接、FOUND_ROWS 客户端标志。"""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user="root",
            password="",
            database=database,
            charset="utf8mb4",
            autocommit=autocommit,
            local_infile=True,
            client_flag=CLIENT.FOUND_ROWS,
        )


def run(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None = None) -> tuple[Any, ...]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def run_dict(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    with conn.cursor(DictCursor) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


@dataclass
class Outcome:
    ok: bool
    elapsed_ms: float
    code: int = 0
    message: str = ""
    warnings: list[tuple[str, int, str]] = field(default_factory=list)
    affected: int = 0
    rows: tuple[Any, ...] = ()

    def brief(self, with_time: bool = True) -> str:
        if not self.ok:
            return f"ERROR {self.code}: {self.message}"
        text: str = f"OK ({self.elapsed_ms:.1f} ms)" if with_time else "OK"
        notes: list[str] = [f"{level} {code}: {msg}" for level, code, msg in self.warnings if code != 1003]
        return text + (" ｜ " + " ｜ ".join(notes) if notes else "")

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "code": self.code,
            "message": self.message,
            "warnings": [list(w) for w in self.warnings],
            "affected": self.affected,
        }


def attempt(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None = None) -> Outcome:
    start: float = time.perf_counter()
    try:
        with conn.cursor() as cur:
            affected: int = cur.execute(sql, params)
            rows: tuple[Any, ...] = cur.fetchall()
            elapsed: float = (time.perf_counter() - start) * 1000
            cur.execute("SHOW WARNINGS")
            warnings: list[tuple[str, int, str]] = [(str(w[0]), int(w[1]), str(w[2])) for w in cur.fetchall()]
        return Outcome(True, elapsed, warnings=warnings, affected=affected, rows=rows)
    except pymysql.MySQLError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        code: int = int(exc.args[0]) if exc.args and isinstance(exc.args[0], int) else 0
        message: str = str(exc.args[1]) if len(exc.args) > 1 else str(exc)
        return Outcome(False, elapsed, code=code, message=message)


def pct(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered: list[float] = sorted(values)
    index: int = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def server_version(conn: pymysql.Connection) -> tuple[int, int, int]:
    raw: str = str(run(conn, "SELECT VERSION()")[0][0]).split("-")[0]
    parts: list[int] = [int(p) for p in raw.split(".")[:3]]
    return parts[0], parts[1], parts[2]


def is_v8(conn: pymysql.Connection) -> bool:
    return server_version(conn) >= (8, 0, 0)


class Loader:
    """把行写入临时 TSV，按块执行 LOAD DATA LOCAL INFILE。"""

    def __init__(self, conn: pymysql.Connection, table: str, columns: Sequence[str]) -> None:
        self.conn: pymysql.Connection = conn
        self.table: str = table
        self.columns: Sequence[str] = columns
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
            run(
                self.conn,
                f"LOAD DATA LOCAL INFILE %s INTO TABLE {self.table} CHARACTER SET utf8mb4 "
                f"FIELDS TERMINATED BY '\\t' LINES TERMINATED BY '\\n' ({', '.join(self.columns)})",
                (path,),
            )
        finally:
            os.unlink(path)
        self.total += len(self.rows)
        self.rows = []


def metric_identity(i: int) -> tuple[str, str | None, str]:
    """返回 (field_name, original_name, metric_type)。

    每 10 个一块：0-2 为同一直方图族（bucket/sum/count），3-6 为带元信息的普通指标，7-9 没有元信息。
    """
    block: int = i // 10
    slot: int = i % 10
    stem: str = f"{STEMS[block % len(STEMS)]}_{block:05d}"
    if slot < 3:
        suffix: str = ("bucket", "sum", "count")[slot]
        return f"{stem}_seconds_{suffix}", f"{stem.replace('_', '.')}.seconds", "histogram"
    name: str = f"{stem}_m{slot}_total"
    if slot < 7:
        return name, name.replace("_", "."), "counter"
    return name, None, "counter"


def tag_list_json(i: int) -> str:
    count: int = 15 + i % 5
    return json.dumps(list(TAG_NAMES[:count]))


def meta_json(original_name: str, metric_type: str) -> str:
    return json.dumps(
        {
            "original_name": original_name,
            "metric_type": metric_type,
            "unit": "s" if metric_type == "histogram" else "",
            "description": f"{original_name} description",
            "temporality": "cumulative",
            "interval": None,
            "usage": "sum",
        },
        sort_keys=True,
    )


def apm_raw_scope(service: str, scope_name: str) -> str:
    def escape(part: str) -> str:
        return part.replace("%", "%25").replace("-", "%2D")

    return f"{escape(service)}-{escape(scope_name)}"


def canonical(labels: dict[str, str]) -> str:
    return "||".join(f"{k}:{labels[k]}" for k in sorted(labels))


def innodb_table_info(conn: pymysql.Connection, table: str) -> dict[str, Any]:
    name: str = f"{DB}/{table}"
    try:
        rows: list[dict[str, Any]] = run_dict(
            conn, "SELECT * FROM information_schema.INNODB_TABLES WHERE NAME = %s", (name,)
        )
    except pymysql.MySQLError:
        rows = run_dict(conn, "SELECT * FROM information_schema.INNODB_SYS_TABLES WHERE NAME = %s", (name,))
    if not rows:
        return {}
    keep: tuple[str, ...] = ("TABLE_ID", "ROW_FORMAT", "INSTANT_COLS", "TOTAL_ROW_VERSIONS")
    return {k: rows[0][k] for k in keep if k in rows[0]}


def tablespace_mib(conn: pymysql.Connection, table: str) -> float:
    name: str = f"{DB}/{table}"
    rows: tuple[Any, ...]
    try:
        rows = run(conn, "SELECT FILE_SIZE FROM information_schema.INNODB_TABLESPACES WHERE NAME = %s", (name,))
    except pymysql.MySQLError:
        rows = run(conn, "SELECT FILE_SIZE FROM information_schema.INNODB_SYS_TABLESPACES WHERE NAME = %s", (name,))
    return round(int(rows[0][0]) / 1024 / 1024, 1) if rows else 0.0


def table_sizes(conn: pymysql.Connection, schema: str) -> list[tuple[str, int, float, float]]:
    try:
        run(conn, "SET SESSION information_schema_stats_expiry = 0")
    except pymysql.MySQLError:
        pass
    rows: tuple[Any, ...] = run(
        conn,
        "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME",
        (schema,),
    )
    return [(str(r[0]), int(r[1] or 0), int(r[2] or 0) / 1048576, int(r[3] or 0) / 1048576) for r in rows]


# ---------------------------------------------------------------- env


def section_env(server: Server) -> None:
    conn: pymysql.Connection = server.connect(database=None)
    version: str = str(run(conn, "SELECT VERSION()")[0][0])
    variables: dict[str, str] = {str(k): str(v) for k, v in run(conn, "SHOW GLOBAL VARIABLES")}
    out("## 0x00 环境")
    out(f"SELECT VERSION() = {version}")
    picked: dict[str, str] = {}
    name: str
    for name in VARIABLES:
        if name in variables:
            picked[name] = variables[name]
            out(f"  {name} = {variables[name]}")
        else:
            out(f"  {name} = （不存在）")
    switches: dict[str, str] = dict(item.split("=") for item in variables.get("optimizer_switch", "").split(","))
    flags: str = ", ".join(f"{k}={switches[k]}" for k in OPTIMIZER_FLAGS if k in switches)
    out(f"  optimizer_switch: {flags}")
    RESULT["version"] = version
    RESULT["variables"] = picked
    RESULT["optimizer_switch"] = variables.get("optimizer_switch", "")

    for statement in (f"DROP DATABASE IF EXISTS {DB}", f"DROP DATABASE IF EXISTS {DDL_DB}"):
        run(conn, statement)
    create: Outcome = attempt(conn, f"CREATE DATABASE {DB} DEFAULT CHARACTER SET utf8 COLLATE utf8_general_ci")
    run(conn, f"CREATE DATABASE {DDL_DB} DEFAULT CHARACTER SET utf8 COLLATE utf8_general_ci")
    db_charset: tuple[Any, ...] = run(
        conn,
        "SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
        (DB,),
    )[0]
    out(
        f"CREATE DATABASE ... DEFAULT CHARACTER SET utf8 → {create.brief(False)}；实际 {db_charset[0]} / {db_charset[1]}"
    )
    RESULT["database_charset"] = [db_charset[0], db_charset[1]]

    instruments: list[str] = [
        (
            "UPDATE performance_schema.setup_instruments SET ENABLED = 'YES', TIMED = 'YES' "
            "WHERE NAME = 'wait/lock/metadata/sql/mdl' OR NAME LIKE 'stage/innodb/alter%'"
        ),
        "UPDATE performance_schema.setup_consumers SET ENABLED = 'YES' WHERE NAME LIKE 'events_stages_%'",
    ]
    statement: str
    for statement in instruments:
        run(conn, statement)
    conn.close()
    out()


# ---------------------------------------------------------------- 1. 建表兼容


INT_BYTES: dict[str, int] = {"int": 4, "bigint": 8, "tinyint": 1, "datetime": 8}


def index_lengths(conn: pymysql.Connection, schema: str) -> list[str]:
    rows: tuple[Any, ...] = run(
        conn,
        "SELECT s.TABLE_NAME, s.INDEX_NAME, s.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_OCTET_LENGTH, c.CHARACTER_SET_NAME, "
        "c.COLLATION_NAME FROM information_schema.STATISTICS s JOIN information_schema.COLUMNS c "
        "ON c.TABLE_SCHEMA = s.TABLE_SCHEMA AND c.TABLE_NAME = s.TABLE_NAME AND c.COLUMN_NAME = s.COLUMN_NAME "
        "WHERE s.TABLE_SCHEMA = %s AND s.INDEX_NAME <> 'PRIMARY' ORDER BY s.TABLE_NAME, s.INDEX_NAME, s.SEQ_IN_INDEX",
        (schema,),
    )
    grouped: dict[tuple[str, str], list[tuple[str, int, str]]] = {}
    row: tuple[Any, ...]
    for row in rows:
        data_type: str = str(row[3])
        size: int = int(row[4]) if row[4] is not None else INT_BYTES.get(data_type, 0)
        charset: str = f" {row[5]}/{row[6]}" if row[5] else ""
        grouped.setdefault((str(row[0]), str(row[1])), []).append((str(row[2]), size, charset))
    lines: list[str] = []
    key: tuple[str, str]
    for key, columns in grouped.items():
        total: int = sum(size for _, size, _ in columns)
        longest: int = max(size for _, size, _ in columns)
        parts: str = " + ".join(f"{name}({size}{charset})" for name, size, charset in columns)
        lines.append(
            f"  {key[0]}.{key[1]}: {parts} = {total} B；单列最长 {longest} B"
            f"{' > 767（需 DYNAMIC/COMPRESSED + large prefix）' if longest > 767 else ' ≤ 767'}"
            f"{'；总长 > 3072' if total > 3072 else ''}"
        )
    return lines


def section_ddl(server: Server) -> None:
    out("## 0x01 建表兼容（库默认 utf8，连接 utf8mb4）")
    conn: pymysql.Connection = server.connect(database=DDL_DB)
    v8: bool = is_v8(conn)
    entries: list[dict[str, Any]] = []

    def probe(key: str, title: str, statements: Sequence[str], cleanup: Sequence[str] = ()) -> Outcome:
        outcome: Outcome = Outcome(True, 0.0)
        statement: str
        for statement in statements:
            outcome = attempt(conn, statement)
            if not outcome.ok:
                break
        out(f"[{key}] {title}: {outcome.brief(False)}")
        entries.append({"key": key, "title": title, **outcome.to_json()})
        for statement in cleanup:
            attempt(conn, statement)
        return outcome

    probe("D1", "指标表 metadata_timeseriesmetric（Django 现有形态）", [BASE_METRIC_DDL])
    probe("D2", "分组表 metadata_timeseriesscope", [SCOPE_DDL])
    probe(
        "D3",
        "X1 列扩展：ALTER ADD COLUMN ×5 + KEY(group_id, original_name)",
        [f"ALTER TABLE metadata_timeseriesmetric {X1_COLUMNS}, {X1_INDEX}"],
    )
    probe("D4", "X2 metric_meta_x2（field_id 主键）", [X2_DDL])
    probe("D5", "X3 metric_meta_x3（自增 id + UNIQUE(group_id, field_name)）", [X3_DDL])
    probe("D6", "report_scope（ascii_bin 哈希 + utf8mb4_bin 原值 + JSON）", [REPORT_SCOPE_DDL])
    probe("D7", "report_scope_label（utf8 键 + utf8mb4_bin 值 复合唯一键）", [LABEL_DDL])
    probe("D8", "report_member", [MEMBER_DDL])

    formats: tuple[Any, ...] = run(
        conn,
        "SELECT TABLE_NAME, ROW_FORMAT FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s ORDER BY 1",
        (DDL_DB,),
    )
    out("  行格式: " + ", ".join(f"{r[0]}={r[1]}" for r in formats))
    columns: tuple[Any, ...] = run(
        conn,
        "SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = %s AND COLUMN_NAME IN ('field_name', 'field_scope', 'original_name', 'scope_hash', "
        "'raw_scope', 'label_key', 'label_value', 'table_id', 'meta') ORDER BY 1, 2",
        (DDL_DB,),
    )
    out("  列字符集: " + "; ".join(f"{r[0]}.{r[1]} {r[2]} {r[3] or '-'}/{r[4] or '-'}" for r in columns))
    lengths: list[str] = index_lengths(conn, DDL_DB)
    out("  索引字节（列最大字节数；767 为 COMPACT/REDUNDANT 单列上限，3072 为 DYNAMIC 单列与总长上限）:")
    line: str
    for line in lengths:
        out(line)
    RESULT["index_lengths"] = lengths

    label_compact: str = LABEL_DDL.replace("report_scope_label", "p_label_compact") + " ROW_FORMAT=COMPACT"
    probe(
        "D9",
        "report_scope_label 改 ROW_FORMAT=COMPACT（utf8mb4 255 = 1020 B）",
        [label_compact],
        ["DROP TABLE IF EXISTS p_label_compact"],
    )
    x3_compact: str = X3_DDL.replace("metric_meta_x3", "p_x3_compact") + " ROW_FORMAT=COMPACT"
    probe(
        "D10",
        "metric_meta_x3 改 ROW_FORMAT=COMPACT（utf8 255 = 765 B）",
        [x3_compact],
        ["DROP TABLE IF EXISTS p_x3_compact"],
    )
    if v8:
        out("[D11] innodb_large_prefix=OFF: 8.0 已移除该变量，DYNAMIC 恒为 3072 B")
        entries.append({"key": "D11", "title": "innodb_large_prefix=OFF", "ok": None, "message": "8.0 已移除"})
    else:
        label_dyn: str = LABEL_DDL.replace("report_scope_label", "p_label_noprefix")
        probe(
            "D11",
            "5.7 SET GLOBAL innodb_large_prefix=OFF 后建 report_scope_label（模拟 5.6 升级上来的实例）",
            ["SET GLOBAL innodb_large_prefix = OFF", label_dyn],
            ["DROP TABLE IF EXISTS p_label_noprefix", "SET GLOBAL innodb_large_prefix = ON"],
        )
        attempt(conn, "SET GLOBAL innodb_large_prefix = ON")
    probe(
        "D12",
        "JSON 列表达式默认值 DEFAULT ('{}')",
        ["CREATE TABLE p_json_default (id int PRIMARY KEY, j json NOT NULL DEFAULT ('{}'))"],
        ["DROP TABLE IF EXISTS p_json_default"],
    )
    probe(
        "D13",
        "JSON 列直接建索引",
        ["CREATE TABLE p_json_index (id int PRIMARY KEY, j json, KEY idx_j (j))"],
        ["DROP TABLE IF EXISTS p_json_index"],
    )
    # Django AddField(JSONField(default=dict)) 的两种生成形态：5.7 无默认值 + 全表 UPDATE；8.0.13+ 表达式默认值后再 DROP DEFAULT
    run(conn, "CREATE TABLE p_addfield (id int AUTO_INCREMENT PRIMARY KEY, name varchar(32) NOT NULL)")
    run(conn, "INSERT INTO p_addfield (name) VALUES " + ",".join(["('x')"] * 1000))
    legacy: Outcome = probe(
        "D15",
        "Django 5.7 形态：ADD COLUMN cfg json NOT NULL（1000 行已有数据）",
        ["ALTER TABLE p_addfield ADD COLUMN cfg json NOT NULL"],
    )
    if legacy.ok:
        implicit: tuple[Any, ...] = run(conn, "SELECT cfg, cfg IS NULL FROM p_addfield LIMIT 1")[0]
        update: Outcome = attempt(conn, "UPDATE p_addfield SET cfg = %s", ("{}",))
        out(
            f"      已有行的隐式值 = {implicit[0]!r}（IS NULL={implicit[1]}）；随后 Django 执行 UPDATE 全表 → {update.affected} 行"
        )
        entries[-1]["implicit_value"] = str(implicit[0])
    probe(
        "D16",
        "Django 8.0.13+ 形态：ADD COLUMN cfg2 json DEFAULT ('{}') NOT NULL + DROP DEFAULT",
        [
            "ALTER TABLE p_addfield ADD COLUMN cfg2 json DEFAULT ('{}') NOT NULL",
            "ALTER TABLE p_addfield ALTER COLUMN cfg2 DROP DEFAULT",
        ],
    )
    probe(
        "D17",
        "同上并指定 ALGORITHM=INSTANT",
        ["ALTER TABLE p_addfield ADD COLUMN cfg3 json DEFAULT ('{}') NOT NULL, ALGORITHM=INSTANT"],
    )
    RESULT["ddl"] = entries
    run(conn, f"DROP DATABASE {DDL_DB}")
    conn.close()
    out()


# ---------------------------------------------------------------- 2. 在线 DDL


@dataclass
class Sample:
    start: float
    latency_ms: float
    error: str = ""


class Workload(threading.Thread):
    def __init__(self, server: Server, name: str, sql: str, params: Callable[[random.Random], Sequence[Any]]) -> None:
        super().__init__(daemon=True)
        self.server: Server = server
        self.label: str = name
        self.sql: str = sql
        self.params: Callable[[random.Random], Sequence[Any]] = params
        self.samples: list[Sample] = []
        self.stop_event: threading.Event = threading.Event()

    def run(self) -> None:
        conn: pymysql.Connection = self.server.connect()
        rng: random.Random = random.Random(self.label)
        while not self.stop_event.is_set():
            params: Sequence[Any] = self.params(rng)
            start: float = time.perf_counter()
            error: str = ""
            try:
                run(conn, self.sql, params)
            except pymysql.MySQLError as exc:
                error = str(exc.args[0]) if exc.args else "error"
            self.samples.append(Sample(start, (time.perf_counter() - start) * 1000, error))
            self.stop_event.wait(WORKLOAD_INTERVAL)
        conn.close()


@dataclass
class MonitorSample:
    at: float
    waiting: int
    alter_state: str
    alter_locks: tuple[str, ...]
    stages: tuple[str, ...]


class MdlMonitor(threading.Thread):
    """每 100 ms 采样：等待元数据锁的业务连接数、ALTER 线程状态、ALTER 持有的 MDL、InnoDB ALTER 阶段。"""

    def __init__(self, server: Server, alter_id: int, table: str) -> None:
        super().__init__(daemon=True)
        self.server: Server = server
        self.alter_id: int = alter_id
        self.table: str = table
        self.samples: list[MonitorSample] = []
        self.stop_event: threading.Event = threading.Event()

    def run(self) -> None:
        conn: pymysql.Connection = self.server.connect()
        while not self.stop_event.is_set():
            at: float = time.perf_counter()
            processes: tuple[Any, ...] = run(
                conn,
                "SELECT ID, STATE FROM information_schema.PROCESSLIST WHERE COMMAND <> 'Sleep' AND ID <> CONNECTION_ID()",
            )
            waiting: int = sum(
                1 for pid, state in processes if pid != self.alter_id and state == "Waiting for table metadata lock"
            )
            alter_state: str = next((str(state or "") for pid, state in processes if pid == self.alter_id), "")
            locks: tuple[Any, ...] = run(
                conn,
                "SELECT ml.LOCK_TYPE, ml.LOCK_STATUS FROM performance_schema.metadata_locks ml "
                "JOIN performance_schema.threads t ON t.THREAD_ID = ml.OWNER_THREAD_ID "
                "WHERE ml.OBJECT_TYPE = 'TABLE' AND ml.OBJECT_SCHEMA = %s AND ml.OBJECT_NAME = %s AND t.PROCESSLIST_ID = %s",
                (DB, self.table, self.alter_id),
            )
            stages: tuple[Any, ...] = run(
                conn,
                "SELECT EVENT_NAME FROM performance_schema.events_stages_current WHERE EVENT_NAME LIKE 'stage/innodb/alter%%'",
                (),
            )
            self.samples.append(
                MonitorSample(
                    at,
                    waiting,
                    alter_state,
                    tuple(f"{t}/{s}" for t, s in locks),
                    tuple(str(s[0]).replace("stage/innodb/alter table ", "") for s in stages),
                )
            )
            self.stop_event.wait(0.1)
        conn.close()


class Blocker(threading.Thread):
    """开启事务读一行后保持不提交，模拟持有共享元数据锁的长事务。"""

    def __init__(self, server: Server, hold: float) -> None:
        super().__init__(daemon=True)
        self.server: Server = server
        self.hold: float = hold

    def run(self) -> None:
        conn: pymysql.Connection = self.server.connect(autocommit=False)
        run(conn, "BEGIN")
        run(conn, "SELECT field_id FROM metadata_timeseriesmetric WHERE field_id = 1")
        time.sleep(self.hold)
        run(conn, "COMMIT")
        conn.close()


@dataclass
class AlterCase:
    key: str
    title: str
    statements: list[str]
    blocker_hold: float = 0.0
    lock_wait_timeout: int = 0
    only_v8: bool = False


def unique_in_order(items: Sequence[str]) -> list[str]:
    seen: list[str] = []
    item: str
    for item in items:
        if item and item not in seen:
            seen.append(item)
    return seen


def latency_summary(samples: Sequence[Sample], start: float, end: float) -> dict[str, Any]:
    during: list[Sample] = [s for s in samples if start <= s.start < end]
    baseline: list[Sample] = [s for s in samples if s.start < start]
    values: list[float] = [s.latency_ms for s in during]
    base_values: list[float] = [s.latency_ms for s in baseline]
    worst: Sample | None = max(during, key=lambda s: s.latency_ms, default=None)
    return {
        "n": len(during),
        "p50": round(pct(values, 0.5), 2),
        "p99": round(pct(values, 0.99), 2),
        "max": round(max(values), 1) if values else 0.0,
        "max_at_s": round(worst.start - start, 2) if worst else None,
        "over_100ms": sum(1 for v in values if v > 100),
        "over_500ms": sum(1 for v in values if v > 500),
        "errors": sorted({s.error for s in during if s.error}),
        "baseline_p50": round(pct(base_values, 0.5), 2),
        "baseline_max": round(max(base_values), 1) if base_values else 0.0,
    }


def load_online_table(server: Server, rows: int) -> None:
    conn: pymysql.Connection = server.connect()
    run(conn, "DROP TABLE IF EXISTS metadata_timeseriesmetric")
    run(conn, BASE_METRIC_DDL)
    columns: list[str] = [
        "field_id",
        "group_id",
        "table_id",
        "field_name",
        "tag_list",
        "last_modify_time",
        "label",
        "last_index",
        "create_time",
        "field_config",
        "field_scope",
        "scope_id",
        "is_active",
    ]
    loader: Loader = Loader(conn, "metadata_timeseriesmetric", columns)
    tags: list[str] = [tag_list_json(i) for i in range(5)]
    groups: int = max(1, rows // ONLINE_METRICS_PER_GROUP)
    start: float = time.perf_counter()
    field_id: int = 0
    g: int
    for g in range(1, groups + 1):
        data_id: int = 1_500_000 + g
        i: int
        for i in range(ONLINE_METRICS_PER_GROUP):
            field_id += 1
            name: str = metric_identity(i)[0]
            config: str = '{"unit": "ms", "alias": "耗时"}' if i % 20 == 0 else "{}"
            loader.add(
                [
                    field_id,
                    g,
                    f"2_bkmonitor_time_series_{data_id}.{name}",
                    name,
                    tags[i % 5],
                    BASE_TIME,
                    "",
                    0,
                    BASE_TIME,
                    config,
                    "default",
                    g * 10 + i % 5,
                    1,
                ]
            )
    loader.flush()
    load_seconds: float = time.perf_counter() - start
    run(conn, "ANALYZE TABLE metadata_timeseriesmetric")
    run(conn, "SELECT COUNT(*) FROM metadata_timeseriesmetric FORCE INDEX (PRIMARY)")
    size: float = tablespace_mib(conn, "metadata_timeseriesmetric")
    out(
        f"装载 {loader.total:,} 行（{groups:,} 分组 × {ONLINE_METRICS_PER_GROUP}），耗时 {load_seconds:.1f} s，表空间 {size} MiB"
    )
    RESULT["online_load"] = {"rows": loader.total, "seconds": round(load_seconds, 1), "tablespace_mib": size}
    conn.close()


def run_alter_case(server: Server, case: AlterCase, rows: int) -> dict[str, Any]:
    table: str = "metadata_timeseriesmetric"
    admin: pymysql.Connection = server.connect()
    info_before: dict[str, Any] = innodb_table_info(admin, table)
    size_before: float = tablespace_mib(admin, table)
    groups: int = max(1, rows // ONLINE_METRICS_PER_GROUP)
    alter_conn: pymysql.Connection = server.connect()
    alter_id: int = int(run(alter_conn, "SELECT CONNECTION_ID()")[0][0])
    if case.lock_wait_timeout:
        run(alter_conn, f"SET SESSION lock_wait_timeout = {case.lock_wait_timeout}")
    workloads: list[Workload] = [
        Workload(
            server,
            "UPDATE last_modify_time",
            f"UPDATE {table} SET last_modify_time = NOW(6) WHERE field_id = %s",
            lambda rng: (rng.randint(1, rows),),
        ),
        Workload(
            server,
            "SELECT 分组首页",
            f"SELECT field_id, field_name FROM {table} WHERE group_id = %s AND field_scope = 'default' "
            "ORDER BY field_name LIMIT 50",
            lambda rng: (rng.randint(1, groups),),
        ),
    ]
    monitor: MdlMonitor = MdlMonitor(server, alter_id, table)
    worker: threading.Thread
    for worker in [*workloads, monitor]:
        worker.start()
    time.sleep(BASELINE_SECONDS)
    blocker: Blocker | None = None
    if case.blocker_hold:
        blocker = Blocker(server, case.blocker_hold)
        blocker.start()
        time.sleep(0.3)
    started: float = time.perf_counter()
    outcomes: list[Outcome] = []
    statement: str
    for statement in case.statements:
        outcomes.append(attempt(alter_conn, statement))
        if not outcomes[-1].ok:
            break
    finished: float = time.perf_counter()
    time.sleep(1.0)
    for worker in [*workloads, monitor]:
        worker.stop_event.set()  # type: ignore[attr-defined]
        worker.join()
    if blocker is not None:
        blocker.join()
    info_after: dict[str, Any] = innodb_table_info(admin, table)
    size_after: float = tablespace_mib(admin, table)
    admin.close()
    alter_conn.close()

    window: list[MonitorSample] = [m for m in monitor.samples if started <= m.at <= finished + 0.05]
    stages: list[str] = unique_in_order([s for m in window for s in m.stages])
    states: list[str] = unique_in_order([m.alter_state for m in window])
    locks: list[str] = unique_in_order([lock for m in window for lock in m.alter_locks])
    rebuilt: bool = bool(info_before) and info_before.get("TABLE_ID") != info_after.get("TABLE_ID")
    wait_samples: int = sum(1 for m in window if m.waiting)
    result: dict[str, Any] = {
        "key": case.key,
        "title": case.title,
        "statements": case.statements,
        "outcomes": [o.to_json() for o in outcomes],
        "elapsed_ms": round((finished - started) * 1000, 1),
        "rebuilt": rebuilt,
        "table_before": info_before,
        "table_after": info_after,
        "tablespace_mib": [size_before, size_after],
        "stages": stages,
        "alter_states": states,
        "alter_mdl": locks,
        "mdl_wait_samples": wait_samples,
        "mdl_wait_max_sessions": max((m.waiting for m in window), default=0),
        "workloads": {w.label: latency_summary(w.samples, started, finished) for w in workloads},
    }
    out(f"[{case.key}] {case.title}")
    for statement, outcome in zip(case.statements, outcomes, strict=False):
        out(f"  SQL: {statement}")
        out(f"  结果: {outcome.brief()}")
    out(
        f"  重建: {'是' if rebuilt else '否'}（table {info_before} → {info_after}）；表空间 {size_before} → {size_after} MiB"
    )
    out(f"  InnoDB 阶段: {' → '.join(stages) or '无'}")
    out(f"  ALTER 线程状态: {' → '.join(states) or '无'}；ALTER 持有/等待的 MDL: {', '.join(locks) or '无'}")
    out(
        f"  业务连接 MDL 等待: {wait_samples} 次采样（100 ms 间隔），最多 {result['mdl_wait_max_sessions']} 个连接同时等待"
    )
    label: str
    stats: dict[str, Any]
    for label, stats in result["workloads"].items():
        out(
            f"  并发 {label}: ALTER 期间 n={stats['n']} p50={stats['p50']} ms p99={stats['p99']} ms "
            f"max={stats['max']} ms（开始于 ALTER 后 {stats['max_at_s']} s）>100ms={stats['over_100ms']} "
            f">500ms={stats['over_500ms']} 错误={stats['errors'] or '无'}；"
            f"基线 p50={stats['baseline_p50']} ms max={stats['baseline_max']} ms"
        )
    return result


def section_online(server: Server, rows: int) -> None:
    out(f"## 0x02 在线 DDL（metadata_timeseriesmetric {rows:,} 行）")
    load_online_table(server, rows)
    conn: pymysql.Connection = server.connect()
    v8: bool = is_v8(conn)
    conn.close()
    t: str = "ALTER TABLE metadata_timeseriesmetric"
    cases: list[AlterCase] = [
        AlterCase("S1", "X1 ADD COLUMN ×5, ALGORITHM=INSTANT", [f"{t} {X1_COLUMNS}, ALGORITHM=INSTANT"]),
        AlterCase(
            "S1b",
            "回滚 S1：DROP COLUMN ×5, ALGORITHM=INSTANT（8.0.29+）",
            [f"{t} {X1_DROP_COLUMNS}, ALGORITHM=INSTANT"],
            only_v8=True,
        ),
        AlterCase(
            "S2", "X1 ADD COLUMN ×5, ALGORITHM=INPLACE, LOCK=NONE", [f"{t} {X1_COLUMNS}, ALGORITHM=INPLACE, LOCK=NONE"]
        ),
        AlterCase(
            "S3",
            "ADD INDEX (group_id, original_name), ALGORITHM=INPLACE, LOCK=NONE",
            [f"{t} {X1_INDEX}, ALGORITHM=INPLACE, LOCK=NONE"],
        ),
        AlterCase(
            "S4",
            "Django AddField 默认形态：单列 ADD COLUMN ... NULL，不写 ALGORITHM",
            [f"{t} ADD COLUMN `probe_col` varchar(16) NULL"],
        ),
        AlterCase(
            "S5",
            "长事务持有共享 MDL 3 s，期间执行仅改元数据的 ALTER（lock_wait_timeout=10）",
            [f"{t} ALTER COLUMN `label` SET DEFAULT 'x'"],
            blocker_hold=3.0,
            lock_wait_timeout=10,
        ),
        AlterCase(
            "S6",
            "同 S5，但 ALTER 会话 lock_wait_timeout=1",
            [f"{t} ALTER COLUMN `label` SET DEFAULT 'y'"],
            blocker_hold=3.0,
            lock_wait_timeout=1,
        ),
    ]
    results: list[dict[str, Any]] = []
    case: AlterCase
    for case in cases:
        if case.only_v8 and not v8:
            continue
        results.append(run_alter_case(server, case, rows))
    RESULT["online"] = results
    conn = server.connect()
    run(conn, "DROP TABLE metadata_timeseriesmetric")
    conn.close()
    out()


# ---------------------------------------------------------------- 3. 执行计划


@dataclass
class PlanData:
    xl_service: str
    xl_scope_name: str
    sample_service: str
    tuples: list[tuple[int, int, int]]


def load_plan_tables(server: Server, scale: float) -> PlanData:
    conn: pymysql.Connection = server.connect()
    statement: str
    for statement in (
        "DROP TABLE IF EXISTS metadata_timeseriesmetric",
        "DROP TABLE IF EXISTS metadata_timeseriesscope",
        "DROP TABLE IF EXISTS metric_meta_x2",
        "DROP TABLE IF EXISTS metric_meta_x3",
        "DROP TABLE IF EXISTS report_scope",
        "DROP TABLE IF EXISTS report_scope_label",
        "DROP TABLE IF EXISTS report_member",
    ):
        run(conn, statement)
    for statement in (BASE_METRIC_DDL, SCOPE_DDL, X2_DDL, X3_DDL, REPORT_SCOPE_DDL, LABEL_DDL, MEMBER_DDL):
        run(conn, statement)
    run(conn, f"ALTER TABLE metadata_timeseriesmetric {X1_COLUMNS}, {X1_INDEX}")

    groups: int = max(10, int(PLAN_GROUPS * scale))
    xl_metrics: int = max(1000, int(XL_METRICS * scale))
    metric_loader: Loader = Loader(
        conn,
        "metadata_timeseriesmetric",
        [
            "field_id",
            "group_id",
            "table_id",
            "field_name",
            "tag_list",
            "last_modify_time",
            "label",
            "last_index",
            "create_time",
            "field_config",
            "field_scope",
            "scope_id",
            "is_active",
            "original_name",
            "metric_type",
            "meta",
            "meta_fingerprint",
            "meta_seen_at",
        ],
    )
    scope_loader: Loader = Loader(
        conn,
        "metadata_timeseriesscope",
        ["id", "group_id", "scope_name", "dimension_config", "auto_rules", "create_from", "last_modify_time"],
    )
    x2_loader: Loader = Loader(
        conn,
        "metric_meta_x2",
        ["field_id", "group_id", "original_name", "metric_type", "meta", "fingerprint", "seen_at"],
    )
    x3_loader: Loader = Loader(
        conn,
        "metric_meta_x3",
        ["id", "group_id", "field_name", "original_name", "metric_type", "meta", "fingerprint", "seen_at"],
    )
    rs_loader: Loader = Loader(
        conn, "report_scope", ["id", "group_id", "scope_type", "scope_hash", "raw_scope", "labels", "last_seen"]
    )
    label_loader: Loader = Loader(
        conn, "report_scope_label", ["group_id", "label_key", "label_value", "report_scope_id"]
    )
    member_loader: Loader = Loader(
        conn, "report_member", ["group_id", "report_scope_id", "ref_id", "last_seen", "meta"]
    )
    tags: list[str] = [tag_list_json(i) for i in range(5)]

    field_id: int = 0
    ts_scope_id: int = 0
    report_scope_id: int = 0
    start: float = time.perf_counter()
    g: int
    for g in range(1, groups + 1):
        xl: bool = g == XL_GROUP
        metric_count: int = xl_metrics if xl else REGULAR_METRICS
        ts_scope_count: int = XL_TS_SCOPES if xl else REGULAR_TS_SCOPES
        rs_count: int = XL_REPORT_SCOPES if xl else REGULAR_REPORT_SCOPES
        ts_scope_base: int = ts_scope_id
        k: int
        for k in range(ts_scope_count):
            ts_scope_id += 1
            scope_loader.add([ts_scope_id, g, f"svc-{k:03d}||default", "{}", "[]", "data", BASE_TIME])
        rs_base: int = report_scope_id
        half: int = rs_count // 2
        j: int
        for j in range(rs_count):
            report_scope_id += 1
            labels: dict[str, str] = {"service_name": f"svc-{j % half:03d}", "scope_name": ("http", "grpc")[j // half]}
            rs_loader.add(
                [
                    report_scope_id,
                    g,
                    "APM",
                    md5_hex("APM" + canonical(labels)),
                    apm_raw_scope(labels["service_name"], labels["scope_name"]),
                    json.dumps(labels, sort_keys=True),
                    BASE_TIME,
                ]
            )
            label_key: str
            for label_key in sorted(labels):
                label_loader.add([g, label_key, labels[label_key], report_scope_id])
        data_id: int = 1_500_000 + g
        i: int
        name: str
        original: str | None
        metric_type: str
        for i in range(metric_count):
            field_id += 1
            name, original, metric_type = metric_identity(i)
            meta: str | None = meta_json(original, metric_type) if original else None
            fingerprint: str | None = md5_hex(meta) if meta else None
            metric_loader.add(
                [
                    field_id,
                    g,
                    f"2_bkmonitor_time_series_{data_id}.{name}",
                    name,
                    tags[i % 5],
                    BASE_TIME,
                    "",
                    0,
                    BASE_TIME,
                    "{}",
                    "default",
                    ts_scope_base + 1 + (i // 10) % ts_scope_count,
                    1,
                    original,
                    metric_type if original else None,
                    meta,
                    fingerprint,
                    BASE_TIME if original else None,
                ]
            )
            if original and meta and fingerprint:
                x2_loader.add([field_id, g, original, metric_type, meta, fingerprint, BASE_TIME])
            x3_meta: str = meta or meta_json(name, metric_type)
            x3_loader.add([field_id, g, name, original or name, metric_type, x3_meta, md5_hex(x3_meta), BASE_TIME])
            scope_indexes: list[int] = (
                [(i * 7 + step * (rs_count // XL_SCOPES_PER_METRIC)) % rs_count for step in range(XL_SCOPES_PER_METRIC)]
                if xl
                else list(range(rs_count))
            )
            idx: int
            for idx in scope_indexes:
                mix: int = (g * 7919 + i * 104729 + idx * 1299709) % 1000
                last_seen: str = EXPIRED_AT if mix < 10 else f"2026-10-10 {mix % 24:02d}:00:00"
                member_meta: str | None = '{"unit": "ms"}' if mix == 999 else None
                member_loader.add([g, rs_base + 1 + idx, field_id, last_seen, member_meta])
    loader: Loader
    for loader in (metric_loader, scope_loader, x2_loader, x3_loader, rs_loader, label_loader, member_loader):
        loader.flush()
    load_seconds: float = time.perf_counter() - start
    table: str
    for table in (
        "metadata_timeseriesmetric",
        "metadata_timeseriesscope",
        "metric_meta_x2",
        "metric_meta_x3",
        "report_scope",
        "report_scope_label",
        "report_member",
    ):
        run(conn, f"ANALYZE TABLE {table}")
    out(
        f"装载 {groups:,} 分组：指标 {metric_loader.total:,}、X2 {x2_loader.total:,}、X3 {x3_loader.total:,}、"
        f"上报范围 {rs_loader.total:,}、标签 {label_loader.total:,}、成员 {member_loader.total:,}；"
        f"XL 分组 {XL_GROUP}：{xl_metrics:,} 指标 × {XL_SCOPES_PER_METRIC} 范围；耗时 {load_seconds:.1f} s"
    )
    sizes: list[tuple[str, int, float, float]] = table_sizes(conn, DB)
    out("  表大小: " + "; ".join(f"{n} 约 {r:,} 行 数据 {d:.1f} MiB 索引 {x:.1f} MiB" for n, r, d, x in sizes))
    RESULT["plan_load"] = {
        "groups": groups,
        "metrics": metric_loader.total,
        "x2": x2_loader.total,
        "x3": x3_loader.total,
        "report_scopes": rs_loader.total,
        "labels": label_loader.total,
        "members": member_loader.total,
        "seconds": round(load_seconds, 1),
        "sizes": sizes,
    }
    tuples: list[tuple[int, int, int]] = [
        (int(a), int(b), int(c))
        for a, b, c in run(
            conn,
            "SELECT group_id, report_scope_id, ref_id FROM report_member WHERE group_id = %s ORDER BY RAND(7) LIMIT %s",
            (XL_GROUP, ROW_IN_TUPLES),
        )
    ]
    conn.close()
    return PlanData("svc-007", "grpc", "svc-001", tuples)


def short_table(row: dict[str, Any]) -> str:
    table: str = str(row.get("table"))
    return table if len(table) <= 32 else table[:28] + "...>"


def plan_signature(rows: Sequence[dict[str, Any]]) -> list[str]:
    """把 EXPLAIN 行压缩成 table:type/key(key_len) rows=估算 Extra；连续同形行合并计数，rows 取合计。"""
    shapes: list[tuple[str, str]] = []
    counts: list[int] = []
    estimates: list[int] = []
    row: dict[str, Any]
    for row in rows:
        head: str = f"{short_table(row)}:{row.get('type')}/{row.get('key') or '-'}({row.get('key_len') or '-'})"
        extra: str = str(row.get("Extra") or "")
        estimate: int = int(row.get("rows") or 0)
        if shapes and shapes[-1] == (head, extra):
            counts[-1] += 1
            estimates[-1] += estimate
        else:
            shapes.append((head, extra))
            counts.append(1)
            estimates.append(estimate)
    lines: list[str] = []
    index: int
    for index, (head, extra) in enumerate(shapes):
        prefix: str = f"×{counts[index]} " if counts[index] > 1 else ""
        lines.append(f"{prefix}{head} rows={estimates[index]} {extra}".rstrip())
    return lines


def plan_flags(rows: Sequence[dict[str, Any]]) -> list[list[Any]]:
    signature: list[list[Any]] = []
    seen: set[str] = set()
    row: dict[str, Any]
    for row in rows:
        extra: str = str(row.get("Extra") or "")
        item: list[Any] = [
            short_table(row),
            str(row.get("type")),
            str(row.get("key") or "-"),
            "filesort" in extra,
            "temporary" in extra,
        ]
        key: str = json.dumps(item)
        if key not in seen:
            seen.add(key)
            signature.append(item)
    return signature


STATUS_SQL: str = (
    "SHOW SESSION STATUS WHERE Variable_name LIKE 'Handler_read%' OR Variable_name IN "
    "('Sort_rows', 'Created_tmp_tables', 'Created_tmp_disk_tables', 'Select_scan', 'Select_full_join')"
)


def session_counters(conn: pymysql.Connection, sql: str, params: Sequence[Any] | None) -> dict[str, int]:
    run(conn, "FLUSH STATUS")
    run(conn, sql, params)
    raw: dict[str, int] = {str(k): int(v) for k, v in run(conn, STATUS_SQL)}
    reads: int = sum(v for k, v in raw.items() if k.startswith("Handler_read"))
    return {
        "handler_reads": reads,
        "sort_rows": raw.get("Sort_rows", 0),
        "tmp_tables": raw.get("Created_tmp_tables", 0),
        "tmp_disk_tables": raw.get("Created_tmp_disk_tables", 0),
        "select_scan": raw.get("Select_scan", 0),
    }


@dataclass
class Query:
    key: str
    title: str
    sql: str
    params: Sequence[Any] | None
    runs: int = 15


def explain_query(conn: pymysql.Connection, query: Query, v8: bool) -> dict[str, Any]:
    entry: dict[str, Any] = {"title": query.title, "sql": query.sql}
    try:
        rows: list[dict[str, Any]] = run_dict(conn, "EXPLAIN " + query.sql, query.params)
        warnings: list[tuple[Any, ...]] = [w for w in run(conn, "SHOW WARNINGS") if int(w[1]) != 1003]
    except pymysql.MySQLError as exc:
        entry["error"] = f"{exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ''}"
        out(f"[{query.key}] {query.title}")
        out(f"  ERROR {entry['error']}")
        return entry
    entry["explain"] = [{k: (str(v) if v is not None else None) for k, v in r.items()} for r in rows]
    entry["summary"] = plan_signature(rows)
    entry["flags"] = plan_flags(rows)
    entry["warnings"] = [[str(w[0]), int(w[1]), str(w[2])] for w in warnings]
    counters: dict[str, int] = session_counters(conn, query.sql, query.params)
    run(conn, query.sql, query.params)
    run(conn, query.sql, query.params)
    timings: list[float] = []
    returned: int = 0
    _: int
    for _ in range(query.runs):
        start: float = time.perf_counter()
        result: tuple[Any, ...] = run(conn, query.sql, query.params)
        timings.append((time.perf_counter() - start) * 1000)
        returned = len(result)
    entry["rows_returned"] = returned
    entry["time_ms"] = {"median": round(statistics.median(timings), 2), "p95": round(pct(timings, 0.95), 2)}
    entry["counters"] = counters
    if v8:
        try:
            analyze: str = str(run(conn, "EXPLAIN ANALYZE " + query.sql, query.params)[0][0])
            entry["analyze"] = analyze
        except pymysql.MySQLError as exc:
            entry["analyze"] = f"ERROR {exc.args[0]}"
    out(f"[{query.key}] {query.title}")
    for line in entry["summary"]:
        out(f"  plan: {line}")
    if entry["warnings"]:
        out("  warnings: " + " ｜ ".join(f"{w[1]} {w[2][:160]}" for w in entry["warnings"]))
    out(
        f"  执行: median {entry['time_ms']['median']} ms p95 {entry['time_ms']['p95']} ms 返回 {returned} 行；"
        f"Handler_read 合计 {counters['handler_reads']:,} Sort_rows {counters['sort_rows']:,} "
        f"临时表 {counters['tmp_tables']}（磁盘 {counters['tmp_disk_tables']}）"
    )
    if v8 and "analyze" in entry:
        lines: list[str] = entry["analyze"].splitlines()
        for line in lines[:12]:
            out(f"  analyze: {line[:200]}")
        if len(lines) > 12:
            out(f"  analyze: ...（共 {len(lines)} 行）")
    return entry


def section_plans(server: Server, scale: float) -> None:
    out("## 0x03 执行计划")
    data: PlanData = load_plan_tables(server, scale)
    conn: pymysql.Connection = server.connect()
    v8: bool = is_v8(conn)
    plans: dict[str, dict[str, Any]] = {}

    def explain(query: Query) -> None:
        plans[query.key] = explain_query(conn, query, v8)

    m: str = "metadata_timeseriesmetric"
    xl: int = XL_GROUP
    sg: int = SAMPLE_GROUP if SAMPLE_GROUP <= RESULT["plan_load"]["groups"] else 2
    page_sql: str = (
        f"SELECT field_id, field_name, scope_id FROM {m} WHERE group_id = %s ORDER BY field_name LIMIT %s, 50"
    )
    page_scope_sql: str = (
        f"SELECT field_id, field_name, scope_id FROM {m} WHERE group_id = %s AND field_scope = 'default' "
        "ORDER BY field_name LIMIT %s, 50"
    )
    out("### Q1 单分组列表")
    explain(Query("Q1a", "XL 分组 ORDER BY field_name LIMIT 50", page_sql, (xl, 0)))
    explain(Query("Q1a-s", "普通分组 ORDER BY field_name LIMIT 50", page_sql, (sg, 0)))
    explain(Query("Q1a-fs", "XL 分组 + field_scope='default' ORDER BY field_name LIMIT 50", page_scope_sql, (xl, 0)))
    explain(Query("Q1b", "XL 分组 ORDER BY field_name LIMIT 10000, 50", page_sql, (xl, 10_000)))
    explain(Query("Q1b-fs", "XL 分组 + field_scope='default' LIMIT 10000, 50", page_scope_sql, (xl, 10_000)))
    explain(Query("Q1c", "XL 分组 COUNT(*)", f"SELECT COUNT(*) FROM {m} WHERE group_id = %s", (xl,)))
    explain(
        Query(
            "Q1d",
            "XL 分组 field_name LIKE '%cache%' ORDER BY field_name LIMIT 50",
            f"SELECT field_id, field_name FROM {m} WHERE group_id = %s AND field_name LIKE %s ORDER BY field_name LIMIT 50",
            (xl, "%cache%"),
        )
    )
    explain(
        Query(
            "Q1d-fs",
            "XL 分组 + field_scope='default' + LIKE '%cache%' LIMIT 50",
            f"SELECT field_id, field_name FROM {m} WHERE group_id = %s AND field_scope = 'default' AND field_name LIKE %s "
            "ORDER BY field_name LIMIT 50",
            (xl, "%cache%"),
        )
    )

    out("### Q2 节点分页（节点 = scope_id + COALESCE(original_name, field_name)）")
    x1_nodes: str = (
        f"SELECT scope_id, COALESCE(original_name, field_name) AS node, COUNT(*) AS metric_count FROM {m} "
        "WHERE group_id = %s GROUP BY scope_id, node ORDER BY scope_id, node LIMIT %s, 50"
    )
    x2_nodes: str = (
        f"SELECT m.scope_id, COALESCE(x.original_name, m.field_name) AS node, COUNT(*) AS metric_count FROM {m} m "
        "LEFT JOIN metric_meta_x2 x ON x.field_id = m.field_id WHERE m.group_id = %s "
        "GROUP BY m.scope_id, node ORDER BY m.scope_id, node LIMIT %s, 50"
    )
    x3_nodes: str = (
        f"SELECT m.scope_id, COALESCE(x.original_name, m.field_name) AS node, COUNT(*) AS metric_count FROM {m} m "
        "LEFT JOIN metric_meta_x3 x ON x.group_id = m.group_id AND x.field_name = m.field_name WHERE m.group_id = %s "
        "GROUP BY m.scope_id, node ORDER BY m.scope_id, node LIMIT %s, 50"
    )
    window_nodes: str = (
        "SELECT scope_id, node, field_id, field_name FROM ("
        "SELECT field_id, field_name, scope_id, COALESCE(original_name, field_name) AS node, "
        "DENSE_RANK() OVER (ORDER BY scope_id, COALESCE(original_name, field_name)) AS rk "
        f"FROM {m} WHERE group_id = %s) t WHERE rk > %s AND rk <= %s ORDER BY rk, field_name"
    )
    explain(Query("Q2-X1", "X1 GROUP BY 节点首页（XL）", x1_nodes, (xl, 0)))
    explain(Query("Q2-X1-deep", "X1 GROUP BY 节点 OFFSET 10000（XL）", x1_nodes, (xl, 10_000)))
    explain(Query("Q2-X1-s", "X1 GROUP BY 节点首页（普通分组）", x1_nodes, (sg, 0)))
    explain(Query("Q2-X2", "X2 LEFT JOIN 一对一表 GROUP BY 节点首页（XL）", x2_nodes, (xl, 0)))
    explain(Query("Q2-X3", "X3 LEFT JOIN 定义表 (group_id, field_name) GROUP BY 节点首页（XL）", x3_nodes, (xl, 0)))
    explain(Query("Q2-WIN", "窗口函数 DENSE_RANK 一次取第 1-50 个节点及其指标（8.0 写法）", window_nodes, (xl, 0, 50)))
    first_page: tuple[Any, ...] = run(conn, x1_nodes, (xl, 0))
    node_pairs: list[tuple[int, str]] = [(int(r[0]), str(r[1])) for r in first_page]
    pair_sql: str = ", ".join(["(%s, %s)"] * len(node_pairs))
    pair_params: list[Any] = [v for pair in node_pairs for v in pair]
    scopes_in: list[int] = sorted({p[0] for p in node_pairs})
    names_in: list[str] = sorted({p[1] for p in node_pairs})
    explain(
        Query(
            "Q2-X1-step2",
            "5.7 两步法第 2 步：按第 1 步的 50 个节点取指标（COALESCE 表达式过滤）",
            f"SELECT field_id, field_name, scope_id, COALESCE(original_name, field_name) AS node FROM {m} "
            f"WHERE group_id = %s AND scope_id IN ({', '.join(['%s'] * len(scopes_in))}) "
            f"AND COALESCE(original_name, field_name) IN ({', '.join(['%s'] * len(names_in))}) ORDER BY scope_id, node, field_name",
            (xl, *scopes_in, *names_in),
        )
    )
    gc: Outcome = attempt(
        conn,
        f"ALTER TABLE {m} ADD COLUMN `node_name` varchar(255) COLLATE utf8_bin "
        "GENERATED ALWAYS AS (COALESCE(`original_name`, `field_name`)) VIRTUAL, "
        "ADD INDEX `idx_group_scope_node` (`group_id`, `scope_id`, `node_name`)",
    )
    out(f"[GC] 虚拟生成列 node_name + KEY(group_id, scope_id, node_name)（5.7 可用的函数索引替代）: {gc.brief()}")
    plans["GC"] = {"title": "虚拟生成列 + 索引", "ddl": gc.to_json()}
    if gc.ok:
        run(conn, f"ANALYZE TABLE {m}")
        gc_nodes: str = (
            f"SELECT scope_id, node_name, COUNT(*) AS metric_count FROM {m} WHERE group_id = %s "
            "GROUP BY scope_id, node_name ORDER BY scope_id, node_name LIMIT %s, 50"
        )
        explain(Query("Q2-GC", "生成列索引 GROUP BY 节点首页（XL）", gc_nodes, (xl, 0)))
        explain(Query("Q2-GC-deep", "生成列索引 GROUP BY 节点 OFFSET 10000（XL）", gc_nodes, (xl, 10_000)))
        explain(
            Query(
                "Q2-GC-step2",
                "生成列索引第 2 步：(scope_id, node_name) IN 50 个节点",
                f"SELECT field_id, field_name, scope_id, node_name FROM {m} WHERE group_id = %s "
                f"AND (scope_id, node_name) IN ({pair_sql}) ORDER BY scope_id, node_name, field_name",
                (xl, *pair_params),
            )
        )
        triple_sql: str = ", ".join(["(%s, %s, %s)"] * len(node_pairs))
        triple_params: list[Any] = [v for scope, node in node_pairs for v in (xl, scope, node)]
        explain(
            Query(
                "Q2-GC-step2b",
                "生成列索引第 2 步：(group_id, scope_id, node_name) IN 50 个节点（group_id 放进行构造器）",
                f"SELECT field_id, field_name, scope_id, node_name FROM {m} "
                f"WHERE (group_id, scope_id, node_name) IN ({triple_sql}) ORDER BY scope_id, node_name, field_name",
                triple_params,
            )
        )

    out("### Q3 标签倒排 → 范围 → 成员 → 指标项")
    q3_x1: str = (
        f"SELECT m.field_id, m.field_name, m.original_name, s.scope_name FROM report_scope_label l "
        "JOIN report_member rm ON rm.group_id = l.group_id AND rm.report_scope_id = l.report_scope_id "
        f"JOIN {m} m ON m.field_id = rm.ref_id LEFT JOIN metadata_timeseriesscope s ON s.id = m.scope_id "
        "WHERE l.group_id = %s AND l.label_key = %s AND l.label_value = %s"
    )
    q3_x3: str = (
        "SELECT m.field_id, m.field_name, x.original_name, s.scope_name FROM report_scope_label l "
        "JOIN report_member rm ON rm.group_id = l.group_id AND rm.report_scope_id = l.report_scope_id "
        "JOIN metric_meta_x3 x ON x.id = rm.ref_id "
        f"JOIN {m} m ON m.group_id = x.group_id AND m.field_scope = 'default' AND m.field_name = x.field_name "
        "LEFT JOIN metadata_timeseriesscope s ON s.id = m.scope_id "
        "WHERE l.group_id = %s AND l.label_key = %s AND l.label_value = %s"
    )
    q3_x3_trap: str = q3_x3.replace("AND m.field_scope = 'default' ", "")
    explain(
        Query("Q3-X1", "X1/X2：service_name 倒排取该服务全部指标（XL）", q3_x1, (xl, "service_name", data.xl_service))
    )
    explain(Query("Q3-X1-s", "同上（普通分组）", q3_x1, (sg, "service_name", data.sample_service)))
    explain(
        Query(
            "Q3-X3",
            "X3：成员 → 定义 → 指标项按 (group_id, field_scope, field_name) 唯一键回表（XL）",
            q3_x3,
            (xl, "service_name", data.xl_service),
        )
    )
    explain(
        Query(
            "Q3-X3-trap",
            "X3：回表条件漏写 field_scope（XL）",
            q3_x3_trap,
            (xl, "service_name", data.xl_service),
            runs=3,
        )
    )
    explain(
        Query(
            "Q3-2L",
            "两个标签求交：service_name AND scope_name → 成员 ref_id（XL）",
            "SELECT DISTINCT rm.ref_id FROM report_scope_label l1 "
            "JOIN report_scope_label l2 ON l2.group_id = l1.group_id AND l2.report_scope_id = l1.report_scope_id "
            "AND l2.label_key = %s AND l2.label_value = %s "
            "JOIN report_member rm ON rm.group_id = l1.group_id AND rm.report_scope_id = l1.report_scope_id "
            "WHERE l1.group_id = %s AND l1.label_key = %s AND l1.label_value = %s",
            ("scope_name", data.xl_scope_name, xl, "service_name", data.xl_service),
        )
    )
    explain(
        Query(
            "Q3-CS",
            "字符集混用：utf8 的 scope_name = utf8mb4 的 label_value 关联（XL）",
            "SELECT s.id, l.report_scope_id FROM report_scope_label l JOIN metadata_timeseriesscope s "
            "ON s.group_id = l.group_id AND s.scope_name = l.label_value WHERE l.group_id = %s AND l.label_key = %s",
            (xl, "service_name"),
        )
    )
    explain(
        Query(
            "Q3-CS-fix",
            "同上，label_value 显式 CONVERT(... USING utf8) 后关联",
            "SELECT s.id, l.report_scope_id FROM report_scope_label l JOIN metadata_timeseriesscope s "
            "ON s.group_id = l.group_id AND s.scope_name = CONVERT(l.label_value USING utf8) "
            "WHERE l.group_id = %s AND l.label_key = %s",
            (xl, "service_name"),
        )
    )

    hash_value: str = str(run(conn, "SELECT scope_hash FROM report_scope WHERE group_id = %s LIMIT 1", (xl,))[0][0])
    explain(
        Query(
            "Q3-HASH",
            "范围精确定位：ascii_bin 的 scope_hash = utf8mb4 连接传入的参数",
            "SELECT id, labels FROM report_scope WHERE group_id = %s AND scope_hash = %s",
            (xl, hash_value),
        )
    )

    out("### Q7 成员 (group, ref) → 范围 labels")
    ref_one: int = data.tuples[0][2]
    refs_50: list[int] = sorted({t[2] for t in data.tuples})[:50]
    explain(
        Query(
            "Q7a",
            "单个指标的上报范围（XL）",
            "SELECT rs.id, rs.labels FROM report_member rm JOIN report_scope rs ON rs.id = rm.report_scope_id "
            "WHERE rm.group_id = %s AND rm.ref_id = %s",
            (xl, ref_one),
        )
    )
    explain(
        Query(
            "Q7b",
            "一页 50 个指标的上报范围（XL）",
            "SELECT rm.ref_id, rs.id, rs.labels FROM report_member rm JOIN report_scope rs ON rs.id = rm.report_scope_id "
            f"WHERE rm.group_id = %s AND rm.ref_id IN ({', '.join(['%s'] * len(refs_50))})",
            (xl, *refs_50),
        )
    )

    out(f"### Q8 成员批量定位 {len(data.tuples)} 组 (group_id, report_scope_id, ref_id)")
    tuples: list[tuple[int, int, int]] = data.tuples
    cols: str = "SELECT id, report_scope_id, ref_id, last_seen FROM report_member"
    row_in: str = f"{cols} WHERE (group_id, report_scope_id, ref_id) IN ({', '.join(['(%s, %s, %s)'] * len(tuples))})"
    explain(Query("Q8a", "行构造 IN ((g, s, r), ...)", row_in, [v for t in tuples for v in t], runs=10))
    scope_ids: list[int] = sorted({t[1] for t in tuples})
    ref_ids: list[int] = sorted({t[2] for t in tuples})
    explain(
        Query(
            "Q8b",
            f"group_id = ? AND report_scope_id IN ({len(scope_ids)}) AND ref_id IN ({len(ref_ids)})（笛卡尔超集，需应用层再过滤）",
            f"{cols} WHERE group_id = %s AND report_scope_id IN ({', '.join(['%s'] * len(scope_ids))}) "
            f"AND ref_id IN ({', '.join(['%s'] * len(ref_ids))})",
            (xl, *scope_ids, *ref_ids),
            runs=5,
        )
    )
    by_scope: dict[int, list[int]] = {}
    t: tuple[int, int, int]
    for t in tuples:
        by_scope.setdefault(t[1], []).append(t[2])
    union_parts: list[str] = []
    union_params: list[Any] = []
    scope_id: int
    for scope_id, refs in sorted(by_scope.items()):
        union_parts.append(
            f"({cols} WHERE group_id = %s AND report_scope_id = %s AND ref_id IN ({', '.join(['%s'] * len(refs))}))"
        )
        union_params.extend([xl, scope_id, *refs])
    explain(
        Query("Q8c", f"按范围拆成 {len(by_scope)} 段 UNION ALL", " UNION ALL ".join(union_parts), union_params, runs=10)
    )
    or_sql: str = f"{cols} WHERE " + " OR ".join(
        ["(group_id = %s AND report_scope_id = %s AND ref_id = %s)"] * len(tuples)
    )
    explain(
        Query("Q8d", "OR 展开（Django 4.2 Q(...) | Q(...) 的形态）", or_sql, [v for t in tuples for v in t], runs=10)
    )
    one_scope: int = max(by_scope, key=lambda s: len(by_scope[s]))
    explain(
        Query(
            "Q8e",
            f"单范围 group_id = ? AND report_scope_id = ? AND ref_id IN ({len(by_scope[one_scope])})",
            f"{cols} WHERE group_id = %s AND report_scope_id = %s AND ref_id IN ({', '.join(['%s'] * len(by_scope[one_scope]))})",
            (xl, one_scope, *by_scope[one_scope]),
        )
    )
    RESULT["plans"] = plans
    conn.close()

    section_delete(server)
    section_upsert(server, data)
    out()


def section_delete(server: Server) -> None:
    out("### Q9 DELETE ... WHERE group_id = ? AND last_seen < ? LIMIT 1000（XL，事务内执行后回滚）")
    sql: str = "DELETE FROM report_member WHERE group_id = %s AND last_seen < %s LIMIT 1000"
    params: tuple[Any, ...] = (XL_GROUP, EXPIRE_BEFORE)
    results: list[dict[str, Any]] = []
    conn: pymysql.Connection = server.connect()
    expired: int = int(
        run(conn, "SELECT COUNT(*) FROM report_member WHERE group_id = %s AND last_seen < %s", params)[0][0]
    )
    total: int = int(run(conn, "SELECT COUNT(*) FROM report_member WHERE group_id = %s", (XL_GROUP,))[0][0])
    out(f"XL 分组成员 {total:,} 行，其中过期 {expired:,} 行")
    conn.close()

    def measure(index_label: str) -> None:
        isolation: str
        for isolation in ("REPEATABLE READ", "READ COMMITTED"):
            conn: pymysql.Connection = server.connect(autocommit=False)
            run(conn, f"SET SESSION TRANSACTION ISOLATION LEVEL {isolation}")
            plan: list[dict[str, Any]] = run_dict(conn, "EXPLAIN " + sql, params)
            conn.rollback()
            timings: list[float] = []
            locked: int = 0
            deleted: int = 0
            reads: int = 0
            _: int
            for _ in range(3):
                run(conn, "FLUSH STATUS")
                start: float = time.perf_counter()
                with conn.cursor() as cur:
                    deleted = cur.execute(sql, params)
                timings.append((time.perf_counter() - start) * 1000)
                time.sleep(0.15)  # INNODB_TRX 的数据最多每 0.1 s 刷新一次
                trx: tuple[Any, ...] = run(
                    conn,
                    "SELECT trx_rows_locked, trx_lock_structs FROM information_schema.INNODB_TRX "
                    "WHERE trx_mysql_thread_id = CONNECTION_ID()",
                )
                locked = int(trx[0][0]) if trx else -1
                status: dict[str, int] = {str(k): int(v) for k, v in run(conn, STATUS_SQL)}
                reads = sum(v for k, v in status.items() if k.startswith("Handler_read"))
                conn.rollback()
            conn.close()
            entry: dict[str, Any] = {
                "index": index_label,
                "isolation": isolation,
                "summary": plan_signature(plan),
                "flags": plan_flags(plan),
                "deleted": deleted,
                "median_ms": round(statistics.median(timings), 1),
                "rows_locked": locked,
                "handler_reads": reads,
            }
            results.append(entry)
            out(
                f"[Q9 {index_label} {isolation}] plan: {' ｜ '.join(entry['summary'])}；删除 {deleted} 行 "
                f"median {entry['median_ms']} ms；trx_rows_locked {locked:,}；Handler_read 合计 {reads:,}"
            )

    measure("无 last_seen 索引")
    conn = server.connect()
    added: Outcome = attempt(
        conn,
        "ALTER TABLE report_member ADD KEY idx_group_last_seen (group_id, last_seen), ALGORITHM=INPLACE, LOCK=NONE",
    )
    out(f"ADD KEY idx_group_last_seen (group_id, last_seen): {added.brief()}")
    run(conn, "ANALYZE TABLE report_member")
    conn.close()
    measure("KEY(group_id, last_seen)")
    RESULT["q9"] = {"expired": expired, "total": total, "add_index": added.to_json(), "runs": results}


def auto_increment(conn: pymysql.Connection, table: str) -> int:
    try:
        run(conn, "SET SESSION information_schema_stats_expiry = 0")
    except pymysql.MySQLError:
        pass
    return int(
        run(
            conn,
            "SELECT AUTO_INCREMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (DB, table),
        )[0][0]
    )


def section_upsert(server: Server, data: PlanData) -> None:
    out(f"### 批量 upsert {UPSERT_BATCH} 行（report_member，XL 分组，事务内执行后回滚）")
    existing: list[tuple[int, int, int]] = data.tuples[:UPSERT_BATCH]
    fresh: list[tuple[int, int, int]] = [(XL_GROUP, existing[i][1], 90_000_000 + i) for i in range(UPSERT_BATCH)]
    batches: dict[str, list[tuple[int, int, int]]] = {
        "全部已存在": existing,
        "半数新增": existing[: UPSERT_BATCH // 2] + fresh[: UPSERT_BATCH - UPSERT_BATCH // 2],
    }
    cols: str = "INSERT INTO report_member (group_id, report_scope_id, ref_id, last_seen, meta)"
    forms: dict[str, Callable[[int], str]] = {
        "U1 VALUES() 引用": lambda n: (
            f"{cols} VALUES {', '.join(['(%s, %s, %s, %s, %s)'] * n)} "
            "ON DUPLICATE KEY UPDATE last_seen = VALUES(last_seen), meta = VALUES(meta)"
        ),
        "U2 行别名 AS new（8.0.19+）": lambda n: (
            f"{cols} VALUES {', '.join(['(%s, %s, %s, %s, %s)'] * n)} AS new "
            "ON DUPLICATE KEY UPDATE last_seen = new.last_seen, meta = new.meta"
        ),
        "U3 派生表 INSERT ... SELECT": lambda n: (
            f"{cols} SELECT * FROM ("
            + " UNION ALL ".join(
                ["SELECT %s AS group_id, %s AS report_scope_id, %s AS ref_id, %s AS last_seen, %s AS meta"]
                + ["SELECT %s, %s, %s, %s, %s"] * (n - 1)
            )
            + ") AS new ON DUPLICATE KEY UPDATE last_seen = new.last_seen, meta = new.meta"
        ),
        "U4 VALUES() 条件更新": lambda n: (
            f"{cols} VALUES {', '.join(['(%s, %s, %s, %s, %s)'] * n)} "
            "ON DUPLICATE KEY UPDATE last_seen = GREATEST(last_seen, VALUES(last_seen)), "
            "meta = IF(VALUES(meta) <=> meta, meta, VALUES(meta))"
        ),
    }
    results: list[dict[str, Any]] = []
    conn: pymysql.Connection = server.connect(autocommit=False)
    form: str
    for form, build in forms.items():
        batch_name: str
        for batch_name, rows in batches.items():
            params: list[Any] = [v for g, s, r in rows for v in (g, s, r, "2026-10-11 01:00:00", None)]
            sql: str = build(len(rows))
            before: int = auto_increment(conn, "report_member")
            timings: list[float] = []
            outcome: Outcome = Outcome(False, 0.0)
            _: int
            for _ in range(3):
                outcome = attempt(conn, sql, params)
                conn.rollback()
                if not outcome.ok:
                    break
                timings.append(outcome.elapsed_ms)
            after: int = auto_increment(conn, "report_member")
            warning_codes: dict[int, int] = {}
            w: tuple[str, int, str]
            for w in outcome.warnings:
                warning_codes[w[1]] = warning_codes.get(w[1], 0) + 1
            entry: dict[str, Any] = {
                "form": form,
                "batch": batch_name,
                "ok": outcome.ok,
                "error": "" if outcome.ok else f"{outcome.code}: {outcome.message[:200]}",
                "affected": outcome.affected,
                "median_ms": round(statistics.median(timings), 1) if timings else None,
                "warnings": {str(k): v for k, v in warning_codes.items()},
                "warning_sample": outcome.warnings[0][2][:200] if outcome.warnings else "",
                "auto_increment_burn_per_batch": (after - before) // 3 if outcome.ok else 0,
            }
            results.append(entry)
            if outcome.ok:
                out(
                    f"[{form} / {batch_name}] OK median {entry['median_ms']} ms affected={outcome.affected}（FOUND_ROWS）"
                    f" 警告 {entry['warnings'] or '无'} {entry['warning_sample']}；每批消耗自增 ID {entry['auto_increment_burn_per_batch']}"
                )
            else:
                out(f"[{form} / {batch_name}] ERROR {entry['error']}")
    conn.close()
    RESULT["upsert"] = results


# ---------------------------------------------------------------- 4. 特性


@dataclass
class Feature:
    key: str
    title: str
    statements: list[str]
    check: str = ""
    cleanup: list[str] = field(default_factory=list)


def section_features(server: Server) -> None:
    out("## 0x04 5.7 可能缺失的特性")
    conn: pymysql.Connection = server.connect()
    m: str = "metadata_timeseriesmetric"
    features: list[Feature] = [
        Feature(
            "F1",
            "JSON 多值索引 CAST(... AS CHAR(64) ARRAY)",
            [
                "CREATE TABLE f_mvi (id int PRIMARY KEY, labels json, KEY idx ((CAST(labels->'$.svc' AS CHAR(64) ARRAY))))"
            ],
            cleanup=["DROP TABLE IF EXISTS f_mvi"],
        ),
        Feature(
            "F2",
            "JSON_TABLE",
            ["SELECT jt.k FROM JSON_TABLE('[\"a\", \"b\"]', '$[*]' COLUMNS (k varchar(64) PATH '$')) AS jt"],
        ),
        Feature(
            "F3",
            "窗口函数 ROW_NUMBER() OVER",
            [
                f"SELECT field_id, ROW_NUMBER() OVER (PARTITION BY scope_id ORDER BY field_name) AS rn FROM {m} WHERE group_id = 1 LIMIT 5"
            ],
        ),
        Feature("F4", "CTE WITH", ["WITH t AS (SELECT 1 AS x) SELECT x FROM t"]),
        Feature(
            "F5",
            "递归 CTE WITH RECURSIVE",
            ["WITH RECURSIVE t (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t WHERE n < 3) SELECT n FROM t"],
        ),
        Feature(
            "F6",
            "ALGORITHM=INSTANT（小表探测）",
            [
                "CREATE TABLE f_instant (id int PRIMARY KEY)",
                "ALTER TABLE f_instant ADD COLUMN c int NULL, ALGORITHM=INSTANT",
            ],
            cleanup=["DROP TABLE IF EXISTS f_instant"],
        ),
        Feature(
            "F7",
            "降序索引 KEY(group_id, last_seen DESC)",
            [
                "CREATE TABLE f_desc (id int PRIMARY KEY, group_id int, last_seen datetime(6), KEY idx (group_id, last_seen DESC))"
            ],
            check="SHOW CREATE TABLE f_desc",
            cleanup=["DROP TABLE IF EXISTS f_desc"],
        ),
        Feature(
            "F8",
            "函数索引 KEY((COALESCE(original_name, field_name)))",
            [
                (
                    "CREATE TABLE f_func (id int PRIMARY KEY, original_name varchar(255) COLLATE utf8_bin NULL, "
                    "field_name varchar(255) COLLATE utf8_bin NOT NULL, KEY idx ((COALESCE(original_name, field_name))))"
                )
            ],
            cleanup=["DROP TABLE IF EXISTS f_func"],
        ),
        Feature(
            "F9",
            "生成列 + 索引（F8 的 5.7 替代）",
            [
                (
                    "CREATE TABLE f_gc (id int PRIMARY KEY, original_name varchar(255) COLLATE utf8_bin NULL, "
                    "field_name varchar(255) COLLATE utf8_bin NOT NULL, node_name varchar(255) COLLATE utf8_bin "
                    "GENERATED ALWAYS AS (COALESCE(original_name, field_name)) VIRTUAL, KEY idx (node_name))"
                )
            ],
            cleanup=["DROP TABLE IF EXISTS f_gc"],
        ),
        Feature(
            "F10",
            "CHECK 约束（插入违反约束的行）",
            ["CREATE TABLE f_chk (a int, CHECK (a > 0))", "INSERT INTO f_chk VALUES (-1)"],
            check="SELECT COUNT(*) FROM f_chk",
            cleanup=["DROP TABLE IF EXISTS f_chk"],
        ),
        Feature(
            "F11",
            "INSERT ... VALUES (...) AS new ON DUPLICATE KEY UPDATE",
            [
                "CREATE TABLE f_alias (id int PRIMARY KEY, v int)",
                "INSERT INTO f_alias VALUES (1, 1) AS new ON DUPLICATE KEY UPDATE v = new.v",
            ],
            cleanup=["DROP TABLE IF EXISTS f_alias"],
        ),
        Feature(
            "F12",
            "VALUES() 引用（8.0.20+ 弃用）",
            [
                "CREATE TABLE f_values (id int PRIMARY KEY, v int)",
                "INSERT INTO f_values VALUES (1, 1) ON DUPLICATE KEY UPDATE v = VALUES(v)",
            ],
            cleanup=["DROP TABLE IF EXISTS f_values"],
        ),
        Feature(
            "F13",
            "SELECT ... FOR UPDATE SKIP LOCKED",
            ["SELECT id FROM report_member WHERE group_id = 1 LIMIT 1 FOR UPDATE SKIP LOCKED"],
        ),
        Feature(
            "F14",
            "SELECT ... FOR UPDATE NOWAIT",
            ["SELECT id FROM report_member WHERE group_id = 1 LIMIT 1 FOR UPDATE NOWAIT"],
        ),
        Feature(
            "F15",
            "LATERAL 派生表",
            [
                (
                    "SELECT s.id, x.c FROM metadata_timeseriesscope s, LATERAL "
                    f"(SELECT COUNT(*) AS c FROM {m} m WHERE m.scope_id = s.id) AS x WHERE s.group_id = 1 LIMIT 3"
                )
            ],
        ),
        Feature("F16", "JSON_VALUE()", ["SELECT JSON_VALUE('{\"a\": \"x\"}', '$.a')"]),
        Feature("F17", "MEMBER OF", ["SELECT 'x' MEMBER OF ('[\"x\", \"y\"]')"]),
        Feature("F18", "JSON_OVERLAPS()", ['SELECT JSON_OVERLAPS(\'["a"]\', \'["a", "b"]\')']),
        Feature(
            "F19",
            "JSON_CONTAINS / ->> / JSON_ARRAYAGG（5.7 替代手段）",
            [
                "SELECT JSON_CONTAINS(labels, '\"svc-007\"', '$.service_name'), labels->>'$.service_name' FROM report_scope LIMIT 1",
                "SELECT JSON_ARRAYAGG(id) FROM report_scope WHERE group_id = 1",
            ],
        ),
        Feature("F20", "REGEXP_LIKE()", ["SELECT REGEXP_LIKE('rpc_server', '^rpc_')"]),
        Feature("F21", "REGEXP 运算符（F20 的 5.7 替代）", ["SELECT 'rpc_server' REGEXP '^rpc_'"]),
        Feature(
            "F22",
            "utf8mb4_0900_ai_ci 排序规则（8.0 默认）",
            ["CREATE TABLE f_coll (c varchar(10) COLLATE utf8mb4_0900_ai_ci)"],
            cleanup=["DROP TABLE IF EXISTS f_coll"],
        ),
        Feature(
            "F23",
            "ALTER TABLE ... RENAME COLUMN",
            ["CREATE TABLE f_rename (id int PRIMARY KEY, a int)", "ALTER TABLE f_rename RENAME COLUMN a TO b"],
            cleanup=["DROP TABLE IF EXISTS f_rename"],
        ),
        Feature("F24", "EXPLAIN ANALYZE", ["EXPLAIN ANALYZE SELECT COUNT(*) FROM report_scope WHERE group_id = 1"]),
        Feature(
            "F25", "EXPLAIN FORMAT=TREE", ["EXPLAIN FORMAT=TREE SELECT COUNT(*) FROM report_scope WHERE group_id = 1"]
        ),
        Feature("F26", "VALUES ROW() 表值构造器", ["SELECT * FROM (VALUES ROW(1, 'a'), ROW(2, 'b')) AS t (id, name)"]),
        Feature(
            "F27",
            "INTERSECT（8.0.31+）",
            [
                "SELECT id FROM report_scope WHERE group_id = 1 INTERSECT SELECT report_scope_id FROM report_scope_label WHERE group_id = 1"
            ],
        ),
    ]
    results: list[dict[str, Any]] = []
    feature: Feature
    for feature in features:
        outcome: Outcome = Outcome(True, 0.0)
        statement: str
        for statement in feature.statements:
            outcome = attempt(conn, statement)
            if not outcome.ok:
                break
        checked: str = ""
        if outcome.ok and feature.check.startswith("SHOW CREATE TABLE"):
            ddl: str = str(run(conn, feature.check)[0][1])
            checked = "; ".join(line.strip() for line in ddl.splitlines() if line.strip().startswith("KEY"))
        elif outcome.ok and feature.check:
            checked = "; ".join(" ".join(str(v) for v in row) for row in run(conn, feature.check))
        for statement in feature.cleanup:
            attempt(conn, statement)
        result: str = outcome.brief(False)
        out(f"[{feature.key}] {feature.title}: {result}" + (f" ｜ 校验: {checked}" if checked else ""))
        results.append({"key": feature.key, "title": feature.title, "check": checked, **outcome.to_json()})
    RESULT["features"] = results
    conn.close()
    out()


# ---------------------------------------------------------------- diff


def brief_json(entry: dict[str, Any]) -> str:
    if entry.get("ok") is None:
        return str(entry.get("message", ""))
    if not entry.get("ok"):
        return f"ERROR {entry.get('code')}: {str(entry.get('message', ''))[:120]}"
    codes: list[str] = sorted({str(w[1]) for w in entry.get("warnings", []) if int(w[1]) != 1003})
    return "OK" + (f"（警告 {','.join(codes)}）" if codes else "")


def diff(paths: Sequence[str]) -> None:
    with open(paths[0], encoding="utf-8") as fp:
        left: dict[str, Any] = json.load(fp)
    with open(paths[1], encoding="utf-8") as fp:
        right: dict[str, Any] = json.load(fp)
    out(f"# 5.7 / 8.0 对比：{left['version']} vs {right['version']}")
    out()
    out("## 建表与特性")
    section: str
    for section in ("ddl", "features"):
        rights: dict[str, dict[str, Any]] = {e["key"]: e for e in right.get(section, [])}
        entry: dict[str, Any]
        for entry in left.get(section, []):
            other: dict[str, Any] = rights.get(entry["key"], {})
            out(f"[{entry['key']}] {entry['title']}: 5.7 {brief_json(entry)} ｜ 8.0 {brief_json(other)}")
    out()
    out("## 在线 DDL")
    online_right: dict[str, dict[str, Any]] = {e["key"]: e for e in right.get("online", [])}
    keys: list[str] = list(dict.fromkeys([e["key"] for e in left.get("online", [])] + list(online_right)))
    lefts: dict[str, dict[str, Any]] = {e["key"]: e for e in left.get("online", [])}
    key: str
    for key in keys:
        cells: list[str] = []
        case: dict[str, Any]
        for case in (lefts.get(key, {}), online_right.get(key, {})):
            if not case:
                cells.append("未执行")
                continue
            outcome: dict[str, Any] = case["outcomes"][-1] if case["outcomes"] else {}
            update: dict[str, Any] = case["workloads"].get("UPDATE last_modify_time", {})
            select: dict[str, Any] = case["workloads"].get("SELECT 分组首页", {})
            cells.append(
                f"{brief_json(outcome)} {case['elapsed_ms'] / 1000:.2f} s 重建={'是' if case['rebuilt'] else '否'} "
                f"MDL 等待采样={case['mdl_wait_samples']} UPDATE max={update.get('max')} ms SELECT max={select.get('max')} ms"
            )
        title: str = (lefts.get(key) or online_right.get(key) or {}).get("title", "")
        out(f"[{key}] {title}")
        out(f"  5.7: {cells[0]}")
        out(f"  8.0: {cells[1]}")
    out()
    out("## upsert")
    upsert_right: dict[tuple[str, str], dict[str, Any]] = {(e["form"], e["batch"]): e for e in right.get("upsert", [])}
    for entry in left.get("upsert", []):
        other = upsert_right.get((entry["form"], entry["batch"]), {})
        cells = []
        item: dict[str, Any]
        for item in (entry, other):
            if not item.get("ok"):
                cells.append(f"ERROR {item.get('error', '')[:80]}")
            else:
                cells.append(
                    f"OK {item['median_ms']} ms affected={item['affected']} 警告={item['warnings'] or '无'} "
                    f"自增消耗={item['auto_increment_burn_per_batch']}"
                )
        out(f"[{entry['form']} / {entry['batch']}] 5.7 {cells[0]} ｜ 8.0 {cells[1]}")
    out()
    out("## 执行计划")
    out("一致 = 各表的 type、key、是否 filesort、是否临时表相同（rows 估算与 key_len 不参与比较）")
    out()
    keys = list(dict.fromkeys([*left.get("plans", {}), *right.get("plans", {})]))
    for key in keys:
        a: dict[str, Any] = left.get("plans", {}).get(key, {})
        b: dict[str, Any] = right.get("plans", {}).get(key, {})
        if "explain" not in a and "explain" not in b:
            continue
        same: str = "一致" if a.get("flags") == b.get("flags") else "不同"
        out(f"[{key}] {a.get('title') or b.get('title')} → {same}")
        out(f"  5.7: {' ｜ '.join(a.get('summary', [])) or a.get('error', '')}")
        out(f"  8.0: {' ｜ '.join(b.get('summary', [])) or b.get('error', '')}")
        out(
            f"  耗时 median: {a.get('time_ms', {}).get('median', '-')} ms vs {b.get('time_ms', {}).get('median', '-')} ms；"
            f"Handler_read: {a.get('counters', {}).get('handler_reads', '-')} vs {b.get('counters', {}).get('handler_reads', '-')}"
        )
    out()
    out("[Q9]")
    run_a: dict[str, Any]
    for run_a, run_b in zip(left.get("q9", {}).get("runs", []), right.get("q9", {}).get("runs", []), strict=False):
        same = "一致" if run_a["flags"] == run_b["flags"] else "不同"
        out(f"  {run_a['index']} {run_a['isolation']} → {same}")
        out(f"    5.7: {' ｜ '.join(run_a['summary'])}；{run_a['median_ms']} ms，锁 {run_a['rows_locked']:,} 行")
        out(f"    8.0: {' ｜ '.join(run_b['summary'])}；{run_b['median_ms']} ms，锁 {run_b['rows_locked']:,} 行")


# ---------------------------------------------------------------- main


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    sub: argparse._SubParsersAction = parser.add_subparsers(dest="command", required=True)
    run_parser: argparse.ArgumentParser = sub.add_parser("run")
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, required=True)
    run_parser.add_argument("--json", required=True)
    run_parser.add_argument("--online-rows", type=int, default=1_000_000)
    run_parser.add_argument("--plan-scale", type=float, default=1.0)
    run_parser.add_argument("--sections", default="env,ddl,online,plans,features")
    diff_parser: argparse.ArgumentParser = sub.add_parser("diff")
    diff_parser.add_argument("paths", nargs=2)
    args: argparse.Namespace = parser.parse_args()
    if args.command == "diff":
        diff(args.paths)
        return
    server: Server = Server(args.host, args.port)
    sections: list[str] = args.sections.split(",")
    started: float = time.perf_counter()
    out(
        f"# MySQL 兼容性验证 {time.strftime('%Y-%m-%d %H:%M:%S')}，python {sys.version.split()[0]}，pymysql {importlib.metadata.version('pymysql')}"
    )
    out()
    if "env" in sections:
        section_env(server)
    if "ddl" in sections:
        section_ddl(server)
    if "online" in sections:
        section_online(server, args.online_rows)
    if "plans" in sections:
        section_plans(server, args.plan_scale)
    if "features" in sections:
        section_features(server)
    out(f"总耗时 {time.perf_counter() - started:.1f} s")
    with open(args.json, "w", encoding="utf-8") as fp:
        json.dump(RESULT, fp, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
