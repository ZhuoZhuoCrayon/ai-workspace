"""基线 D「元信息建表」：定义 + 例外取值 + 每「scope × 指标」一行成员。

写入沿用 pk5/p3 的实现（PLAN 旧版 0x04 b），并按 5.7 的三处 SQL 退化修正：
[a] 行构造 IN 一律按 200 组分段
[b] 过期扫描按 scope 分段走成员唯一键前缀，过滤放到服务端，不再用 (a > ? OR (a = ? AND b > ?)) 翻页
[c] 服务视图从 d_scope.labels 取 scope_name，不回连标签表
D 的 metric_type 存旧协议 __type（即拆分前类型），用于复现 pk5 的错误类型计数。
"""

from __future__ import annotations

import random
from collections import Counter

from common import DB, EXPIRE, RC, Scenario, chunks, marks

MEMBER_REFRESH_H = 24
SEEN_REFRESH_MIN = 30

DDL = [
    """CREATE TABLE d_meta (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  group_id INT NOT NULL,
  field_name VARCHAR(255) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  original_name VARCHAR(255) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  metric_type VARCHAR(16) NOT NULL,
  meta JSON NULL,
  fingerprint VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  seen_at DATETIME(6) NOT NULL,
  UNIQUE KEY uk_group_field (group_id, field_name),
  KEY tsmm_group_original_idx (group_id, original_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
    """CREATE TABLE d_value (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  group_id INT NOT NULL,
  fingerprint VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  meta JSON NULL,
  retired_at DATETIME(6) NULL,
  UNIQUE KEY uk_group_fp (group_id, fingerprint)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
    """CREATE TABLE d_scope (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  group_id INT NOT NULL,
  scope_hash VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  scope_type VARCHAR(32) NOT NULL,
  labels JSON NULL,
  raw_scope VARCHAR(512) NOT NULL,
  last_seen DATETIME(6) NOT NULL,
  UNIQUE KEY uk_group_hash (group_id, scope_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
    """CREATE TABLE d_scope_label (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  group_id INT NOT NULL,
  label_key VARCHAR(64) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  label_value VARCHAR(255) CHARACTER SET utf8 COLLATE utf8_bin NOT NULL,
  report_scope_id BIGINT NOT NULL,
  UNIQUE KEY uk_label (group_id, label_key, label_value, report_scope_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
    """CREATE TABLE d_member (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  group_id INT NOT NULL,
  report_scope_id BIGINT NOT NULL,
  meta_id BIGINT NOT NULL,
  last_seen DATETIME(6) NOT NULL,
  meta_value_id BIGINT NOT NULL DEFAULT 0,
  field_config JSON NULL,
  UNIQUE KEY uk_member (group_id, report_scope_id, meta_id),
  KEY tsrm_group_meta_idx (group_id, meta_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
]


def _member_refresh(now):
    import datetime as dt
    return now - dt.timedelta(hours=MEMBER_REFRESH_H)


def _seen_refresh(now):
    import datetime as dt
    return now - dt.timedelta(minutes=SEEN_REFRESH_MIN)


def apply(db: DB, sc: Scenario, recs, now, st: Counter, cache=None):
    g = sc.group_id
    dd = {}
    for s, v in recs:
        dd[(s, sc.values[v].field)] = (s, v)
    recs = list(dd.values())
    db.ex("BEGIN")
    hashes = sorted({sc.scopes[s].hash for s, _ in recs})
    by_hash = {sc.scopes[s].hash: sc.scopes[s] for s, _ in recs}
    sid = {}
    for part in chunks(hashes, RC):
        for i, h, ls in db.ex(
            f"SELECT id, scope_hash, last_seen FROM d_scope WHERE group_id = %s AND scope_hash IN ({marks(len(part))})",
            [g, *part],
        ):
            sid[h] = (i, ls)
    missing = [h for h in hashes if h not in sid]
    if missing:
        db.ex(
            "INSERT INTO d_scope (group_id, scope_hash, scope_type, labels, raw_scope, last_seen) VALUES "
            + marks(len(missing), 6),
            [x for h in missing for x in (g, h, by_hash[h].stype, by_hash[h].labels, by_hash[h].raw, now)],
        )
        st["d_scope.ins"] += db.rc
        for part in chunks(missing, RC):
            for i, h, ls in db.ex(
                f"SELECT id, scope_hash, last_seen FROM d_scope WHERE group_id = %s AND scope_hash IN ({marks(len(part))})",
                [g, *part],
            ):
                sid[h] = (i, ls)
        lab = []
        for h in missing:
            for k, v in sorted(by_hash[h].labels_d.items()):
                lab.append((g, k, v, sid[h][0]))
        if lab:
            db.ex(
                "INSERT INTO d_scope_label (group_id, label_key, label_value, report_scope_id) VALUES " + marks(len(lab), 4),
                [x for r in lab for x in r],
            )
            st["d_scope_label.ins"] += db.rc
    stale = sorted({i for i, ls in sid.values() if ls < _member_refresh(now)})
    for part in chunks(stale):
        db.ex(f"UPDATE d_scope SET last_seen = %s WHERE id IN ({marks(len(part))})", [now, *part])
        st["d_scope.upd"] += db.rc

    first = {}
    for s, v in recs:
        first.setdefault(sc.values[v].field, v)
    names = sorted(first)
    defs = {}
    for part in chunks(names, RC):
        for i, f, fp, seen in db.ex(
            f"SELECT id, field_name, fingerprint, seen_at FROM d_meta WHERE group_id = %s AND field_name IN ({marks(len(part))})",
            [g, *part],
        ):
            defs[f] = (i, fp, seen)
    missing = [f for f in names if f not in defs]
    for part in chunks(missing, RC):
        db.ex(
            "INSERT INTO d_meta (group_id, field_name, original_name, metric_type, meta, fingerprint, seen_at) VALUES "
            + marks(len(part), 7),
            [x for f in part for vv in (sc.values[first[f]],)
             for x in (g, f, vv.original, vv.otype, vv.meta, vv.fp_d, now)],
        )
        st["d_meta.ins"] += db.rc
        for i, f, fp, seen in db.ex(
            f"SELECT id, field_name, fingerprint, seen_at FROM d_meta WHERE group_id = %s AND field_name IN ({marks(len(part))})",
            [g, *part],
        ):
            defs[f] = (i, fp, seen)
    stale = sorted({defs[sc.values[v].field][0] for s, v in recs
                    if sc.values[v].fp_d == defs[sc.values[v].field][1]
                    and defs[sc.values[v].field][2] < _seen_refresh(now)})
    for part in chunks(stale):
        db.ex(f"UPDATE d_meta SET seen_at = %s WHERE id IN ({marks(len(part))})", [now, *part])
        st["d_meta.upd"] += db.rc

    wanted = {}
    for s, v in recs:
        vv = sc.values[v]
        if vv.fp_d != defs[vv.field][1]:
            wanted[vv.fp_d] = vv.meta
    vid = {}
    if wanted:
        fps = sorted(wanted)
        for part in chunks(fps, RC):
            for i, fp in db.ex(
                f"SELECT id, fingerprint FROM d_value WHERE group_id = %s AND fingerprint IN ({marks(len(part))}) FOR UPDATE",
                [g, *part],
            ):
                vid[fp] = i
        miss = [fp for fp in fps if fp not in vid]
        for part in chunks(miss, RC):
            db.ex("INSERT INTO d_value (group_id, fingerprint, meta) VALUES " + marks(len(part), 3),
                  [x for fp in part for x in (g, fp, wanted[fp])])
            st["d_value.ins"] += db.rc
            for i, fp in db.ex(
                f"SELECT id, fingerprint FROM d_value WHERE group_id = %s AND fingerprint IN ({marks(len(part))}) FOR UPDATE",
                [g, *part],
            ):
                vid[fp] = i

    want = {}
    for s, v in recs:
        vv = sc.values[v]
        mid, dfp, _ = defs[vv.field]
        want[(sid[sc.scopes[s].hash][0], mid)] = 0 if vv.fp_d == dfp else vid[vv.fp_d]
    keys = sorted(want)
    have = {}
    for part in chunks(keys, RC):
        for i, rs, mid, ls, mv in db.ex(
            "SELECT id, report_scope_id, meta_id, last_seen, meta_value_id FROM d_member "
            f"WHERE (group_id, report_scope_id, meta_id) IN ({marks(len(part), 3)})",
            [x for k in part for x in (g, *k)],
        ):
            have[(rs, mid)] = (i, ls, mv)
    ins, refresh, change = [], [], []
    for k in keys:
        h = have.get(k)
        if h is None:
            ins.append((g, k[0], k[1], now, want[k]))
        elif h[2] != want[k]:
            change.append((h[0], want[k]))
        elif h[1] < _member_refresh(now):
            refresh.append(h[0])
    for part in chunks(ins):
        db.ex("INSERT INTO d_member (group_id, report_scope_id, meta_id, last_seen, meta_value_id) VALUES "
              + marks(len(part), 5), [x for r in part for x in r])
        st["d_member.ins"] += db.rc
    for part in chunks(refresh):
        db.ex(f"UPDATE d_member SET last_seen = %s WHERE id IN ({marks(len(part))})", [now, *part])
        st["d_member.upd"] += db.rc
    for part in chunks(change):
        db.ex("UPDATE d_member SET last_seen = %s, meta_value_id = CASE id "
              + " ".join(["WHEN %s THEN %s"] * len(part)) + f" END WHERE id IN ({marks(len(part))})",
              [now, *[x for r in part for x in r], *[r[0] for r in part]])
        st["d_member.upd"] += db.rc
    db.ex("COMMIT")


SCOPE_SEG = 20  # 每段 20 个 scope，S1 约 40,000 个成员


def expire_scan(db: DB, g, cutoff):
    """按 scope 分段走 uk_member 前缀，服务端过滤 last_seen，返回过期成员 (id, report_scope_id, meta_value_id)。"""
    sids = [i for (i,) in db.ex("SELECT id FROM d_scope WHERE group_id = %s ORDER BY id", (g,))]
    out = []
    for part in chunks(sids, SCOPE_SEG):
        out += db.ex(
            "SELECT id, report_scope_id, meta_value_id FROM d_member "
            f"WHERE group_id = %s AND report_scope_id IN ({marks(len(part))}) AND last_seen < %s",
            [g, *part, cutoff])
    return out


def expire(db: DB, sc: Scenario, now, st: Counter):
    g = sc.group_id
    cutoff = now - EXPIRE
    rows = expire_scan(db, g, cutoff)
    st["d.expire_members"] += len(rows)
    for part in chunks([r[0] for r in rows]):
        db.ex(f"DELETE FROM d_member WHERE id IN ({marks(len(part))})", part)
        st["d_member.del"] += db.rc
    if rows:
        touched = sorted({r[1] for r in rows})
        for part in chunks(touched, RC):
            dead = [i for (i,) in db.ex(
                f"SELECT s.id FROM d_scope s WHERE s.group_id = %s AND s.id IN ({marks(len(part))}) AND NOT EXISTS "
                "(SELECT 1 FROM d_member m WHERE m.group_id = s.group_id AND m.report_scope_id = s.id)", [g, *part])]
            if dead:
                db.ex(f"DELETE FROM d_scope_label WHERE group_id = %s AND report_scope_id IN ({marks(len(dead))})", [g, *dead])
                db.ex(f"DELETE FROM d_scope WHERE id IN ({marks(len(dead))})", dead)
                st["d_scope.del"] += db.rc
        cand = sorted({r[2] for r in rows if r[2]})
        if cand:
            # meta_value_id 没有索引，只在本轮删过引用时扫一次本组成员
            alive = set()
            for part in chunks(cand):
                alive |= {i for (i,) in db.ex(
                    f"SELECT DISTINCT meta_value_id FROM d_member WHERE group_id = %s AND meta_value_id IN ({marks(len(part))})",
                    [g, *part])}
            dead = [i for i in cand if i not in alive]
            for part in chunks(dead):
                db.ex(f"DELETE FROM d_value WHERE id IN ({marks(len(part))})", part)
                st["d_value.del"] += db.rc


# ---------------------------------------------------------------- reads


def readers(db: DB, sc: Scenario, now, rng: random.Random):
    g = sc.group_id
    cutoff = now - EXPIRE
    services = sorted({s.service for s in sc.scopes if s.stype == "APM"})
    fields = sorted({v.field for v in sc.values})

    def service_view():
        svc = rng.choice(services)
        sids = [r[0] for r in db.ex(
            "SELECT report_scope_id FROM d_scope_label WHERE group_id = %s AND label_key = 'service_name' AND label_value = %s",
            (g, svc))]
        if not sids:
            return
        db.ex(f"SELECT id, labels FROM d_scope WHERE id IN ({marks(len(sids))})", sids)
        rows = db.ex(
            "SELECT mm.field_name, mm.original_name, mm.metric_type, mm.meta, mb.report_scope_id, mb.meta_value_id, mb.field_config "
            "FROM d_member mb JOIN d_meta mm ON mm.id = mb.meta_id "
            f"WHERE mb.group_id = %s AND mb.report_scope_id IN ({marks(len(sids))}) AND mb.last_seen >= %s",
            [g, *sids, cutoff])
        vids = sorted({r[5] for r in rows if r[5]})
        if vids:
            db.ex(f"SELECT id, meta FROM d_value WHERE id IN ({marks(len(vids))})", vids)

    def prefetch():
        db.ex("SELECT id, field_name, original_name, metric_type, meta FROM d_meta WHERE group_id = %s", (g,))

    def by_metric():
        f = rng.choice(fields)
        mids = [r[0] for r in db.ex("SELECT id FROM d_meta WHERE group_id = %s AND field_name = %s", (g, f))]
        if not mids:
            return
        sids = sorted({r[0] for r in db.ex(
            f"SELECT report_scope_id FROM d_member WHERE group_id = %s AND meta_id IN ({marks(len(mids))})", [g, *mids])})
        for part in chunks(sids):
            db.ex(f"SELECT id, labels FROM d_scope WHERE id IN ({marks(len(part))})", part)

    def expire_noop():
        expire_scan(db, g, cutoff)

    return {"service_view": service_view, "prefetch": prefetch, "by_metric": by_metric, "expire_noop": expire_noop}


def resolved(db: DB, sc: Scenario):
    """(scope_hash, field) -> (fp_f 推断, metric_type)：按 D 的读法还原每个成员读到的取值与类型。"""
    g = sc.group_id
    dval = dict(db.ex("SELECT id, fingerprint FROM d_value WHERE group_id = %s", (g,)))
    dscope = dict(db.ex("SELECT id, scope_hash FROM d_scope WHERE group_id = %s", (g,)))
    dmeta = {i: (f, fp, t) for i, f, fp, t in db.ex(
        "SELECT id, field_name, fingerprint, metric_type FROM d_meta WHERE group_id = %s", (g,))}
    out = {}
    for rs, mid, mv in db.ex("SELECT report_scope_id, meta_id, meta_value_id FROM d_member WHERE group_id = %s", (g,)):
        f, dfp, t = dmeta[mid]
        out[(dscope[rs], f)] = (dval[mv] if mv else dfp, t)
    return out


def verify(db: DB, sc: Scenario, kinds):
    want = {(sc.scopes[s].hash, f): sc.values[kv[0]] for (s, f), kv in sc.keys.items() if kv[1] in kinds}
    got = resolved(db, sc)
    meta_bad = type_bad = missing = 0
    for k, v in want.items():
        r = got.get(k)
        if r is None:
            missing += 1
            continue
        if r[0] != v.fp_d:
            meta_bad += 1
        if r[1] != v.otype:
            type_bad += 1
    extra = len(set(got) - set(want))
    return {"want": len(want), "rows": len(got), "missing": missing, "extra": extra,
            "meta_mismatch": meta_bad, "type_mismatch": type_bad}
