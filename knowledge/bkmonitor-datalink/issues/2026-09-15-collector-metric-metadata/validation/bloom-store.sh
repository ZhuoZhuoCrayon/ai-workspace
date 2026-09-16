#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
lab_binary=$(mktemp "${TMPDIR:-/tmp}/collector-metadata-bloom-store.XXXXXX")
trap 'rm -f "$lab_binary"' EXIT
go test -race ./... > results/tests.txt
go vet ./...
go test -c -o "$lab_binary"
: > results/bloom_store_memory.txt
for n in 10000 100000 1000000; do
  for desc in 64 1024; do
    for mode in pipeline inflight; do
      BLOOM_STORE_MEMORY_RUN=1 N="$n" DESC="$desc" MODE="$mode" "$lab_binary" -test.run '^TestBloomStoreMemory$' >> results/bloom_store_memory.txt
    done
  done
done
for axis in dataid service group metric; do
  BLOOM_STORE_MEMORY_RUN=1 N=10000 DESC=64 MODE=pipeline AXIS="$axis" "$lab_binary" -test.run '^TestBloomStoreMemory$' >> results/bloom_store_memory.txt
done
go test -run '^$' -bench '^BenchmarkBloomStoreFlush$' -benchmem -benchtime=3x -count=3 > results/bloom_store_benchmark.txt
BLOOM_COLD_RUN=1 "$lab_binary" -test.run '^TestBloomColdStart$' -test.timeout 10m > results/bloom_store_coldstart.txt
"$lab_binary" -test.run '^TestBloomStore' -test.v > results/bloom_store_behavior.txt

BLOOM_TTL_RUN=1 "$lab_binary" -test.run '^TestBloomTTLSimulation$' > results/bloom_store_ttl.txt
