#!/usr/bin/env python3
"""终版 E 与基线 D 在同一 MySQL 实例、同一库内的对照压测（S1、S2、S3x）。

运行：uv run --with 'pymysql==1.1.1' bench.py s1|s2|s3x|s1tx|smoke
环境变量：MYSQL_HOST、MYSQL_PORT（默认 127.0.0.1:33341）
"""

from __future__ import annotations

import datetime as dt
import random
import sys
import time
from collections import Counter, defaultdict

import common as C
import design_d as D
import design_f as F
from common import T0, chunks, emit, pct

H = dt.timedelta(hours=1)


def run_apply(design, db, sc, recs, now, W, cache=None, tx="scope"):
    st = Counter()
    db.reset()
    s0 = db.status()
    t = time.perf_counter()
    lat = []
    for part in chunks(recs, W):
        t1 = time.perf_counter()
        if design == "D":
            D.apply(db, sc, part, now, st)
        else:
            F.apply(db, sc, part, now, st, cache, tx)
        lat.append(time.perf_counter() - t1)
    st["seconds"] = round(time.perf_counter() - t, 3)
    s1 = db.status()
    d = C.status_delta(s0, s1)
    st["db_seconds"] = round(db.t, 3)
    st["statements"] = db.n
    st["records"] = len(recs)
    st["batches"] = len(lat)
    st["batch_p50_ms"] = round(pct(lat, 0.5) * 1000, 2) if lat else 0
    st["innodb_rows_written"] = d["Innodb_rows_inserted"] + d["Innodb_rows_updated"] + d["Innodb_rows_deleted"]
    st["innodb_ins/upd/del"] = f'{d["Innodb_rows_inserted"]}/{d["Innodb_rows_updated"]}/{d["Innodb_rows_deleted"]}'
    st["redo_MiB"] = round(d["Innodb_os_log_written"] / 2**20, 2)
    st["commits"] = d["Com_commit"]
    st["stmt_rows_written"] = sum(v for k, v in st.items() if isinstance(v, int) and k.endswith((".ins", ".upd", ".del")))
    return st


def report(label, st):
    for k, v in list(st.items()):
        if isinstance(v, float):
            st[k] = round(v, 3)
    emit(f"{label:<52} {C.counter_fmt(st)}")
    C.RESULT[label] = dict(st)


def run_expire(design, db, sc, now, cache=None):
    st = Counter()
    db.reset()
    s0 = db.status()
    t = time.perf_counter()
    if design == "D":
        D.expire(db, sc, now, st)
    else:
        F.expire(db, sc, now, st, cache)
    st["seconds"] = round(time.perf_counter() - t, 3)
    d = C.status_delta(s0, db.status())
    st["statements"] = db.n
    st["innodb_rows_written"] = d["Innodb_rows_inserted"] + d["Innodb_rows_updated"] + d["Innodb_rows_deleted"]
    return st


def reads(db, sc, now, tag, light=(30, 300), heavy=(5, 30)):
    timing = defaultdict(list)
    rd = D.readers(db, sc, now, random.Random(7))
    rf = F.readers(db, sc, now, random.Random(7), timing)
    cases = [
        ("service view", "service_view", light),
        ("group prefetch", "prefetch", heavy),
        ("by metric -> all scopes (1 metric)", "by_metric", light),
        ("expire round, no-op", "expire_noop", light),
    ]
    emit(f"{'read case':<44}{'D p50':>10}{'D p95':>10}{'F p50':>10}{'F p95':>10}  warm/runs")
    for label, key, (w, r) in cases:
        dw, dr = ((1, 5) if key == "expire_noop" else (w, r))
        d50, d95 = C.timed(rd[key], dw, dr)
        if key == "service_view":
            timing.clear()
        f50, f95 = C.timed(rf[key], w, r)
        emit(f"{label:<44}{d50:>10.2f}{d95:>10.2f}{f50:>10.2f}{f95:>10.2f}  D {dw}/{dr} F {w}/{r}")
        C.RESULT[f"{tag} read: {label}"] = {"D_p50": round(d50, 3), "D_p95": round(d95, 3),
                                            "F_p50": round(f50, 3), "F_p95": round(f95, 3)}
        if key == "service_view":
            parts = {k: (round(pct(v[w:], 0.5), 3), round(pct(v[w:], 0.95), 3)) for k, v in timing.items()}
            emit(f"  F service view steps p50/p95 ms: {parts}")
            C.RESULT[f"{tag} read: service view F steps"] = parts
    best, conflicts = F.prefetch(db, sc.group_id, C.label_hash("DEFAULT", {}))
    emit(f"  F prefetch: fields={len(best):,} metric_type conflicts={conflicts:,}")
    C.RESULT[f"{tag} prefetch conflicts"] = conflicts


def check(label, d, f):
    emit(f"verify {label}: D={d}")
    emit(f"verify {label}: F={f}")
    C.RESULT[f"verify {label}"] = {"D": d, "F": f}


def flow(sc: C.Scenario, d_w1000=True):
    db = C.setup_db(sc.name, D.DDL + F.DDL)
    rng = random.Random(11)
    g = sc.group_id
    n_scope = len(sc.scopes)
    emit(f"# scenario {sc.name}: scopes={n_scope} values={len(sc.values):,} fields={len({v.field for v in sc.values}):,} "
         f"keys={len(sc.keys):,} kinds={dict(Counter(kv[1] for kv in sc.keys.values()))}")
    old, cur = C.cold_records(sc, rng)
    cache = F.FCache()

    emit("\n## (1) cold load, shuffled arrival, W=30000 for both")
    for design in ("D", "F"):
        tot = Counter()
        if old:
            st = run_apply(design, db, sc, old, T0 - dt.timedelta(days=40), 30000, cache)
            report(f"cold {design} expired-part (T0-40d)", st)
        st = run_apply(design, db, sc, cur, T0, 30000, cache)
        report(f"cold {design}", st)
    check("after cold", D.verify(db, sc, (0, 1, 2)), F.verify(db, sc, (0, 1, 2)))
    emit("\n## sizes after cold load")
    C.RESULT["sizes_cold"] = C.sizes(db, sc.name, ("d_", "f_"))

    emit("\n## (2) expire round at T0")
    report("expire#1 D", run_expire("D", db, sc, T0))
    report("expire#1 F", run_expire("F", db, sc, T0, cache))
    for kv in sc.keys.values():
        if kv[1] == 2:
            kv[1] = 9  # D 已按成员删除；终版的 scope 仍在上报其他指标，这些条目留在列表里
    check("after expire#1", D.verify(db, sc, (0, 1)), F.verify(db, sc, (0, 1, 9)))

    emit("\n## (3) reads at T0")
    reads(db, sc, T0, sc.name)

    emit("\n## (4) same-day 2h resend (non-sparse active keys)")
    recs = C.active_records(sc, rng, include_sparse=False)
    if d_w1000:
        report("same-day D W=1000 (T0+2h)", run_apply("D", db, sc, recs, T0 + 2 * H, 1000))
    report("same-day D W=30000 (T0+3h)", run_apply("D", db, sc, recs, T0 + 3 * H, 30000))
    report("same-day F W=30000 warm cache (T0+2h)", run_apply("F", db, sc, recs, T0 + 2 * H, 30000, cache))
    cache = F.FCache()
    report("same-day F W=30000 cold cache (T0+3h)", run_apply("F", db, sc, recs, T0 + 3 * H, 30000, cache))

    emit("\n## (5) events at T0+5h")
    t5 = T0 + 5 * H
    like = [kv[0] for (s, f), kv in sorted(sc.keys.items()) if s == 0 and kv[1] in (0, 1)]
    newsvc = []
    for k in range(5):
        s = sc.scope(f"svc-new{k}-{sc.name}", "http")
        pv = sc.value(f"new_private_{k}_total", f"new.private.{k}", "counter", C.base_meta("1", "private"))
        r = [(s, v) for v in like] + [(s, pv)]
        for _, v in r:
            sc.keys[(s, sc.values[v].field)] = [v, 0]
        newsvc.append(r)
    for design in ("D", "F"):
        lat, tot = [], Counter()
        for r in newsvc:
            st = run_apply(design, db, sc, r, t5, 30000, cache)
            lat.append(st["seconds"] * 1000)
            tot.update({k: v for k, v in st.items() if isinstance(v, (int, float)) and not k.startswith("batch")})
        tot["svc_p50_ms"] = round(pct(lat, 0.5), 2)
        tot["svc_max_ms"] = round(max(lat), 2)
        report(f"new service x5 ({len(newsvc[0])} recs each) {design}", tot)
    pool = sorted(k for k, kv in sc.keys.items() if kv[1] == 0 and k[0] < n_scope)
    evt = []
    for (s, f) in rng.sample(pool, 30):
        ov = sc.values[sc.keys[(s, f)][0]]
        meta = C.json.loads(ov.meta)
        meta["unit"] = "us"
        v = sc.value(f, ov.original, ov.otype, meta)
        sc.keys[(s, f)][0] = v
        evt.append([(s, v)])
    for design in ("D", "F"):
        lat, tot = [], Counter()
        for r in evt:
            st = run_apply(design, db, sc, r, t5, 30000, cache)
            lat.append(st["seconds"] * 1000)
            tot.update({k: v for k, v in st.items() if isinstance(v, (int, float)) and not k.startswith("batch")})
        tot["p50_ms"] = round(pct(lat, 0.5), 2)
        tot["p95_ms"] = round(pct(lat, 0.95), 2)
        report(f"(scope, metric) value change x30 {design}", tot)
    for k in rng.sample(sorted(k for k, kv in sc.keys.items() if kv[1] == 0 and k[0] < n_scope), 30):
        sc.keys[k][1] = 3  # 单个指标停报：D 30 d 后删成员，终版留在 scope 列表里
    for r in newsvc:
        for s, v in r:
            sc.keys[(s, sc.values[v].field)][1] = 8  # 整个 scope 停报：两边都要在 30 d 后删除

    emit("\n## (6) next-day first resend (all active incl. sparse)")
    recs = C.active_records(sc, rng, include_sparse=True)
    if d_w1000:
        report("next-day D W=1000 (T0+1d+1h)", run_apply("D", db, sc, recs, T0 + dt.timedelta(days=1) + H, 1000))
    report("next-day F W=30000 warm cache (T0+1d+1h)",
           run_apply("F", db, sc, recs, T0 + dt.timedelta(days=1) + H, 30000, cache))
    report("next-day D W=30000 (T0+2d+1h)", run_apply("D", db, sc, recs, T0 + dt.timedelta(days=2) + H, 30000))
    cache = F.FCache()
    report("next-day F W=30000 cold cache (T0+2d+1h)",
           run_apply("F", db, sc, recs, T0 + dt.timedelta(days=2) + H, 30000, cache))

    emit("\n## (7) resend at T0+31d, then expire: 5 stopped services and 30 stopped keys")
    t31 = T0 + dt.timedelta(days=31)
    report("resend D W=30000 (T0+31d)", run_apply("D", db, sc, recs, t31, 30000))
    report("resend F W=30000 warm cache (T0+31d)", run_apply("F", db, sc, recs, t31, 30000, cache))
    report("expire D (T0+31d+1h)", run_expire("D", db, sc, t31 + H))
    report("expire F (T0+31d+1h)", run_expire("F", db, sc, t31 + H, cache))
    check("after expire#2", D.verify(db, sc, (0, 1)), F.verify(db, sc, (0, 1, 3, 9)))
    stale = sum(1 for kv in sc.keys.values() if kv[1] in (3, 9))
    emit(f"F keeps stale entries of live scopes (D removed them): {stale:,}")
    C.RESULT["F stale entries kept"] = stale

    emit("\n## sizes at end")
    C.RESULT["sizes_end"] = C.sizes(db, sc.name, ("d_", "f_"))


def flow_tx(sc: C.Scenario):
    """S1 冷启动对照：批末逐 scope 事务（终版规定）与一批一个事务。"""
    for tx in ("scope", "batch"):
        name = f"{sc.name}tx{tx}"
        db = C.setup_db(name, F.DDL)
        rng = random.Random(11)
        _, cur = C.cold_records(sc, rng)
        report(f"cold F tx={tx}", run_apply("F", db, sc, cur, T0, 30000, F.FCache(), tx))
        C.DB().ex(f"DROP DATABASE {name}")


def main():
    which = sys.argv[1]
    C.open_log(which)
    v = C.DB().ex("SELECT VERSION()")[0][0]
    emit(f"# final bench {which} on {C.HOST}:{C.PORT} server {v}, started {time.strftime('%Y-%m-%d %H:%M:%S')}")
    t = time.perf_counter()
    if which == "s1":
        flow(C.gen_s1())
    elif which == "s2":
        flow(C.gen_s2())
    elif which == "s3x":
        flow(C.gen_s3x())
    elif which == "s1tx":
        flow_tx(C.gen_s1())
    elif which.startswith("smoke"):
        flow(C.gen_s1(11, 40, 150, "sm1"))
        flow(C.gen_s2(12, 60, 0.08, "sm2"))
        for n in ("sm1", "sm2"):
            C.DB().ex(f"DROP DATABASE {n}")
    emit(f"# done in {time.perf_counter() - t:.1f}s")
    C.dump_result(which)


if __name__ == "__main__":
    main()
