#!/usr/bin/env bash
# 启动隔离的本地 mysqld，执行 bench.py 的一个套件，输出写入 results/<name>.txt，结束后关闭实例。
# 用法：bash run.sh <name> <脚本参数...>；CM_BENCH_SCRIPT 选择脚本，默认 bench.py
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="${CM_BENCH_WORK:-${TMPDIR:-/tmp}/cm-metric-bench}"
DATADIR="$WORK/data"
SOCKET="$WORK/mysql.sock"
PIDFILE="$WORK/mysqld.pid"
NAME="$1"
shift

mkdir -p "$WORK" "$ROOT/results"
if [[ ! -d "$DATADIR/mysql" ]]; then
  mysqld --no-defaults --initialize-insecure --datadir="$DATADIR" >"$WORK/init.log" 2>&1
fi

mysqld --no-defaults \
  --datadir="$DATADIR" --socket="$SOCKET" --pid-file="$PIDFILE" --port=33306 --bind-address=127.0.0.1 \
  --skip-log-bin --skip-mysqlx --local-infile=ON --character-set-server=utf8mb4 \
  --innodb-buffer-pool-size=8G --innodb-redo-log-capacity=2G --innodb-flush-log-at-trx-commit=1 \
  --max-allowed-packet=256M >"$WORK/mysqld.log" 2>&1 &

cleanup() {
  mysqladmin --no-defaults --socket="$SOCKET" -uroot shutdown >/dev/null 2>&1 || true
  wait 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  mysqladmin --no-defaults --socket="$SOCKET" -uroot ping >/dev/null 2>&1 && break
  sleep 1
done
mysql --no-defaults --socket="$SOCKET" -uroot -e "CREATE DATABASE IF NOT EXISTS cm_bench"

export CM_BENCH_SOCKET="$SOCKET"
cd "$ROOT"
uv run --quiet --with 'pymysql==1.1.1' python "${CM_BENCH_SCRIPT:-bench.py}" "$@" | tee "results/$NAME.txt"
