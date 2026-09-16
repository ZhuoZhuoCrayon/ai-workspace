#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
lab_binary=$(mktemp "${TMPDIR:-/tmp}/collector-metadata-bloom.XXXXXX")
trap 'rm -f "$lab_binary"' EXIT
go test -c -o "$lab_binary"
: > results/bloom_sizing.txt
for n in 100000 1000000; do
  for fpr in 1e-2 1e-4 1e-6; do
    BLOOM_MEMORY_RUN=1 N="$n" FPR="$fpr" "$lab_binary" -test.run '^TestBloomSizingMemory$' >> results/bloom_sizing.txt
  done
done
go test -run '^$' -bench '^BenchmarkBloomTargets$' -benchmem -benchtime=200ms -count=3 > results/bloom_benchmark.txt
BLOOM_RUN=1 "$lab_binary" -test.run '^TestBloomTargets$' > results/bloom_targets.txt
"$lab_binary" -test.run '^TestBloomHistoricalVersion$' >> results/bloom_targets.txt
