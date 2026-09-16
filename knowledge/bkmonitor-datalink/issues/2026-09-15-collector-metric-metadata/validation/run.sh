#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p results
lab_binary=$(mktemp "${TMPDIR:-/tmp}/collector-metadata-lab.XXXXXX")
trap 'rm -f "$lab_binary"' EXIT
go version > results/environment.txt
go env GOOS GOARCH >> results/environment.txt
uname -sm >> results/environment.txt
go test -race ./... > results/tests.txt
go vet ./...
go test -race -v ./protocolcheck > results/protocol.txt
go test -c -o "$lab_binary"
go test -run '^$' -bench 'Benchmark(Lookup|Observe)$' -benchmem -benchtime=200ms -count=3 > results/benchmark.txt
go test -run '^$' -bench '^BenchmarkFlush$' -benchmem -benchtime=3x -count=3 > results/flush.txt
: > results/memory.txt
for n in 1000 10000 100000 1000000; do
  for mode in full sha256 bloom go-cache pipeline; do
    MEMORY_RUN=1 N="$n" DESC=64 AXIS=combined MODE="$mode" "$lab_binary" -test.run '^TestMemory$' >> results/memory.txt
  done
done
for axis in dataid service group metric all10k; do
  MEMORY_RUN=1 N=10000 DESC=64 AXIS="$axis" MODE=full "$lab_binary" -test.run '^TestMemory$' >> results/memory.txt
done
for mode in full sha256 pipeline; do
  MEMORY_RUN=1 N=100000 DESC=1024 AXIS=combined MODE="$mode" "$lab_binary" -test.run '^TestMemory$' >> results/memory.txt
done
for n in 25000 130000 1450000; do
  MEMORY_RUN=1 N="$n" DESC=64 AXIS=combined MODE=full "$lab_binary" -test.run '^TestMemory$' >> results/memory.txt
done
for desc in 64 1024; do
  MEMORY_RUN=1 N=100000 DESC="$desc" AXIS=combined MODE=inflight "$lab_binary" -test.run '^TestMemory$' >> results/memory.txt
done
for n in 10000 100000 1000000; do
  for mode in full pipeline; do
    MEMORY_RUN=1 N="$n" DESC=64 AXIS=joint10k MODE="$mode" "$lab_binary" -test.run '^TestMemory$' >> results/memory.txt
  done
done
JOINT_RUN=1 "$lab_binary" -test.run '^TestJointCardinality$' > results/cardinality.txt
COLD_RUN=1 "$lab_binary" -test.run '^TestColdStart$' -test.timeout 10m > results/coldstart.txt
"$lab_binary" -test.run '^TestLimitedExport' -test.v >> results/coldstart.txt
TTL_RUN=1 "$lab_binary" -test.run '^TestTTLSimulation$' -test.timeout 10m > results/ttl.txt
"$lab_binary" -test.run '^TestBloomFalsePositives$' > results/bloom.txt
"$lab_binary" -test.run '^TestWireSize$' > results/wire.txt
go run ./cmd/demo > results/demo.txt

bash bloom.sh
bash bloom-store.sh
