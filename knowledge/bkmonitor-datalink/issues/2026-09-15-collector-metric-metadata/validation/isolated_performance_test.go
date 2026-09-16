package metadata

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"testing"
)

// A single unique metric identifies each entry; there is no Cartesian fixture.
func performanceEntry(i, descriptionBytes int) Entry {
	name := fmt.Sprintf("metric_%08d", i)
	return Entry{
		Key: Key{DataID: 1, ScopeType: strings.Clone("DEFAULT"), Metric: name},
		Value: Value{
			Name: strings.Clone(name), Unit: strings.Clone("1"),
			Description: strings.Repeat("d", descriptionBytes),
			Type:        strings.Clone("gauge"), Temporality: strings.Clone("delta"),
			Usage: strings.Clone("last"), Present: 11,
		},
	}
}

func performanceSize(t *testing.T, name string) int {
	t.Helper()
	n, err := strconv.Atoi(os.Getenv(name))
	if err != nil || n <= 0 {
		t.Fatalf("invalid %s", name)
	}
	return n
}

func printPerformanceRow(t *testing.T, row map[string]any) {
	t.Helper()
	b, err := json.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	fmt.Println(string(b))
}

func TestIsolatedSentMemory(t *testing.T) {
	if os.Getenv("ISOLATED_SENT_RUN") == "" {
		t.Skip("run make sent")
	}
	n := performanceSize(t, "N")
	// Retain only sent state after GC. Source records are not cached.
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	s := &BloomStore{filter: newBloomWithProbability(n, 1e-6), capacity: n, generation: 1}
	for i := 0; i < n; i++ {
		s.filter.testAdd(s.fingerprint(performanceEntry(i, 64)), true)
		s.versions++
	}
	runtime.GC()
	runtime.ReadMemStats(&after)
	runtime.KeepAlive(s)
	printPerformanceRow(t, map[string]any{
		"component": "sent", "unique_keys": n, "versions": s.versions,
		"target_fpr": 1e-6, "hash_probes": s.filter.k,
		"bitmap_bytes":    len(s.filter.bits) * 8,
		"heap_live_bytes": int64(after.HeapAlloc) - int64(before.HeapAlloc),
		"go":              runtime.Version(),
	})
}

func BenchmarkIsolatedSent(b *testing.B) {
	for _, n := range []int{10000, 100000, 1000000, 10000000} {
		b.Run(fmt.Sprintf("N=%d", n), func(b *testing.B) {
			s := &BloomStore{filter: newBloomWithProbability(n, 1e-6), capacity: n, generation: 1}
			for i := 0; i < n; i++ {
				s.filter.testAdd(s.fingerprint(performanceEntry(i, 64)), true)
			}
			// Spread queries across the full inserted range without retaining every record.
			count := min(n, 65536)
			entries := make([]Entry, count)
			hashes := make([][32]byte, count)
			for i := range entries {
				entries[i] = performanceEntry(i*n/count, 64)
				hashes[i] = s.fingerprint(entries[i])
			}
			b.Run("bitmap", func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					if !s.filter.testAdd(hashes[i%count], false) {
						b.Fatal("inserted fingerprint missing")
					}
				}
			})
			b.Run("version", func(b *testing.B) {
				b.ReportAllocs()
				for i := 0; i < b.N; i++ {
					if !s.filter.testAdd(s.fingerprint(entries[i%count]), false) {
						b.Fatal("inserted version missing")
					}
				}
			})
		})
	}
}

func TestIsolatedBufferMemory(t *testing.T) {
	if os.Getenv("ISOLATED_BUFFER_RUN") == "" {
		t.Skip("run make buffer")
	}
	n, descriptionBytes := performanceSize(t, "N"), performanceSize(t, "DESC")
	mode := os.Getenv("MODE")
	if mode != "pending" && mode != "inflight" {
		t.Fatal("MODE must be pending or inflight")
	}
	fill := func(offset int) map[Key]pendingValue {
		items := make(map[Key]pendingValue)
		for i := 0; i < n; i++ {
			e := performanceEntry(i+offset, descriptionBytes)
			items[e.Key] = pendingValue{Value: e.Value}
		}
		return items
	}
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	pending := fill(0)
	var snapshot map[Key]pendingValue
	if mode == "inflight" {
		snapshot = pending
		pending = fill(n) // Independent records keep both complete maps alive.
	}
	runtime.GC()
	runtime.ReadMemStats(&after)
	runtime.KeepAlive(pending)
	runtime.KeepAlive(snapshot)
	printPerformanceRow(t, map[string]any{
		"component": "buffer", "unique_keys_per_map": n,
		"description_bytes": descriptionBytes, "mode": mode,
		"pending_entries": len(pending), "snapshot_entries": len(snapshot),
		"heap_live_bytes": int64(after.HeapAlloc) - int64(before.HeapAlloc),
		"go":              runtime.Version(),
	})
}
