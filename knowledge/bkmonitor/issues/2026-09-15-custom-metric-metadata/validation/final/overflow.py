#!/usr/bin/env python3
"""验证 (a)：SELECT id, labels FROM f_scope WHERE group_id = ? 是否读取 report_value_ids 的溢出页。

cold 模式必须在 mysqld 刚重启（缓冲池为空，且关闭了 buffer pool load）后立即运行：
先执行不带 BLOB 列的查询，统计物理读与缓冲池中该表各类页数；再执行带 BLOB 列的查询，看新增的页。
warm 模式对比两条语句的耗时与逻辑读（Innodb_buffer_pool_read_requests）。

运行：uv run --with 'pymysql==1.1.1' overflow.py cold|warm <database> <group_id>
"""

import sys
import time

import common as C

Q_NO = "SELECT id, labels FROM f_scope WHERE group_id = %s"
Q_WITH = "SELECT id, labels, report_value_ids FROM f_scope WHERE group_id = %s"


def census(db, space):
    rows = db.ex("SELECT PAGE_TYPE, IFNULL(INDEX_NAME, '-'), COUNT(*) FROM information_schema.INNODB_BUFFER_PAGE "
                 "WHERE SPACE = %s GROUP BY PAGE_TYPE, INDEX_NAME ORDER BY PAGE_TYPE, INDEX_NAME", (space,))
    return {f"{t}:{i}": n for t, i, n in rows}


def main():
    mode, name, g = sys.argv[1], sys.argv[2], int(sys.argv[3])
    C.open_log(f"overflow_{mode}_{name}")
    db = C.DB(name)
    ((space,),) = db.ex("SELECT SPACE FROM information_schema.INNODB_SYS_TABLES WHERE NAME = %s", (f"{name}/f_scope",))
    C.emit(f"# overflow {mode} {name} group={g} space={space} {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if mode == "cold":
        C.emit(f"buffer pool pages of f_scope before: {census(db, space)}")
        for label, q in (("without report_value_ids", Q_NO), ("with report_value_ids", Q_WITH)):
            s0 = db.status()
            t = time.perf_counter()
            rows = db.ex(q, (g,))
            ms = (time.perf_counter() - t) * 1000
            d = C.status_delta(s0, db.status())
            C.emit(f"{label:<28} rows={len(rows):,} {ms:.2f} ms Innodb_pages_read=+{d['Innodb_pages_read']:,} "
                   f"Innodb_buffer_pool_reads=+{d['Innodb_buffer_pool_reads']:,} "
                   f"read_requests=+{d['Innodb_buffer_pool_read_requests']:,}")
            C.emit(f"  buffer pool pages of f_scope after: {census(db, space)}")
            C.RESULT[f"cold {label}"] = {"ms": round(ms, 2), **d}
    else:
        for label, q in (("without report_value_ids", Q_NO), ("with report_value_ids", Q_WITH)):
            p50, p95 = C.timed(lambda: db.ex(q, (g,)), 30, 300)
            s0 = db.status()
            for _ in range(20):
                db.ex(q, (g,))
            d = C.status_delta(s0, db.status())
            C.emit(f"{label:<28} p50={p50:.2f} ms p95={p95:.2f} ms logical page reads per query="
                   f"{d['Innodb_buffer_pool_read_requests'] / 20:,.0f} physical={d['Innodb_pages_read']}")
            C.RESULT[f"warm {label}"] = {"p50": round(p50, 3), "p95": round(p95, 3),
                                         "read_requests_per_query": d["Innodb_buffer_pool_read_requests"] / 20}
        ((n, tot, big, mx),) = db.ex(
            "SELECT COUNT(*), SUM(LENGTH(report_value_ids)), SUM(LENGTH(report_value_ids) > 8000), MAX(LENGTH(report_value_ids)) "
            "FROM f_scope WHERE group_id = %s", (g,))
        C.emit(f"blob stats: scopes={n:,} total={int(tot or 0) / 2**20:.2f} MiB rows>8000B={int(big or 0):,} max={mx:,} B")
        C.RESULT["blob"] = {"scopes": n, "bytes": int(tot or 0), "over_8000": int(big or 0), "max": mx}
    C.dump_result(f"overflow_{mode}_{name}")


if __name__ == "__main__":
    main()
