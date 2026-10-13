#!/usr/bin/env python3
"""终版关键语句与 D 修正后语句的执行计划。

5.7 上对已装载的场景库执行；8.0 上加 --create 建空表并造少量数据（统计信息不同，主要核对 DDL 可建、索引可选）。

运行：uv run --with 'pymysql==1.1.1' explain.py <database> <group_id> [--create]
"""

import sys

import common as C
import design_d as D
import design_f as F


def queries(db, g, n_in):
    """IN 列表优先取本组真实的 scope_hash、field_name 与 ID，不足时补占位值。"""
    hs = [h for (h,) in db.ex("SELECT scope_hash FROM f_scope WHERE group_id = %s LIMIT %s", (g, n_in))]
    fs = [f for (f,) in db.ex("SELECT DISTINCT field_name FROM f_value WHERE group_id = %s LIMIT %s", (g, n_in))]
    ids = [i for (i,) in db.ex("SELECT id FROM f_value WHERE group_id = %s LIMIT %s", (g, n_in))]
    sids = [i for (i,) in db.ex("SELECT id FROM f_scope WHERE group_id = %s LIMIT %s", (g, n_in))]
    hs += [f"{i:032x}" for i in range(n_in - len(hs))]
    fs += [f"f{i}" for i in range(n_in - len(fs))]
    ids += [10**9 + i for i in range(n_in - len(ids))]
    sids += [10**9 + i for i in range(n_in - len(sids))]
    ph = C.marks(n_in)
    return [
        ("F apply: scopes by hash IN", f"SELECT id, scope_hash, version, last_seen, report_value_ids FROM f_scope "
                                       f"WHERE group_id = %s AND scope_hash IN ({ph})", [g, *hs]),
        ("F apply: values by field IN", f"SELECT id, field_name, fingerprint FROM f_value WHERE group_id = %s "
                                        f"AND field_name IN ({ph})", [g, *fs]),
        ("F apply: lock scope", "SELECT version FROM f_scope WHERE id = %s FOR UPDATE", [1]),
        ("F apply: scope_count CASE", "UPDATE f_value SET scope_count = scope_count + CASE id WHEN 1 THEN 1 WHEN 2 THEN -1 "
                                      "ELSE 0 END WHERE id IN (1, 2)", []),
        ("F apply: last_seen only", f"UPDATE f_scope SET last_seen = NOW(6) WHERE id IN ({ph})", sids),
        ("F read: id, labels by group", "SELECT id, labels, last_seen FROM f_scope WHERE group_id = %s", [g]),
        ("F read: blobs by id IN", f"SELECT id, report_value_ids FROM f_scope WHERE id IN ({C.marks(3)})", [1, 2, 3]),
        ("F read: values by id IN", f"SELECT id, field_name, original_name, original_type, metric_type, meta FROM f_value "
                                    f"WHERE id IN ({ph})", ids),
        ("F read: overrides", "SELECT selector_hash, field_name, field_config, scope_id FROM f_override WHERE group_id = %s "
                              "AND selector_hash IN (%s, %s)", [g, "a" * 32, "b" * 32]),
        ("F read: prefetch", "SELECT id, field_name, original_name, original_type, metric_type, meta, scope_count FROM f_value "
                             "WHERE group_id = %s", [g]),
        ("F read: default scope", "SELECT report_value_ids FROM f_scope WHERE group_id = %s AND scope_hash = %s", [g, "a" * 32]),
        ("F read: by metric value", "SELECT id FROM f_value WHERE group_id = %s AND field_name = %s", [g, "x"]),
        ("F read: family", "SELECT field_name, metric_type FROM f_value WHERE group_id = %s AND original_name = %s", [g, "x"]),
        ("F expire: scopes", "SELECT id FROM f_scope WHERE group_id = %s AND last_seen < '2026-09-01'", [g]),
        ("F expire: values", "SELECT id FROM f_value WHERE group_id = %s AND scope_count = 0", [g]),
        ("D member row IN (200)", "SELECT id FROM d_member WHERE (group_id, report_scope_id, meta_id) IN ("
         + C.marks(200, 3) + ")", [x for i in range(200) for x in (g, i + 1, i + 1)]),
        ("D member row IN (201)", "SELECT id FROM d_member WHERE (group_id, report_scope_id, meta_id) IN ("
         + C.marks(201, 3) + ")", [x for i in range(201) for x in (g, i + 1, i + 1)]),
        ("D expire: scope segment", f"SELECT id, report_scope_id, meta_value_id FROM d_member WHERE group_id = %s "
                                    f"AND report_scope_id IN ({C.marks(20)}) AND last_seen < '2026-09-01'",
         [g, *range(1, 21)]),
    ]


def main():
    name, g = sys.argv[1], int(sys.argv[2])
    if "--create" in sys.argv:
        # 10 个数据源 × 1,000 个 scope × 2,000 个取值，每个 scope 引用 500 个取值；D 表每组 20,000 个成员
        db = C.setup_db(name, D.DDL + F.DDL)
        for gg in range(1, 11):
            for part in C.chunks(range(2000), 1000):
                db.ex("INSERT INTO f_value (group_id, field_name, fingerprint, original_name, original_type, metric_type, meta, "
                      "scope_count) VALUES " + C.marks(len(part), 8),
                      [x for i in part for x in (gg, f"f{i}", C.md5(f"{gg}{i}"), f"f{i}", "counter", "counter", "{}", 250)])
            base = (gg - 1) * 2000
            for part in C.chunks(range(1000), 200):
                db.ex("INSERT INTO f_scope (group_id, scope_hash, scope_type, labels, raw_scope, report_value_ids, value_count, "
                      "last_seen, version) VALUES " + C.marks(len(part), 9),
                      [x for i in part for x in (gg, C.md5(f"{gg}|{i}"), "APM", C.canon({"service_name": f"s{i}"}), "",
                                                F.encode(range(base + 1 + (i % 4) * 500, base + 1 + (i % 4) * 500 + 500)),
                                                500, C.T0, 0)])
            for part in C.chunks(range(20000), 2000):
                db.ex("INSERT INTO d_member (group_id, report_scope_id, meta_id, last_seen) VALUES " + C.marks(len(part), 4),
                      [x for i in part for x in (gg, i // 20 + 1, i % 20 + 1 + gg * 100, C.T0)])
        for t in ("f_scope", "f_value", "d_member"):
            db.ex(f"ANALYZE TABLE {t}")
    else:
        db = C.DB(name)
    ((ver,),) = db.ex("SELECT VERSION()")
    C.open_log(f"explain_{name}_{ver.split('-')[0]}")
    C.emit(f"# server {ver}, database {name}, group {g}")
    for t in ("f_value", "f_scope", "f_override"):
        ((_, ddl),) = db.ex(f"SHOW CREATE TABLE {t}")
        C.emit(f"-- {t}: created OK, row_format={db.ex('SELECT ROW_FORMAT FROM information_schema.tables WHERE table_schema = %s AND table_name = %s', (name, t))[0][0]}")
    for n_in in (200, 1000):
        C.emit(f"\n## IN list size {n_in}")
        for label, sql, args in queries(db, g, n_in):
            if n_in == 1000 and not label.startswith("F apply") and "id IN" not in label:
                continue
            try:
                rows = db.ex("EXPLAIN " + sql, args)
            except Exception as e:  # S3 库只有终版表
                C.emit(f"{label:<32} skipped: {e.args[0]}")
                continue
            cols = [d[0] for d in db.cur.description]
            for r in rows:
                d = dict(zip(cols, r))
                C.emit(f"{label:<32} type={d['type']} key={d['key']} key_len={d['key_len']} rows={d['rows']} "
                       f"extra={d['Extra']}")


if __name__ == "__main__":
    main()
