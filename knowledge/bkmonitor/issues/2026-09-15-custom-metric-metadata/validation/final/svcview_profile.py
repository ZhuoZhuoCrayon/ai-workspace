#!/usr/bin/env python3
"""服务视图耗时拆解：终版三步各自的服务端 + 传输耗时（不做类型转换）、pymysql 类型转换与 JSON 解析开销，对照 D。

运行：uv run --with 'pymysql==1.1.1' svcview_profile.py <database> <group_id>
"""

import json
import random
import sys
import time

import pymysql

import common as C
import design_f as F

WARM, RUNS = 30, 300


def raw(name):
    # 只保留参数编码器，去掉结果解码器（整数键），结果按原始字节串返回
    conv = {k: v for k, v in pymysql.converters.conversions.items() if not isinstance(k, int)}
    return pymysql.connect(host=C.HOST, port=C.PORT, user="root", password="", database=name, autocommit=True,
                           conv=conv, charset="utf8", max_allowed_packet=256 * 1024 * 1024).cursor()


def t(fn):
    p50, p95 = C.timed(fn, WARM, RUNS)
    return round(p50, 3), round(p95, 3)


def main():
    name, g = sys.argv[1], int(sys.argv[2])
    C.open_log(f"svcview_profile_{name}")
    cur = C.DB(name)
    rc = raw(name)
    rng = random.Random(7)
    svcs = sorted({json.loads(l).get("service_name") for (l,) in cur.ex("SELECT labels FROM f_scope WHERE group_id = %s", (g,))
                   if l and json.loads(l).get("service_name")})
    svc = svcs[len(svcs) // 2]
    rows = cur.ex("SELECT id, labels FROM f_scope WHERE group_id = %s", (g,))
    sids = [i for i, l in rows if json.loads(l).get("service_name") == svc]
    ((blob,),) = cur.ex("SELECT report_value_ids FROM f_scope WHERE id = %s", (sids[0],))
    ids = list(F.decode(blob))
    ph = C.marks(len(ids))
    q_labels = "SELECT id, labels, last_seen FROM f_scope WHERE group_id = %s"
    q_vals = f"SELECT id, field_name, original_name, original_type, metric_type, meta FROM f_value WHERE id IN ({ph})"
    q_vals_group = "SELECT id, field_name, original_name, original_type, metric_type, meta FROM f_value WHERE group_id = %s"
    labels_rows = cur.ex(q_labels, (g,))
    C.emit(f"# {name} group={g} scopes={len(labels_rows):,} service={svc} ids={len(ids):,}")
    res = {
        "F1 id,labels,last_seen scan (pymysql conv)": t(lambda: cur.ex(q_labels, (g,))),
        "F1 id,labels,last_seen scan (raw, no conv)": t(lambda: (rc.execute(q_labels, (g,)), rc.fetchall())),
        "F1 json.loads labels only (python)": t(lambda: [json.loads(l) for _, l, _ in labels_rows]),
        "F2 blob by id (conv)": t(lambda: cur.ex(f"SELECT id, report_value_ids FROM f_scope WHERE id IN ({C.marks(len(sids))})", sids)),
        "F3 values by id IN (conv)": t(lambda: cur.ex(q_vals, ids)),
        "F3 values by id IN (raw)": t(lambda: (rc.execute(q_vals, ids), rc.fetchall())),
        "F3 build+escape args only (python)": t(lambda: rc.mogrify(q_vals, ids)),
        "F3' values whole group (raw, compare)": t(lambda: (rc.execute(q_vals_group, (g,)), rc.fetchall())),
    }
    try:
        sid_d = [r[0] for r in cur.ex("SELECT report_scope_id FROM d_scope_label WHERE group_id = %s AND label_key = "
                                      "'service_name' AND label_value = %s", (g, svc))]
        q_d = ("SELECT mm.field_name, mm.original_name, mm.metric_type, mm.meta, mb.report_scope_id, mb.meta_value_id, "
               "mb.field_config FROM d_member mb JOIN d_meta mm ON mm.id = mb.meta_id WHERE mb.group_id = %s AND "
               f"mb.report_scope_id IN ({C.marks(len(sid_d))}) AND mb.last_seen >= %s")
        args_d = [g, *sid_d, C.T0 - C.EXPIRE]
        res["D label lookup (conv)"] = t(lambda: cur.ex(
            "SELECT report_scope_id FROM d_scope_label WHERE group_id = %s AND label_key = 'service_name' AND label_value = %s",
            (g, svc)))
        res["D member join (conv)"] = t(lambda: cur.ex(q_d, args_d))
        res["D member join (raw)"] = t(lambda: (rc.execute(q_d, args_d), rc.fetchall()))
    except pymysql.MySQLError as e:
        C.emit(f"D tables not available: {e}")
    for k, v in res.items():
        C.emit(f"{k:<46} p50={v[0]:>8.3f} ms p95={v[1]:>8.3f} ms")
    C.RESULT.update({k: {"p50": v[0], "p95": v[1]} for k, v in res.items()})
    C.dump_result(f"svcview_profile_{name}")


if __name__ == "__main__":
    main()
