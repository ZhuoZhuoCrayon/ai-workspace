#!/usr/bin/env python3
"""验证 (d)：TimeSeriesScope 加 selector / selector_hash 两列并把唯一键换成 (group_id, selector_hash, scope_name)。

建表与迁移语句取自 Django 4.2.27 生成结果（results/django_ddl_<tag>.sql），每条语句按 INSTANT → INPLACE/NONE →
INPLACE/SHARED → COPY 依次尝试，第一个被接受的就是 MySQL 默认会选的算法；以 TABLE_ID 是否变化判断是否重建表。
另测：长事务持有元数据锁时 DDL 与后续查询的排队、DDL 执行期间的并发 DML 延迟、迁移后旧代码写入是否报错。

运行：uv run --with 'pymysql==1.1.1' scope_ddl.py <tag>    # tag 用于输出文件名，如 57、80
"""

import itertools
import random
import sys
import threading
import time

import pymysql

import common as C

TABLE = "metadata_timeseriesscope"
CREATE = [
    f"CREATE TABLE `{TABLE}` (`id` integer AUTO_INCREMENT NOT NULL PRIMARY KEY, `group_id` integer NOT NULL, "
    "`scope_name` varchar(255) COLLATE `utf8_bin` NOT NULL, `dimension_config` json NOT NULL, `auto_rules` json NOT NULL, "
    "`create_from` varchar(10) NOT NULL, `last_modify_time` datetime(6) NOT NULL)",
    f"ALTER TABLE `{TABLE}` ADD CONSTRAINT `metadata_timeseriesscope_group_id_scope_name_47eede0c_uniq` UNIQUE (`group_id`, `scope_name`)",
    f"CREATE INDEX `metadata_timeseriesscope_group_id_88f6387c` ON `{TABLE}` (`group_id`)",
    f"CREATE INDEX `metadata_timeseriesscope_create_from_2981f159` ON `{TABLE}` (`create_from`)",
    f"ALTER TABLE `{TABLE}` ALTER COLUMN `create_from` SET DEFAULT 'data'",  # 0251 迁移里的 RunSQL
]
MIGRATION = [
    ("add selector", "ADD COLUMN `selector` json NULL"),
    ("add selector_hash", "ADD COLUMN `selector_hash` varchar(32) COLLATE `ascii_bin` DEFAULT '' NOT NULL"),
    ("drop default", "ALTER COLUMN `selector_hash` DROP DEFAULT"),
    ("drop old unique", "DROP INDEX `metadata_timeseriesscope_group_id_scope_name_47eede0c_uniq`"),
    ("add new unique", "ADD CONSTRAINT `metadata_timeseriesscope_group_id_selector_hash_s_feae1a29_uniq` "
                       "UNIQUE (`group_id`, `selector_hash`, `scope_name`)"),
]
COMBINED = ("ADD COLUMN `selector` json NULL, ADD COLUMN `selector_hash` varchar(32) COLLATE `ascii_bin` DEFAULT '' NOT NULL, "
            "DROP INDEX `metadata_timeseriesscope_group_id_scope_name_47eede0c_uniq`, "
            "ADD CONSTRAINT `metadata_timeseriesscope_group_id_selector_hash_s_feae1a29_uniq` "
            "UNIQUE (`group_id`, `selector_hash`, `scope_name`)")
SEQ = itertools.count()
TRIES = [("INSTANT", None), ("INPLACE", "NONE"), ("INPLACE", "SHARED"), ("COPY", "SHARED")]


def table_id(db, name, table=TABLE):
    if db.v57:
        r = db.ex("SELECT TABLE_ID FROM information_schema.INNODB_SYS_TABLES WHERE NAME = %s", (f"{name}/{table}",))
    else:
        r = db.ex("SELECT TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME = %s", (f"{name}/{table}",))
    return r[0][0]


def connect(name):
    db = C.DB(name)
    db.v57 = db.ex("SELECT VERSION()")[0][0].startswith("5.")
    return db


def load(db, n, table=TABLE):
    rng = random.Random(n)
    now = C.T0
    rows = []
    for i in range(n):
        rows.append((i // 100 + 1, f"{rng.choice(C.WORDS)}_{i % 100:03d}", "{}", "[]", "data", now))
        if len(rows) == 5000:
            db.ex(f"INSERT INTO `{table}` (group_id, scope_name, dimension_config, auto_rules, create_from, last_modify_time) "
                  "VALUES " + C.marks(len(rows), 6), [x for r in rows for x in r])
            rows = []
    if rows:
        db.ex(f"INSERT INTO `{table}` (group_id, scope_name, dimension_config, auto_rules, create_from, last_modify_time) "
              "VALUES " + C.marks(len(rows), 6), [x for r in rows for x in r])
    db.ex(f"ANALYZE TABLE `{table}`")


def run_alter(db, name, clause, table=TABLE):
    before = table_id(db, name, table)
    errs = []
    for algo, lock in TRIES:
        opt = f"ALGORITHM={algo}" + (f", LOCK={lock}" if lock else "")
        t = time.perf_counter()
        try:
            db.ex(f"ALTER TABLE `{table}` {clause}, {opt}")
        except pymysql.MySQLError as e:
            errs.append(f"{opt}: {e.args[0]}")
            continue
        s = time.perf_counter() - t
        after = table_id(db, name, table)
        return {"algorithm": opt, "seconds": round(s, 3), "rebuild": before != after, "rejected": errs}
    return {"algorithm": None, "rejected": errs}


def mdl_queue(name):
    """长事务持有共享元数据锁 → DDL 等待排他锁 → 之后到达的普通查询排在 DDL 后面。"""
    a, b, c, mon = connect(name), connect(name), connect(name), connect(name)
    a.ex("BEGIN")
    a.ex(f"SELECT id FROM `{TABLE}` LIMIT 1")
    res = {}

    def ddl():
        t = time.perf_counter()
        b.ex(f"ALTER TABLE `{TABLE}` ADD COLUMN `selector` json NULL")
        res["ddl_s"] = round(time.perf_counter() - t, 3)

    def query():
        t = time.perf_counter()
        c.ex(f"SELECT COUNT(*) FROM `{TABLE}` WHERE group_id = 5")
        res["query_s"] = round(time.perf_counter() - t, 3)

    tb = threading.Thread(target=ddl)
    tb.start()
    time.sleep(1)
    tc = threading.Thread(target=query)
    tc.start()
    time.sleep(2)
    res["states"] = sorted({s for (s,) in mon.ex(
        "SELECT state FROM information_schema.processlist WHERE info LIKE %s AND info NOT LIKE %s",
        (f"%{TABLE}%", "%processlist%")) if s})
    a.ex("COMMIT")
    tb.join()
    tc.join()
    res["note"] = "事务 A 在 t=0 持锁、t=3 s 提交；DDL t=0 发起，查询 t=1 s 发起"
    return res


def concurrent_dml(name, clause, stop_after=None):
    """DDL 执行期间另一个连接每 5 ms 做一次点查、点更新与插入，记录最大延迟与次数。"""
    d = connect(name)
    w = connect(name)
    stop = threading.Event()
    lat = []
    errors = {}
    ((mx,),) = w.ex(f"SELECT MAX(id) FROM `{TABLE}`")

    def worker():
        i = 0
        rng = random.Random(1)
        while not stop.is_set():
            t = time.perf_counter()
            k = rng.randint(1, mx)
            w.ex(f"SELECT id FROM `{TABLE}` WHERE id = %s", (k,))
            w.ex(f"UPDATE `{TABLE}` SET last_modify_time = NOW(6) WHERE id = %s", (k,))
            try:
                # 旧版本代码的写法：不带 selector / selector_hash
                w.ex(f"INSERT INTO `{TABLE}` (group_id, scope_name, dimension_config, auto_rules, create_from, last_modify_time) "
                     "VALUES (%s, %s, '{}', '[]', 'data', NOW(6))", (999999, f"dml_{next(SEQ)}"))
            except pymysql.MySQLError as e:
                errors[e.args[0]] = errors.get(e.args[0], 0) + 1
            lat.append((time.perf_counter() - t) * 1000)
            i += 1
            time.sleep(0.005)

    th = threading.Thread(target=worker)
    th.start()
    time.sleep(0.5)
    t = time.perf_counter()
    d.ex(f"ALTER TABLE `{TABLE}` {clause}")
    s = time.perf_counter() - t
    time.sleep(0.5)
    stop.set()
    th.join()
    return {"ddl_s": round(s, 3), "dml_rounds": len(lat), "dml_p50_ms": round(C.pct(lat, 0.5), 2),
            "dml_max_ms": round(max(lat), 2), "old_insert_errors": errors}


def old_code_insert(name):
    db = connect(name)
    ((mode,),) = db.ex("SELECT @@GLOBAL.sql_mode")
    out = {"global_sql_mode": mode}
    ins = (f"INSERT INTO `{TABLE}` (group_id, scope_name, dimension_config, auto_rules, create_from, last_modify_time) "
           "VALUES (%s, %s, '{}', '[]', 'data', NOW(6))")
    for label, sm in (("strict(default)", mode), ("non-strict", "")):
        db.ex("SET SESSION sql_mode = %s", (sm,))
        try:
            db.ex(ins, (888888, f"old_{label}"))
            ((h,),) = db.ex(f"SELECT selector_hash FROM `{TABLE}` WHERE group_id = 888888 AND scope_name = %s", (f"old_{label}",))
            out[label] = f"OK selector_hash={h!r}"
        except pymysql.MySQLError as e:
            out[label] = f"ERROR {e.args[0]}: {e.args[1]}"
    db.ex("SET SESSION sql_mode = %s", (mode,))
    t = time.perf_counter()
    db.ex(f"ALTER TABLE `{TABLE}` ALTER COLUMN `selector_hash` SET DEFAULT ''")
    out["set_default_s"] = round(time.perf_counter() - t, 3)
    try:
        db.ex(ins, (888888, "old_after_set_default"))
        out["strict after SET DEFAULT ''"] = "OK"
    except pymysql.MySQLError as e:
        out["strict after SET DEFAULT ''"] = f"ERROR {e.args[0]}"
    return out


def main():
    tag = sys.argv[1]
    sizes = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [10_000, 100_000, 1_000_000]
    C.open_log(f"scope_ddl_{tag}")
    root = connect(None)
    C.emit(f"# TimeSeriesScope DDL on {C.HOST}:{C.PORT} server {root.ex('SELECT VERSION()')[0][0]} "
           f"row_format={root.ex('SELECT @@innodb_default_row_format')[0][0]} {time.strftime('%Y-%m-%d %H:%M:%S')}")
    for n in sizes:
        name = f"scope_ddl_{n}"
        C.setup_db(name, CREATE)
        db = connect(name)
        t = time.perf_counter()
        load(db, n)
        db.ex(f"CREATE TABLE `{TABLE}_c` LIKE `{TABLE}`")
        db.ex(f"INSERT INTO `{TABLE}_c` SELECT * FROM `{TABLE}`")
        C.emit(f"\n## {n:,} rows (loaded in {time.perf_counter() - t:.1f}s)")
        total = 0.0
        res = []
        for label, clause in MIGRATION:
            r = run_alter(db, name, clause)
            total += r.get("seconds", 0)
            res.append((label, r))
            C.emit(f"{label:<20} {r}")
        C.emit(f"django sequence total {total:.3f}s")
        r = run_alter(db, name, COMBINED, f"{TABLE}_c")
        C.emit(f"{'combined one ALTER':<20} {r}")
        C.RESULT[f"{n}"] = {"steps": dict(res), "django_total_s": round(total, 3), "combined": r}
        db.ex(f"DROP TABLE `{TABLE}_c`")
        if n == 100_000:
            C.emit("\n### metadata lock queue (100,000 rows, fresh table)")
            C.setup_db(name + "m", CREATE)
            m = connect(name + "m")
            load(m, n)
            r = mdl_queue(name + "m")
            C.emit(f"{r}")
            C.RESULT["mdl_queue"] = r
            C.emit("\n### old code insert after migration (strict sql_mode)")
            r = old_code_insert(name)
            C.emit(f"{r}")
            C.RESULT["old_code_insert"] = r
            C.DB().ex(f"DROP DATABASE {name}m")
        if n == 1_000_000:
            C.emit("\n### concurrent DML during each step (1,000,000 rows, fresh table, worker every 5 ms)")
            C.setup_db(name + "c", CREATE)
            m = connect(name + "c")
            load(m, n)
            for label, clause in MIGRATION:
                r = concurrent_dml(name + "c", clause)
                C.emit(f"{label:<20} {r}")
                C.RESULT[f"dml during {label}"] = r
            C.DB().ex(f"DROP DATABASE {name}c")
        C.DB().ex(f"DROP DATABASE {name}")
    C.dump_result(f"scope_ddl_{tag}")


if __name__ == "__main__":
    main()
