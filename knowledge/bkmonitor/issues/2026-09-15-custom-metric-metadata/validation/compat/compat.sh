#!/usr/bin/env bash
# 用 Docker 依次启动 MySQL 5.7 / 8.0，执行 compat.py，结果写入 results/compat_<57|80>.{txt,json}。
# 每个版本独占一个容器与数据卷，执行结束（含失败）即删除，两个版本不同时运行以控制磁盘占用。
# 用法：bash compat/compat.sh [57|80|all|diff|rmi] [compat.py run 的额外参数...]
# Docker Hub 不可达时用 IMAGE_57 / IMAGE_80 指定镜像源，例如 docker.m.daocloud.io/library/mysql:5.7
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_57="${IMAGE_57:-mysql:5.7}"
IMAGE_80="${IMAGE_80:-mysql:8.0}"
TARGET="${1:-all}"
shift || true
EXTRA_ARGS=("$@")

COMMON_FLAGS=(
  --character-set-server=utf8 --collation-server=utf8_general_ci
  --innodb-file-per-table=ON --innodb-default-row-format=DYNAMIC
  --innodb-buffer-pool-size=2G --innodb-flush-log-at-trx-commit=1
  --local-infile=ON --max-allowed-packet=256M --skip-name-resolve --performance-schema=ON
)

cleanup() {
  docker rm -f "cm-compat-$1" >/dev/null 2>&1 || true
  docker volume rm "cm-compat-$1-data" >/dev/null 2>&1 || true
}

run_version() {
  local ver="$1" image port platform name volume
  local -a flags
  case "$ver" in
    57)
      image="$IMAGE_57" port=33307 platform="linux/amd64"
      flags=(--innodb-large-prefix=ON --innodb-file-format=Barracuda --innodb-log-file-size=128M)
      ;;
    80)
      image="$IMAGE_80" port=33308 platform="linux/arm64"
      flags=(--skip-log-bin --innodb-redo-log-capacity=268435456)
      ;;
    *) echo "unknown version $ver" >&2; return 1 ;;
  esac
  name="cm-compat-$ver"
  volume="cm-compat-$ver-data"
  cleanup "$ver"
  trap "cleanup $ver" EXIT
  docker run -d --name "$name" --platform "$platform" -p "127.0.0.1:$port:3306" \
    -e MYSQL_ALLOW_EMPTY_PASSWORD=yes -v "$volume:/var/lib/mysql" \
    "$image" "${COMMON_FLAGS[@]}" "${flags[@]}" >/dev/null
  for _ in $(seq 1 180); do
    docker exec "$name" mysql -uroot -h127.0.0.1 --protocol=TCP -e "SELECT 1" >/dev/null 2>&1 && break
    sleep 1
  done
  mkdir -p "$ROOT/results"
  cd "$ROOT"
  uv run --quiet --with 'pymysql==1.1.1' python compat/compat.py run --port "$port" \
    --json "results/compat_$ver.json" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} | tee "results/compat_$ver.txt"
  docker system df -v 2>/dev/null | grep -E "cm-compat-$ver-data" || true
  cleanup "$ver"
  trap - EXIT
}

case "$TARGET" in
  57 | 80) run_version "$TARGET" ;;
  all)
    run_version 57
    run_version 80
    ;;
  diff)
    cd "$ROOT"
    uv run --quiet --with 'pymysql==1.1.1' python compat/compat.py diff results/compat_57.json results/compat_80.json |
      tee results/compat_diff.txt
    ;;
  rmi) docker rmi "$IMAGE_57" "$IMAGE_80" ;;
  *) echo "usage: bash compat/compat.sh [57|80|all|diff|rmi] [run 参数...]" >&2; exit 1 ;;
esac
