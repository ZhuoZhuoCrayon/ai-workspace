#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
lab_binary=$(mktemp "${TMPDIR:-/tmp}/metricmeta-performance.XXXXXX")
trap 'rm -f "$lab_binary"' EXIT
go test -c -o "$lab_binary"
case "${1:-}" in
  sent)
    : > results/sent_memory.txt
    for n in 10000 100000 1000000 10000000; do
      ISOLATED_SENT_RUN=1 N="$n" "$lab_binary" -test.run '^TestIsolatedSentMemory$' >> results/sent_memory.txt
    done
    go test -run '^$' -bench '^BenchmarkIsolatedSent$' -benchmem -benchtime=200ms -count=3 > results/sent_lookup.txt
    ;;
  buffer)
    : > results/buffer_memory.txt
    for n in 10000 100000 1000000; do
      for desc in 64 1024; do
        for mode in pending inflight; do
          ISOLATED_BUFFER_RUN=1 N="$n" DESC="$desc" MODE="$mode" "$lab_binary" -test.run '^TestIsolatedBufferMemory$' >> results/buffer_memory.txt
        done
      done
    done
    ISOLATED_COLD_RUN=1 "$lab_binary" -test.run '^TestIsolatedColdStart$' -test.timeout 10m > results/buffer_coldstart.txt
    ;;
  *)
    echo 'usage: bash performance.sh sent|buffer' >&2
    exit 2
    ;;
esac
