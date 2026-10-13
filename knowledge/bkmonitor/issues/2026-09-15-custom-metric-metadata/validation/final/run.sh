#!/usr/bin/env bash
# 终版复测一键运行：5.7 全量压测 → 8.0 复核 DDL 与执行计划，结束或失败都删除容器与数据卷。
# 用法：./run.sh [all|57|80]
set -euo pipefail
cd "$(dirname "$0")"

NAME57=${NAME57:-pk6-b1-mysql}
PORT57=${PORT57:-33341}
VOL57=${VOL57:-pk6-b1-data}
NAME80=${NAME80:-pk6-b1-mysql80}
PORT80=${PORT80:-33342}
VOL80=${VOL80:-pk6-b1-data80}
IMAGE57=${IMAGE57:-biarms/mysql:5.7}
IMAGE80=${IMAGE80:-mysql:8.0}
UV=(uv run -q --with 'pymysql==1.1.1')
mkdir -p results

cleanup() {
  docker rm -f -v "$NAME57" "$NAME80" >/dev/null 2>&1 || true
  docker volume rm "$VOL57" "$VOL80" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_ready() {
  for _ in $(seq 1 90); do
    if MYSQL_PORT=$1 "${UV[@]}" python -c "import common; common.DB().ex('SELECT 1')" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "mysqld on port $1 not ready" >&2
  return 1
}

common_args=(--character-set-server=utf8 --collation-server=utf8_general_ci --innodb-buffer-pool-size=4G
  --innodb-flush-log-at-trx-commit=1 --skip-log-bin --innodb-log-file-size=512M --innodb-default-row-format=DYNAMIC
  --max-allowed-packet=256M --skip-name-resolve --innodb-buffer-pool-load-at-startup=OFF
  --innodb-buffer-pool-dump-at-shutdown=OFF)

run57() {
  docker run -d --name "$NAME57" --platform linux/arm64 -p "127.0.0.1:$PORT57:3306" -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
    -v "$VOL57:/var/lib/mysql" "$IMAGE57" "${common_args[@]}" --innodb-large-prefix=ON --innodb-file-format=Barracuda
  wait_ready "$PORT57"
  export MYSQL_PORT=$PORT57
  uv run -q --with 'django==4.2.27' --with 'pymysql==1.1.1' django_ddl.py 57 >/dev/null
  "${UV[@]}" bench.py smoke57
  for s in s1 s2 s3x s1tx; do "${UV[@]}" bench.py "$s"; done
  for p in "s1 1" "s2 2" "s3x 3"; do
    # shellcheck disable=SC2086
    "${UV[@]}" svcview_profile.py $p
    # shellcheck disable=SC2086
    "${UV[@]}" explain.py $p
  done
  for p in "s1 1" "s2 2" "s3x 3"; do
    # shellcheck disable=SC2086
    "${UV[@]}" overflow.py warm $p
    docker restart "$NAME57" >/dev/null
    wait_ready "$PORT57"
    # shellcheck disable=SC2086
    "${UV[@]}" overflow.py cold $p
  done
  for d in s1 s2 s3x; do "${UV[@]}" python -c "import common; common.DB().ex('DROP DATABASE $d')"; done
  "${UV[@]}" s3_size.py
  "${UV[@]}" explain.py s3f 1
  "${UV[@]}" python -c "import common; common.DB().ex('DROP DATABASE s3f')"
  "${UV[@]}" scope_ddl.py 57
  docker rm -f -v "$NAME57" >/dev/null
  docker volume rm "$VOL57" >/dev/null
}

run80() {
  docker run -d --name "$NAME80" --platform linux/arm64 -p "127.0.0.1:$PORT80:3306" -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
    -v "$VOL80:/var/lib/mysql" "$IMAGE80" "${common_args[@]}" --default-authentication-plugin=mysql_native_password
  wait_ready "$PORT80"
  export MYSQL_PORT=$PORT80
  uv run -q --with 'django==4.2.27' --with 'pymysql==1.1.1' django_ddl.py 80 >/dev/null
  "${UV[@]}" explain.py e80 1 --create
  "${UV[@]}" python -c "import common; common.DB().ex('DROP DATABASE e80')"
  "${UV[@]}" bench.py smoke80
  "${UV[@]}" scope_ddl.py 80
  docker rm -f -v "$NAME80" >/dev/null
  docker volume rm "$VOL80" >/dev/null
}

case "${1:-all}" in
  57) run57 ;;
  80) run80 ;;
  all) run57; run80 ;;
esac
docker ps -a --filter "name=pk6-b1"
docker volume ls --filter "name=pk6-b1"
