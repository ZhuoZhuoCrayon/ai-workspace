"""终版复测公共部分：连接、场景生成、计时与体积统计。

场景生成沿用 pk5 压测的 S1、S2 生成器（同一随机种子），并按终版协议给每个取值补上 original_type。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter

import pymysql

HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
PORT = int(os.environ.get("MYSQL_PORT", "33341"))
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "results")
T0 = dt.datetime(2026, 10, 1, 12, 0, 0)
EXPIRE = dt.timedelta(days=30)
DAY = dt.timedelta(hours=24)
SCOPE_NAMES = ("http", "grpc", "custom", "default", "trpc")
WORDS = (
    "http", "rpc", "server", "client", "request", "handled", "queue", "pool", "conn", "cache",
    "db", "kafka", "redis", "goroutine", "gc", "memory", "cpu", "panic", "retry", "codec",
)
# 5.7 上行构造 IN 与长 IN 列表超过 eq_range_index_dive_limit（200）后改用索引统计估算
RC = 200

assert sys.byteorder == "little", "report_value_ids 按小端序编码，脚本直接用 array('I') 的本机字节序"

STATUS_KEYS = (
    "Innodb_rows_inserted", "Innodb_rows_updated", "Innodb_rows_deleted", "Innodb_rows_read",
    "Innodb_buffer_pool_read_requests", "Innodb_buffer_pool_reads", "Innodb_pages_read",
    "Innodb_data_written", "Innodb_os_log_written", "Com_commit",
)


def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def label_hash(scope_type: str, labels: dict) -> str:
    """scope_hash / selector_hash：键名升序拼 k:v，以 || 连接后取 MD5；scope_hash 额外带 scope_type 前缀。"""
    body = "||".join(f"{k}:{v}" for k, v in sorted(labels.items()))
    return md5(f"{scope_type}\x00{body}") if scope_type else md5(body)


def marks(n: int, width: int = 1) -> str:
    one = "%s" if width == 1 else "(" + ", ".join(["%s"] * width) + ")"
    return ", ".join([one] * n)


def chunks(xs, n=1000):
    xs = list(xs)
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def pct(xs, p):
    s = sorted(xs)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


# ---------------------------------------------------------------- data


def sub_type(field: str, original_type: str) -> str:
    """终版 __type：本条输出序列自身的类型。Histogram / Summary 的 _bucket、_sum、_count 是 counter。"""
    if original_type in ("histogram", "summary"):
        return "counter"
    return original_type


class Value:
    __slots__ = ("field", "original", "otype", "mtype", "meta", "fp_d", "fp_f")

    def __init__(self, field, original, otype, meta: dict):
        self.field, self.original, self.otype = field, original, otype
        self.mtype = sub_type(field, otype)
        self.meta = canon(meta)
        self.fp_d = md5(self.meta)  # D：指纹只算 meta，类型放在定义上
        self.fp_f = md5(canon({"m": meta, "n": original, "o": otype, "t": self.mtype}))  # 终版：覆盖全部字段


class Scope:
    __slots__ = ("service", "scope_name", "stype", "hash", "labels", "labels_d", "raw")

    def __init__(self, service, scope_name, stype="APM"):
        self.service, self.scope_name, self.stype = service, scope_name, stype
        labels = {"scope_name": scope_name, "service_name": service} if stype == "APM" else {}
        self.labels_d = labels
        self.labels = canon(labels)
        self.hash = label_hash(stype, labels)
        self.raw = service.replace("%", "%25").replace("-", "%2D") + "-" + scope_name.replace("-", "%2D") if labels else ""


class Scenario:
    def __init__(self, name, group_id):
        self.name, self.group_id = name, group_id
        self.scopes: list[Scope] = []
        self.values: list[Value] = []
        self.vindex: dict[tuple[str, str], int] = {}
        # (scope_idx, field) -> [value_idx, kind]；kind 0 常规 1 稀疏 2 已过期 3 停报 9 已被 D 删除
        self.keys: dict[tuple[int, str], list[int]] = {}

    def value(self, field, original, otype, meta) -> int:
        v = Value(field, original, otype, meta)
        k = (field, v.fp_f)
        if k not in self.vindex:
            self.vindex[k] = len(self.values)
            self.values.append(v)
        return self.vindex[k]

    def scope(self, service, scope_name, stype="APM") -> int:
        self.scopes.append(Scope(service, scope_name, stype))
        return len(self.scopes) - 1


def catalog(rng, n, prefix):
    out, i = [], 0
    while len(out) < n:
        base = f"{prefix}.{rng.choice(WORDS)}.{rng.choice(WORDS)}.{i:05d}"
        norm = base.replace(".", "_")
        r = rng.random()
        if r < 0.3:
            for suf in ("_bucket", "_count", "_sum"):
                out.append((norm + suf, base, "histogram", "s", f"{base} handling latency"))
        elif r < 0.65:
            out.append((norm + "_total", base, "counter", "1", f"{base} handled total"))
        else:
            out.append((norm, base, "gauge", "By", f"{base} current size"))
        i += 1
    return out[:n]


def base_meta(unit, desc):
    return {"description": desc, "interval": 60000, "temporality": "cumulative", "unit": unit, "usage": "sum"}


def gen_s1(group_id=1, n_svc=1000, n_met=2000, name="s1") -> Scenario:
    rng = random.Random(1)
    sc = Scenario(name, group_id)
    vids = [sc.value(f, o, t, base_meta(u, d)) for f, o, t, u, d in catalog(rng, n_met, "galileo")]
    for i in range(n_svc):
        s = sc.scope(f"svc-{i:04d}-galileo", rng.choice(SCOPE_NAMES))
        for v in vids:
            sc.keys[(s, sc.values[v].field)] = [v, 0]
    return sc


def s2_profile_values(sc, p, version, items):
    """画像 p 的版本 version：v>=1 时约 10% 指标换单位，v>=2 时约 5% 指标换类型。"""
    out = []
    for f, o, t, u, d in items:
        h = int(md5(f"{f}|{p}")[:8], 16)
        if version >= 1 and h % 10 == 0:
            u = {"s": "ms", "1": "{req}", "By": "KiBy"}[u]
        if version >= 2 and h % 20 == 1:
            t = {"counter": "gauge", "gauge": "counter", "histogram": "summary"}[t]
        out.append(sc.value(f, o, t, base_meta(u, d)))
    return out


def gen_s2(group_id=2, n_svc=1000, scale=1.0, name="s2", with_default=True) -> Scenario:
    rng = random.Random(2)
    sc = Scenario(name, group_id)
    shared = catalog(rng, int(1250 * scale), "galileo")
    profiles = []
    for p in range(5):
        n = int(rng.randint(1500, 2500) * scale)
        items = shared[: n // 2] + catalog(rng, n - n // 2, f"sdk{p}")
        nv = rng.randint(1, 3)
        profiles.append((items, [s2_profile_values(sc, p, v, items) for v in range(nv)]))
    for i in range(n_svc):
        p = rng.randrange(5)
        items, versions = profiles[p]
        vids = list(versions[rng.randrange(len(versions))])
        k = rng.randint(0, int(0.05 * len(items)))
        for f, o, t, u, d in catalog(rng, k, f"priv{i:04d}"):
            vids.append(sc.value(f, o, t, base_meta(u, d)))
        s = sc.scope(f"svc-{i:04d}-p{p}", rng.choice(SCOPE_NAMES))
        for v in vids:
            sc.keys[(s, sc.values[v].field)] = [v, 0]
    fields = sorted({v.field for v in sc.values})
    sparse = set(rng.sample(fields, len(fields) // 10))
    for key, kv in sc.keys.items():
        if key[1] in sparse:
            kv[1] = 1
    for key in rng.sample(sorted(sc.keys), len(sc.keys) // 50):
        sc.keys[key][1] = 2
    if with_default:
        # 终版新增：DEFAULT 上报也建一个 scope，这里让它上报画像 0 的最新版本，放在随机抽样之后，不影响 pk5 的数据画像
        items, versions = profiles[0]
        s = sc.scope("", "", "DEFAULT")
        for v in versions[-1]:
            sc.keys[(s, sc.values[v].field)] = [v, 0]
    return sc


def gen_s3x(group_id=3, n_svc=667, n_met=20000, per=1500, name="s3x") -> Scenario:
    """最大档单数据源：20,000 指标 × 667 服务，每服务约 1,500 指标，1% 指标多一种取值（单位不同），一半服务用它。"""
    rng = random.Random(5)
    sc = Scenario(name, group_id)
    items = catalog(rng, n_met, "galileo")
    prim = [sc.value(f, o, t, base_meta(u, d)) for f, o, t, u, d in items]
    alt = {}
    for i in rng.sample(range(n_met), n_met // 100):
        f, o, t, u, d = items[i]
        alt[i] = sc.value(f, o, t, base_meta({"s": "ms", "1": "{req}", "By": "KiBy"}[u], d))
    for i in range(n_svc):
        s = sc.scope(f"svc-{i:04d}-galileo", rng.choice(SCOPE_NAMES))
        for j in rng.sample(range(n_met), per):
            v = alt[j] if j in alt and rng.random() < 0.5 else prim[j]
            sc.keys[(s, sc.values[v].field)] = [v, 0]
    return sc


def cold_records(sc, rng):
    old = [(s, kv[0]) for (s, f), kv in sc.keys.items() if kv[1] == 2]
    cur = [(s, kv[0]) for (s, f), kv in sc.keys.items() if kv[1] != 2]
    rng.shuffle(old)
    rng.shuffle(cur)
    return old, cur


def active_records(sc, rng, include_sparse):
    recs = [(s, kv[0]) for (s, f), kv in sc.keys.items() if kv[1] == 0 or (include_sparse and kv[1] == 1)]
    rng.shuffle(recs)
    return recs


# ---------------------------------------------------------------- db


class DB:
    def __init__(self, database=None, host=HOST, port=PORT):
        self.conn = pymysql.connect(
            host=host, port=port, user="root", password="", database=database, autocommit=True,
            charset="utf8", max_allowed_packet=256 * 1024 * 1024,
        )
        self.cur = self.conn.cursor()
        self.t = 0.0
        self.n = 0
        self.rc = 0

    def ex(self, sql, args=None):
        t = time.perf_counter()
        self.rc = self.cur.execute(sql, args)
        rows = self.cur.fetchall()
        self.t += time.perf_counter() - t
        self.n += 1
        return rows

    def many(self, sql, args):
        t = time.perf_counter()
        self.rc = self.cur.executemany(sql, args)
        self.t += time.perf_counter() - t
        self.n += len(args)
        return self.rc

    def reset(self):
        self.t, self.n = 0.0, 0

    def status(self):
        rows = self.ex("SHOW GLOBAL STATUS WHERE Variable_name IN (" + marks(len(STATUS_KEYS)) + ")", STATUS_KEYS)
        return {k: int(v) for k, v in rows}


def status_delta(a, b):
    return {k: b[k] - a[k] for k in a}


def setup_db(name, ddl, **kw):
    root = DB(**kw)
    root.ex(f"DROP DATABASE IF EXISTS {name}")
    root.ex(f"CREATE DATABASE {name} DEFAULT CHARACTER SET utf8")
    db = DB(name, **kw)
    for s in ddl:
        db.ex(s)
    return db


# ---------------------------------------------------------------- output

LOG = None
RESULT: dict = {}


def open_log(name):
    global LOG
    os.makedirs(OUT, exist_ok=True)
    LOG = open(os.path.join(OUT, f"{name}.txt"), "w")


def emit(s=""):
    print(s, flush=True)
    if LOG is not None:
        LOG.write(s + "\n")
        LOG.flush()


def dump_result(name):
    with open(os.path.join(OUT, f"{name}.json"), "w") as f:
        json.dump(RESULT, f, indent=1, default=str, ensure_ascii=False)


def timed(fn, warm, runs):
    for _ in range(warm):
        fn()
    xs = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    return pct(xs, 0.5), pct(xs, 0.95)


def sizes(db: DB, dbname, prefixes):
    tabs = [t for (t,) in db.ex("SHOW TABLES") if t.startswith(prefixes)]
    for t in tabs:
        db.ex(f"ANALYZE TABLE {t}")
    rows = db.ex(
        "SELECT t.table_name, t.data_length, t.index_length, s.file_size, s.allocated_size "
        "FROM information_schema.tables t LEFT JOIN information_schema.innodb_sys_tablespaces s "
        "ON s.name = CONCAT(t.table_schema, '/', t.table_name) WHERE t.table_schema = %s ORDER BY t.table_name",
        (dbname,),
    ) if _has_sys_tablespaces(db) else [
        (t, dl, il, None, None) for t, dl, il in db.ex(
            "SELECT table_name, data_length, index_length FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name",
            (dbname,))
    ]
    out = {}
    emit(f"{'table':<16}{'rows(exact)':>14}{'data MiB':>10}{'index MiB':>10}{'total MiB':>10}{'ibd MiB':>10}")
    for t, dl, il, fs, _ in rows:
        if not t.startswith(prefixes):
            continue
        ((n,),) = db.ex(f"SELECT COUNT(*) FROM {t}")
        out[t] = {"rows": n, "data": dl, "index": il, "ibd": fs}
        emit(f"{t:<16}{n:>14,}{dl / 2**20:>10.2f}{il / 2**20:>10.2f}{(dl + il) / 2**20:>10.2f}"
             f"{(fs or 0) / 2**20:>10.2f}")
    for p in prefixes:
        part = [v for t, v in out.items() if t.startswith(p)]
        tot = sum(v["data"] + v["index"] for v in part)
        ibd = sum(v["ibd"] or 0 for v in part)
        rows_ = sum(v["rows"] for v in part)
        emit(f"  {p}* total rows={rows_:,} size={tot / 2**20:.2f} MiB ibd={ibd / 2**20:.2f} MiB")
        out[p + "*"] = {"rows": rows_, "mib": round(tot / 2**20, 2), "ibd_mib": round(ibd / 2**20, 2)}
    return out


def _has_sys_tablespaces(db):
    return db.ex("SELECT VERSION()")[0][0].startswith("5.")


def counter_fmt(st: Counter, first=("seconds", "db_seconds", "records", "batches", "statements")):
    head = " ".join(f"{k}={st[k]}" for k in first if k in st)
    rest = " ".join(f"{k}={v}" for k, v in sorted(st.items()) if k not in first)
    return head + " | " + rest
