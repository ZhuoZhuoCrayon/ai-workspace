"""终版 E「取值去重」：TimeSeriesReportValue + TimeSeriesReportScope（无标签表），另有 TimeSeriesMetricOverride。

DDL 与 Django 4.2.27 生成结果一致（见 results/django_ddl_57.sql），只把三条建索引语句并入 CREATE TABLE，
并显式写出表字符集 utf8（与 bk-monitor 库默认字符集一致）。表名缩短为 f_value、f_scope、f_override。
"""

from __future__ import annotations

import array
import datetime as dt
import json
import random
from collections import Counter, defaultdict

from common import DAY, DB, EXPIRE, Scenario, chunks, label_hash, marks

MAX_SCOPES = 2000
MAX_VALUES = 60000
MAX_VALUE_ID = 2**32 - 1
IN_CHUNK = 500  # 单列 IN，避开行构造 IN；同样不超过 eq_range_index_dive_limit 的影响见 explain 输出

DDL = [
    """CREATE TABLE f_value (
  id bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  group_id integer NOT NULL,
  field_name varchar(255) COLLATE utf8_bin NOT NULL,
  fingerprint varchar(32) COLLATE ascii_bin NOT NULL,
  original_name varchar(255) COLLATE utf8_bin NOT NULL,
  original_type varchar(16) NOT NULL,
  metric_type varchar(16) NOT NULL,
  meta json NULL,
  scope_count integer NOT NULL,
  UNIQUE KEY f_value_group_field_fp_uniq (group_id, field_name, fingerprint),
  KEY tsrv_group_original_idx (group_id, original_name),
  KEY tsrv_group_count_idx (group_id, scope_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
    """CREATE TABLE f_scope (
  id bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  group_id integer NOT NULL,
  scope_hash varchar(32) COLLATE ascii_bin NOT NULL,
  scope_type varchar(32) NOT NULL,
  labels json NULL,
  raw_scope varchar(512) NOT NULL,
  report_value_ids mediumblob NOT NULL,
  value_count integer NOT NULL,
  last_seen datetime(6) NOT NULL,
  version integer NOT NULL,
  UNIQUE KEY f_scope_group_hash_uniq (group_id, scope_hash),
  KEY tsrs_group_seen_idx (group_id, last_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
    """CREATE TABLE f_override (
  id bigint AUTO_INCREMENT NOT NULL PRIMARY KEY,
  group_id integer NOT NULL,
  selector_hash varchar(32) COLLATE ascii_bin NOT NULL,
  selector json NULL,
  field_name varchar(255) COLLATE utf8_bin NOT NULL,
  field_config json NULL,
  scope_id integer NULL,
  UNIQUE KEY f_override_group_sel_field_uniq (group_id, selector_hash, field_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8""",
]


def encode(ids) -> bytes:
    """uint32 小端序、升序、每个 4 B、无表头。"""
    return array.array("I", sorted(ids)).tobytes()


def decode(blob: bytes) -> array.array:
    a = array.array("I")
    a.frombytes(blob)
    return a


class FScope:
    __slots__ = ("sid", "version", "by_field", "last_seen")

    def __init__(self, sid, version, by_field, last_seen):
        self.sid, self.version, self.by_field, self.last_seen = sid, version, by_field, last_seen


class FCache:
    """bmw 进程内缓存：每个 scope 的 version + 取值 ID 集合（按 field_name 索引），以及 (field_name, fingerprint) → 取值 ID。"""

    def __init__(self):
        self.sid_by_hash: dict[str, int] = {}
        self.scopes: dict[int, FScope] = {}
        self.vid: dict[tuple[str, str], int] = {}
        self.vfield: dict[int, str] = {}
        self.n_values = 0


def _load_values_by_id(db, cache: FCache, ids):
    miss = [i for i in ids if i not in cache.vfield]
    for part in chunks(miss, IN_CHUNK * 2):
        for i, f, fp in db.ex(f"SELECT id, field_name, fingerprint FROM f_value WHERE id IN ({marks(len(part))})", part):
            cache.vfield[i] = f
            cache.vid[(f, fp)] = i


def _scope_from_row(db, cache, sid, ver, last_seen, blob):
    ids = decode(blob)
    _load_values_by_id(db, cache, ids)
    return FScope(sid, ver, {cache.vfield[i]: i for i in ids}, last_seen)


def apply(db: DB, sc: Scenario, recs, now, st: Counter, cache: FCache, tx="scope"):
    """MetricMetaSvc.Apply()：按 0x02 e 的四种情况计算改动，批末对有变化的 scope 逐个事务提交。"""
    g = sc.group_id
    dd = {}
    for s, v in recs:
        dd[(s, sc.values[v].field)] = (s, v)
    by_scope: dict[str, list[int]] = defaultdict(list)
    obj = {}
    for (s, _), (_, v) in dd.items():
        h = sc.scopes[s].hash
        by_scope[h].append(v)
        obj[h] = sc.scopes[s]

    # 1. scope：缓存未命中时读库，仍不存在时插入
    unknown = sorted(h for h in by_scope if h not in cache.sid_by_hash)
    for part in chunks(unknown, IN_CHUNK):
        for sid, h, ver, ls, blob in db.ex(
            "SELECT id, scope_hash, version, last_seen, report_value_ids FROM f_scope "
            f"WHERE group_id = %s AND scope_hash IN ({marks(len(part))})", [g, *part]):
            cache.sid_by_hash[h] = sid
            cache.scopes[sid] = _scope_from_row(db, cache, sid, ver, ls, blob)
            st["f.scope_loaded"] += 1
    missing = [h for h in unknown if h not in cache.sid_by_hash]
    if missing:
        room = MAX_SCOPES - len(cache.scopes)
        if room < len(missing):
            st["f.scope_dropped"] += len(missing) - max(room, 0)
            for h in missing[max(room, 0):]:
                del by_scope[h]
            missing = missing[: max(room, 0)]
    for part in chunks(missing, IN_CHUNK):
        db.ex("INSERT INTO f_scope (group_id, scope_hash, scope_type, labels, raw_scope, report_value_ids, value_count, "
              "last_seen, version) VALUES " + marks(len(part), 9),
              [x for h in part for x in (g, h, obj[h].stype, obj[h].labels, obj[h].raw, b"", 0, now, 0)])
        st["f_scope.ins"] += db.rc
        for sid, h in db.ex(f"SELECT id, scope_hash FROM f_scope WHERE group_id = %s AND scope_hash IN ({marks(len(part))})",
                            [g, *part]):
            cache.sid_by_hash[h] = sid
            cache.scopes[sid] = FScope(sid, 0, {}, now)

    # 2. 取值：(field_name, fingerprint) 缓存未命中时按 field_name 读库，仍不存在时插入
    pairs = {(sc.values[v].field, sc.values[v].fp_f): v for vs in by_scope.values() for v in vs}
    need = sorted({f for (f, fp) in pairs if (f, fp) not in cache.vid})
    for part in chunks(need, IN_CHUNK):
        for i, f, fp in db.ex(
                f"SELECT id, field_name, fingerprint FROM f_value WHERE group_id = %s AND field_name IN ({marks(len(part))})",
                [g, *part]):
            cache.vid[(f, fp)] = i
            cache.vfield[i] = f
    newv = sorted(k for k in pairs if k not in cache.vid)
    if newv and cache.n_values == 0:
        ((cache.n_values,),) = db.ex("SELECT COUNT(*) FROM f_value WHERE group_id = %s", (g,))
    if len(newv) > MAX_VALUES - cache.n_values:
        keep = max(MAX_VALUES - cache.n_values, 0)
        st["f.value_dropped"] += len(newv) - keep
        newv = newv[:keep]
    for part in chunks(newv, IN_CHUNK):
        db.ex("INSERT INTO f_value (group_id, field_name, fingerprint, original_name, original_type, metric_type, meta, "
              "scope_count) VALUES " + marks(len(part), 8),
              [x for k in part for vv in (sc.values[pairs[k]],)
               for x in (g, vv.field, vv.fp_f, vv.original, vv.otype, vv.mtype, vv.meta, 0)])
        st["f_value.ins"] += db.rc
        cache.n_values += db.rc
        fs = sorted({f for f, _ in part})
        for i, f, fp in db.ex(
                f"SELECT id, field_name, fingerprint FROM f_value WHERE group_id = %s AND field_name IN ({marks(len(fs))})",
                [g, *fs]):
            if i > MAX_VALUE_ID:
                st["f.value_id_overflow"] += 1
                continue
            cache.vid[(f, fp)] = i
            cache.vfield[i] = f

    # 3. 计算每个 scope 的改动
    ops: dict[int, list[tuple[str, int]]] = {}
    refresh = []
    for h, vs in by_scope.items():
        sid = cache.sid_by_hash[h]
        cs = cache.scopes[sid]
        todo = []
        for v in vs:
            vv = sc.values[v]
            vid = cache.vid.get((vv.field, vv.fp_f))
            if vid is None:
                continue
            if cs.by_field.get(vv.field) != vid:
                todo.append((vv.field, vid))
        if todo:
            ops[sid] = todo
        elif now - cs.last_seen >= DAY:
            refresh.append(sid)

    # 4. 批末提交
    delta = Counter()
    if tx == "scope":
        for sid, todo in sorted(ops.items()):
            db.ex("BEGIN")
            ((ver,),) = db.ex("SELECT version FROM f_scope WHERE id = %s FOR UPDATE", (sid,))
            cs = cache.scopes[sid]
            if ver != cs.version:
                ((ver, ls, blob),) = db.ex("SELECT version, last_seen, report_value_ids FROM f_scope WHERE id = %s", (sid,))
                cs = cache.scopes[sid] = _scope_from_row(db, cache, sid, ver, ls, blob)
                st["f.version_replay"] += 1
            d = _replay(cs, todo)
            db.ex("UPDATE f_scope SET report_value_ids = %s, value_count = %s, version = version + 1, last_seen = %s "
                  "WHERE id = %s", (encode(cs.by_field.values()), len(cs.by_field), now, sid))
            st["f_scope.upd"] += db.rc
            db.ex("COMMIT")
            cs.version += 1
            cs.last_seen = now
            delta.update(d)
    else:
        db.ex("BEGIN")
        sids = sorted(ops)
        vers = {}
        for part in chunks(sids, IN_CHUNK * 2):
            vers.update(dict(db.ex(f"SELECT id, version FROM f_scope WHERE id IN ({marks(len(part))}) FOR UPDATE", part)))
        args = []
        for sid in sids:
            cs = cache.scopes[sid]
            if vers[sid] != cs.version:
                ((ver, ls, blob),) = db.ex("SELECT version, last_seen, report_value_ids FROM f_scope WHERE id = %s", (sid,))
                cs = cache.scopes[sid] = _scope_from_row(db, cache, sid, ver, ls, blob)
                st["f.version_replay"] += 1
            delta.update(_replay(cs, ops[sid]))
            args.append((encode(cs.by_field.values()), len(cs.by_field), now, sid))
        if args:
            db.many("UPDATE f_scope SET report_value_ids = %s, value_count = %s, version = version + 1, last_seen = %s "
                    "WHERE id = %s", args)
            st["f_scope.upd"] += len(args)
        db.ex("COMMIT")
        for sid in sids:
            cache.scopes[sid].version += 1
            cache.scopes[sid].last_seen = now
    touch = sorted(k for k, d in delta.items() if d)
    for part in chunks(touch):
        n = db.ex("UPDATE f_value SET scope_count = scope_count + CASE id " + " ".join(["WHEN %s THEN %s"] * len(part))
                  + f" ELSE 0 END WHERE id IN ({marks(len(part))})", [*[x for i in part for x in (i, delta[i])], *part])
        st["f_value.upd"] += db.rc
        if db.rc < len(part):
            st["f.value_missing"] += len(part) - db.rc
    for part in chunks(sorted(refresh)):
        db.ex(f"UPDATE f_scope SET last_seen = %s WHERE id IN ({marks(len(part))})", [now, *part])
        st["f_scope.upd"] += db.rc
        st["f.last_seen_only"] += db.rc
        for sid in part:
            cache.scopes[sid].last_seen = now


def _replay(cs: FScope, todo):
    d = Counter()
    for f, vid in todo:
        old = cs.by_field.get(f)
        if old == vid:
            continue
        if old is not None:
            d[old] -= 1
        d[vid] += 1
        cs.by_field[f] = vid
    return d


# ---------------------------------------------------------------- expire


def expire(db: DB, sc: Scenario, now, st: Counter, cache: FCache | None = None, seg=100):
    """MetricMetaSvc.Expire()：删 last_seen 过期的 scope 并回减 scope_count，再删 scope_count = 0 的取值。"""
    return expire_group(db, sc.group_id, now, st, cache, seg)


def expire_group(db: DB, g, now, st: Counter, cache: FCache | None = None, seg=100):
    cut = now - EXPIRE
    sids = [i for (i,) in db.ex("SELECT id FROM f_scope WHERE group_id = %s AND last_seen < %s", (g, cut))]
    for part in chunks(sids, seg):
        db.ex("BEGIN")
        rows = db.ex(f"SELECT id, last_seen, report_value_ids FROM f_scope WHERE id IN ({marks(len(part))}) FOR UPDATE", part)
        dec = Counter()
        dead = []
        for sid, ls, blob in rows:
            if ls >= cut:
                continue
            dead.append(sid)
            for i in decode(blob):
                dec[i] -= 1
        for p2 in chunks(sorted(dec)):
            db.ex("UPDATE f_value SET scope_count = scope_count + CASE id " + " ".join(["WHEN %s THEN %s"] * len(p2))
                  + f" ELSE 0 END WHERE id IN ({marks(len(p2))})", [*[x for i in p2 for x in (i, dec[i])], *p2])
            st["f_value.upd"] += db.rc
        if dead:
            db.ex(f"DELETE FROM f_scope WHERE id IN ({marks(len(dead))})", dead)
            st["f_scope.del"] += db.rc
        db.ex("COMMIT")
        if cache is not None:
            for sid in dead:
                cache.scopes.pop(sid, None)
            cache.sid_by_hash = {h: s for h, s in cache.sid_by_hash.items() if s in cache.scopes}
    vids = [i for (i,) in db.ex("SELECT id FROM f_value WHERE group_id = %s AND scope_count = 0", (g,))]
    for part in chunks(vids):
        db.ex(f"DELETE FROM f_value WHERE id IN ({marks(len(part))}) AND scope_count = 0", part)
        st["f_value.del"] += db.rc
    if cache is not None and vids:
        gone = set(vids)
        cache.vid = {k: i for k, i in cache.vid.items() if i not in gone}
        cache.n_values = 0
    return len(sids), len(vids)


def expire_noop(db: DB, g, now):
    cut = now - EXPIRE
    db.ex("SELECT id FROM f_scope WHERE group_id = %s AND last_seen < %s", (g, cut))
    db.ex("SELECT id FROM f_value WHERE group_id = %s AND scope_count = 0", (g,))


# ---------------------------------------------------------------- reads


def service_view(db: DB, g, svc, now, timing=None):
    """0x02 d 服务视图三步：全部 scope 的 id/labels → 命中 scope 的 report_value_ids → 按主键批量取取值；再取覆盖。"""
    import time
    t0 = time.perf_counter()
    cut = now - EXPIRE
    hit = []
    for sid, labels, ls in db.ex("SELECT id, labels, last_seen FROM f_scope WHERE group_id = %s", (g,)):
        lab = json.loads(labels) if labels else {}
        if lab.get("service_name") == svc and ls >= cut:
            hit.append((sid, lab, ls))
    t1 = time.perf_counter()
    if not hit:
        return {}
    ref = {}
    for sid, blob in db.ex(f"SELECT id, report_value_ids FROM f_scope WHERE id IN ({marks(len(hit))})", [h[0] for h in hit]):
        ref[sid] = decode(blob)
    t2 = time.perf_counter()
    vids = sorted({i for a in ref.values() for i in a})
    vals = {}
    for part in chunks(vids, 5000):
        for i, f, o, ot, mt, m in db.ex(
                "SELECT id, field_name, original_name, original_type, metric_type, meta FROM f_value "
                f"WHERE id IN ({marks(len(part))})", part):
            vals[i] = (f, o, ot, mt, m)
    t3 = time.perf_counter()
    sels = {label_hash("", {"service_name": svc})}
    for _, lab, _ in hit:
        sels.add(label_hash("", {"service_name": svc, "scope_name": lab.get("scope_name", "")}))
    db.ex(f"SELECT selector_hash, field_name, field_config, scope_id FROM f_override WHERE group_id = %s "
          f"AND selector_hash IN ({marks(len(sels))})", [g, *sorted(sels)])
    # 同一服务多个 scope 引用不同取值时取 last_seen 最近的 scope
    out = {}
    for sid, lab, ls in sorted(hit, key=lambda x: x[2]):
        for i in ref[sid]:
            out[vals[i][0]] = (i, sid, lab.get("scope_name"))
    t4 = time.perf_counter()
    if timing is not None:
        timing["labels"].append((t1 - t0) * 1000)
        timing["blobs"].append((t2 - t1) * 1000)
        timing["values"].append((t3 - t2) * 1000)
        timing["override+merge"].append((t4 - t3) * 1000)
    return out


def prefetch(db: DB, g, default_hash):
    """不分 scope 的有效上报取值：DEFAULT scope 引用的取值优先，否则 scope_count 最大，并列取 ID 小者；类型不止一种时标冲突。"""
    rows = db.ex("SELECT id, field_name, original_name, original_type, metric_type, meta, scope_count FROM f_value "
                 "WHERE group_id = %s", (g,))
    dflt = set()
    r = db.ex("SELECT report_value_ids FROM f_scope WHERE group_id = %s AND scope_hash = %s", (g, default_hash))
    if r:
        dflt = set(decode(r[0][0]))
    best, types = {}, defaultdict(set)
    for i, f, o, ot, mt, m, c in rows:
        types[f].add(mt)
        key = (1 if i in dflt else 0, c, -i)
        b = best.get(f)
        if b is None or key > b[0]:
            best[f] = (key, i, o, ot, mt, m)
    conflicts = sum(1 for s in types.values() if len(s) > 1)
    return best, conflicts


def by_metric(db: DB, g, field):
    """0x02 d 按指标取所有 scope：按 field_name 查取值 → 读全部 scope 的 report_value_ids 找含它们的行 → 读 labels。"""
    vids = sorted(i for (i,) in db.ex("SELECT id FROM f_value WHERE group_id = %s AND field_name = %s", (g, field)))
    if not vids:
        return []
    hit = []
    for sid, blob in db.ex("SELECT id, report_value_ids FROM f_scope WHERE group_id = %s", (g,)):
        a = decode(blob)
        s = set(a) if len(vids) > 4 else None
        for v in vids:
            if (v in s) if s is not None else _contains(a, v):
                hit.append(sid)
                break
    if hit:
        return db.ex(f"SELECT id, labels FROM f_scope WHERE id IN ({marks(len(hit))})", hit)
    return []


def _contains(a, v):
    import bisect
    p = bisect.bisect_left(a, v)
    return p < len(a) and a[p] == v


def readers(db: DB, sc: Scenario, now, rng: random.Random, timing=None):
    g = sc.group_id
    services = sorted({s.service for s in sc.scopes if s.stype == "APM"})
    fields = sorted({v.field for v in sc.values})
    dh = label_hash("DEFAULT", {})
    return {
        "service_view": lambda: service_view(db, g, rng.choice(services), now, timing),
        "prefetch": lambda: prefetch(db, g, dh),
        "by_metric": lambda: by_metric(db, g, rng.choice(fields)),
        "expire_noop": lambda: expire_noop(db, g, now),
    }


def verify(db: DB, sc: Scenario, kinds):
    """每个 (scope, 指标) 读到的取值必须与生成器期望一致；scope_count 必须等于实际引用数。"""
    g = sc.group_id
    want = {(sc.scopes[s].hash, f): sc.values[kv[0]] for (s, f), kv in sc.keys.items() if kv[1] in kinds}
    ev = {i: (f, fp, ot, mt) for i, f, fp, ot, mt in db.ex(
        "SELECT id, field_name, fingerprint, original_type, metric_type FROM f_value WHERE group_id = %s", (g,))}
    got, cnt, bad_order = {}, Counter(), 0
    for h, blob, n in db.ex("SELECT scope_hash, report_value_ids, value_count FROM f_scope WHERE group_id = %s", (g,)):
        a = decode(blob)
        if list(a) != sorted(set(a)) or len(a) != n:
            bad_order += 1
        for i in a:
            cnt[i] += 1
            got[(h, ev[i][0])] = ev[i]
    meta_bad = type_bad = missing = 0
    for k, v in want.items():
        r = got.get(k)
        if r is None:
            missing += 1
            continue
        if r[1] != v.fp_f:
            meta_bad += 1
        if r[2] != v.otype or r[3] != v.mtype:
            type_bad += 1
    count_bad = sum(1 for i, c in db.ex("SELECT id, scope_count FROM f_value WHERE group_id = %s", (g,)) if cnt[i] != c)
    extra = len(set(got) - set(want))
    return {"want": len(want), "rows": len(got), "missing": missing, "extra": extra, "meta_mismatch": meta_bad,
            "type_mismatch": type_bad, "scope_count_bad": count_bad, "blob_bad": bad_order}
