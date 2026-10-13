#!/usr/bin/env python3
"""S3 全平台上界：按 validation README 0x02 上界规模的五档分布直接批量装载终版表（不走 Apply），测体积与全平台过期一轮。

与 pk5/p3 的 S3 装载同一分布、同一随机种子：每个 scope 抽取「每源成员 / 每源服务」个指标，1% 指标多一种取值并被一半 scope 引用，
0.1% 的条目带一条按服务的覆盖。D 的体积引用 validation 实测 7,849 MiB，不在本脚本装载。

运行：uv run --with 'pymysql==1.1.1' s3_size.py
"""

import array
import datetime as dt
import json
import random
import time
from collections import Counter

import common as C
import design_f as F

# (档, 数据源数, 每源指标, 每源服务, 每源成员)
TIERS = [
    ("XL", 5, 20_000, 667, 1_000_000),
    ("L", 1_550, 221, 126, 19_966),
    ("M", 2_000, 145, 12, 1_409),
    ("S", 3_000, 83, 8, 436),
    ("micro", 167, 111, 2, 111),
]


def main():
    C.open_log("s3")
    db = C.setup_db("s3f", F.DDL)
    C.emit(f"# S3 final bulk load started {time.strftime('%Y-%m-%d %H:%M:%S')} server {db.ex('SELECT VERSION()')[0][0]}")
    rng = random.Random(3)
    meta = C.canon(C.base_meta("s", "x" * 30 + " handling latency"))
    alt = C.canon(C.base_meta("ms", "x" * 30 + " handling latency"))
    vid = sid = g = 0
    tot = Counter()
    t = time.perf_counter()
    for tier, nsrc, nmet, nsvc, nmem in TIERS:
        per = max(1, nmem // nsvc)
        for _ in range(nsrc):
            g += 1
            names = [f"galileo_{rng.choice(C.WORDS)}_{rng.choice(C.WORDS)}_{i:05d}_seconds_bucket" for i in range(nmet)]
            exc = set(rng.sample(range(nmet), max(1, nmet // 100)))
            prim, alt_of, vrows = [], {}, []
            for i, n in enumerate(names):
                vid += 1
                prim.append(vid)
                vrows.append([vid, g, n, C.md5(n + meta), n.replace("_", "."), "histogram", "counter", meta, 0])
                if i in exc:
                    vid += 1
                    alt_of[i] = vid
                    vrows.append([vid, g, n, C.md5(n + alt), n.replace("_", "."), "histogram", "counter", alt, 0])
            cnt = Counter()
            srows, orows = [], []
            for s in range(nsvc):
                sid += 1
                pick = rng.sample(range(nmet), min(per, nmet))
                ids = sorted(alt_of[i] if (i in alt_of and rng.random() < 0.5) else prim[i] for i in pick)
                cnt.update(ids)
                svc = f"svc-{s:04d}-galileo"
                labels = {"scope_name": "http", "service_name": svc}
                srows.append((sid, g, C.label_hash("APM", labels), "APM", C.canon(labels), svc + "-http",
                              array.array("I", ids).tobytes(), len(ids), C.T0, 0))
                sel = {"service_name": svc}
                for _ in range(sum(1 for _ in range(len(ids)) if rng.random() < 0.001)):
                    orows.append((g, C.label_hash("", sel), C.canon(sel), names[rng.choice(pick)], json.dumps({"unit": "ms"})))
                tot["entries"] += len(ids)
            for r in vrows:
                r[8] = cnt[r[0]]
            # 没有 scope 引用的取值在稳态下已被过期清理删除，不装载
            tot["unreferenced_values_skipped"] += sum(1 for r in vrows if r[8] == 0)
            vrows = [r for r in vrows if r[8] > 0]
            for part in C.chunks(vrows, 2000):
                db.ex("INSERT INTO f_value (id, group_id, field_name, fingerprint, original_name, original_type, metric_type, "
                      "meta, scope_count) VALUES " + C.marks(len(part), 9), [x for r in part for x in r])
            for part in C.chunks(srows, 500):
                db.ex("INSERT INTO f_scope (id, group_id, scope_hash, scope_type, labels, raw_scope, report_value_ids, "
                      "value_count, last_seen, version) VALUES " + C.marks(len(part), 10), [x for r in part for x in r])
            if orows:
                db.ex("INSERT IGNORE INTO f_override (group_id, selector_hash, selector, field_name, field_config) VALUES "
                      + C.marks(len(orows), 5), [x for r in orows for x in r])
            tot["values"] += len(vrows)
            tot["scopes"] += nsvc
            tot["overrides_attempted"] += len(orows)
        print(f"tier {tier} loaded, totals {dict(tot)}, {time.perf_counter() - t:.0f}s", flush=True)
    C.emit(f"loaded groups={g:,} {dict(tot)} in {time.perf_counter() - t:.0f}s")
    C.RESULT["load"] = dict(tot)
    C.RESULT["sizes"] = C.sizes(db, "s3f", ("f_",))

    now = C.T0 + dt.timedelta(hours=1)
    for r in range(3):
        t1 = time.perf_counter()
        for gg in range(1, g + 1):
            F.expire_noop(db, gg, now)
        s = time.perf_counter() - t1
        C.emit(f"expire round #{r + 1} over all {g:,} groups, no-op (2 index range queries per group): {s:.2f}s")
        C.RESULT.setdefault("expire_noop_s", []).append(round(s, 3))
    old = C.T0 - dt.timedelta(days=40)
    db.ex("UPDATE f_scope SET last_seen = %s WHERE id %% 100 = 0", (old,))
    ((n_old,),) = db.ex("SELECT COUNT(*) FROM f_scope WHERE last_seen < %s", (now - C.EXPIRE,))
    st = Counter()
    t1 = time.perf_counter()
    for gg in range(1, g + 1):
        F.expire_group(db, gg, now, st)
    s = time.perf_counter() - t1
    C.emit(f"expire round over all {g:,} groups with 1% scopes expired ({n_old:,}): {s:.2f}s {dict(st)}")
    C.RESULT["expire_with_deletes"] = {"seconds": round(s, 3), "expired_scopes": n_old, **st}
    C.dump_result("s3")


if __name__ == "__main__":
    main()
