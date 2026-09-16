package metadata

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"runtime"
	"strconv"
	"testing"
	"time"
)

func TestBloomSizingMemory(t *testing.T) {
	if os.Getenv("BLOOM_MEMORY_RUN") == "" {
		t.Skip("run with BLOOM_MEMORY_RUN")
	}
	n, nErr := strconv.Atoi(os.Getenv("N"))
	p, pErr := strconv.ParseFloat(os.Getenv("FPR"), 64)
	if nErr != nil || pErr != nil || n <= 0 || p <= 0 || p >= 1 {
		t.Fatal("invalid N/FPR")
	}
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	f := newBloomWithProbability(n, p)
	for i := 0; i < n; i++ {
		f.testAdd(digest(fixture(i, "metric", 64)), true)
	}
	runtime.GC()
	runtime.ReadMemStats(&after)
	runtime.KeepAlive(f)
	// Sizing equations assume n distinct key/value versions, not just n keys.
	predicted := func(multiplier float64) float64 {
		return math.Pow(1-math.Exp(-float64(f.k)*float64(n)*multiplier/float64(len(f.bits)*64)), float64(f.k))
	}
	row := map[string]any{"keys": n, "target_fpr": p, "hashes": f.k, "bitmap_bytes": len(f.bits) * 8, "two_generation_bitmap_bytes": len(f.bits) * 16, "heap_live_bytes": int64(after.HeapAlloc) - int64(before.HeapAlloc), "predicted_fpr_at_capacity": predicted(1), "predicted_fpr_at_2x_versions": predicted(2), "predicted_fpr_at_5x_versions": predicted(5), "two_generation_union_upper_bound": 2 * p}
	b, err := json.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	fmt.Println(string(b))
}

func BenchmarkBloomTargets(b *testing.B) {
	for _, n := range []int{100000, 1000000} {
		for _, p := range []float64{1e-2, 1e-4, 1e-6} {
			b.Run(fmt.Sprintf("N=%d/p=%g", n, p), func(b *testing.B) {
				f := newBloomWithProbability(n, p)
				entries := make([]Entry, n)
				for i := range entries {
					entries[i] = fixture(i, "metric", 64)
					f.testAdd(digest(entries[i]), true)
				}
				b.ReportAllocs()
				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					if !f.testAdd(digest(entries[i%n]), false) {
						b.Fatal("lost inserted value")
					}
				}
			})
		}
	}
}

func TestBloomTargets(t *testing.T) {
	if os.Getenv("BLOOM_RUN") == "" {
		t.Skip("run with BLOOM_RUN")
	}
	const probes = 1000000
	for _, n := range []int{100000, 1000000} {
		for _, p := range []float64{1e-2, 1e-4, 1e-6} {
			f := newBloomWithProbability(n, p)
			for i := 0; i < n; i++ {
				f.testAdd(digest(fixture(i, "metric", 64)), true)
			}
			absent, changed := 0, 0
			for i := 0; i < probes; i++ {
				if f.testAdd(digest(fixture(n+i, "metric", 64)), false) {
					absent++
				}
				e := fixture(i%n, "metric", 64)
				// Even when probes > n, every changed key/value pair is distinct.
				e.Value.Description = fmt.Sprintf("%064d", i)
				if f.testAdd(digest(e), false) {
					changed++
				}
			}
			row := map[string]any{"keys": n, "target_fpr": p, "probes_per_population": probes, "absent_false_positive": absent, "changed_description_false_positive": changed}
			b, err := json.Marshal(row)
			if err != nil {
				t.Fatal(err)
			}
			fmt.Println(string(b))
		}
	}
}

func TestBloomHistoricalVersion(t *testing.T) {
	a := fixture(0, "metric", 64)
	b := a
	b.Value.Usage = "max"
	f := newBloomWithProbability(100000, 1e-6)
	f.testAdd(digest(a), true)
	f.testAdd(digest(b), true)
	if !f.testAdd(digest(a), false) {
		t.Fatal("Bloom must remember the earlier A")
	}
	s := NewStore(time.Hour, 10, 10, func(context.Context, []Entry) error { return nil })
	for _, e := range []Entry{a, b, a} {
		s.Observe(e.Key, e.Value)
		if n, err := s.Flush(context.Background()); n != 1 || err != nil {
			t.Fatal(n, err)
		}
	}
	f = newBloomWithProbability(100000, 1e-6)
	if f.testAdd(digest(a), false) {
		t.Fatal("empty filter cannot remember A")
	}
	fmt.Println("history sequence=A,B,A exact_exports=1,1,1 bloom_exports=1,1,0 after_full_reset_A_is_new=true")
}
