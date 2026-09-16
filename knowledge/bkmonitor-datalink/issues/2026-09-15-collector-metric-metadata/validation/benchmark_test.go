package metadata

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	cache "github.com/patrickmn/go-cache"
)

// fixture allocates independent strings, including repeated names across sources.
// This intentionally avoids assuming an interning layer in production.
func fixture(i int, axis string, descBytes int) Entry {
	d, s, g, m := i%10000, i%10000, i%10000, i/10000
	switch axis {
	case "all10k":
		m = i % 10000
	case "joint10k":
		s, g, m = (i+i/10000)%10000, (i+i/100000)%10000, i%10000
	case "dataid":
		d, s, g, m = i, 0, 0, 0
	case "service":
		d, s, g, m = 0, i, 0, 0
	case "group":
		d, s, g, m = 0, 0, i, 0
	case "metric":
		d, s, g, m = 0, 0, 0, i
	}
	name := fmt.Sprintf("request_duration_seconds_%06d", m)
	return Entry{
		Key:   Key{DataID: int32(d), ScopeType: strings.Clone("APM"), Scope: fmt.Sprintf("service_%06d-group_%06d", s, g), Metric: name + "_sum"},
		Value: Value{Name: strings.Clone(name), Unit: strings.Clone("s"), Description: strings.Repeat("d", descBytes), Type: strings.Clone("histogram"), Temporality: strings.Clone("delta"), Usage: strings.Clone("sum"), Interval: 60000, Present: 15},
	}
}

type digestValue struct {
	Digest  [32]byte
	Expires int64
}

func BenchmarkLookup(b *testing.B) {
	for _, n := range []int{1000, 10000, 100000, 1000000} {
		entries := make([]Entry, n)
		full := make(map[Key]sentEntry, n)
		hashed := make(map[Key]digestValue, n)
		filter := newBloom(n)
		generic := cache.New(2*time.Hour, 0)
		genericKeys := make([]string, n)
		for i := range entries {
			entries[i] = fixture(i, "combined", 64)
			e := fixture(i, "combined", 64) // Equal bytes with distinct backing strings, like a newly decoded request.
			full[e.Key] = sentEntry{e.Value, time.Unix(7200, 0)}
			h := digest(e)
			hashed[e.Key] = digestValue{valueDigest(e.Value), 7200}
			filter.testAdd(h, true)
			genericKeys[i] = fmt.Sprintf("%d/%s/%s/%s", e.Key.DataID, e.Key.ScopeType, e.Key.Scope, e.Key.Metric)
			generic.Set(genericKeys[i], e.Value, cache.DefaultExpiration)
			genericKeys[i] = strings.Clone(genericKeys[i]) // Query keys must not share backing strings with cache keys.
		}
		b.Run(fmt.Sprintf("full/N=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				e := entries[i%n]
				if full[e.Key].Value != e.Value {
					b.Fatal("miss")
				}
			}
		})
		b.Run(fmt.Sprintf("sha256/N=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				e := entries[i%n]
				if hashed[e.Key].Digest != valueDigest(e.Value) {
					b.Fatal("miss")
				}
			}
		})
		b.Run(fmt.Sprintf("bloom/N=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				if !filter.testAdd(digest(entries[i%n]), false) {
					b.Fatal("miss")
				}
			}
		})
		b.Run(fmt.Sprintf("go-cache/N=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				v, ok := generic.Get(genericKeys[i%n])
				if !ok || v.(Value) != entries[i%n].Value {
					b.Fatal("miss")
				}
			}
		})
		b.Run(fmt.Sprintf("go-cache-key/N=%d", n), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				e := entries[i%n]
				k := fmt.Sprintf("%d/%s/%s/%s", e.Key.DataID, e.Key.ScopeType, e.Key.Scope, e.Key.Metric)
				v, ok := generic.Get(k)
				if !ok || v.(Value) != e.Value {
					b.Fatal("miss")
				}
			}
		})
	}
}

func BenchmarkObserve(b *testing.B) {
	entries := make([]Entry, 10000)
	s := NewStore(2*time.Hour, 100000, 1000, nil)
	for i := range entries {
		entries[i] = fixture(i, "combined", 64)
		s.Observe(entries[i].Key, entries[i].Value)
	}
	b.Run("warm-serial", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			e := entries[i%len(entries)]
			s.Observe(e.Key, e.Value)
		}
	})
	b.Run("warm-parallel", func(b *testing.B) {
		b.ReportAllocs()
		b.RunParallel(func(pb *testing.PB) {
			i := 0
			for pb.Next() {
				e := entries[i%len(entries)]
				s.Observe(e.Key, e.Value)
				i++
			}
		})
	})
	b.Run("changed", func(b *testing.B) {
		b.ReportAllocs()
		for i := 0; i < b.N; i++ {
			e := entries[i%len(entries)]
			e.Value.Interval = int64(i)
			s.Observe(e.Key, e.Value)
		}
	})
}

func BenchmarkFlush(b *testing.B) {
	for _, n := range []int{10000, 100000} {
		for _, mode := range []string{"stable", "expired"} {
			b.Run(fmt.Sprintf("%s/N=%d", mode, n), func(b *testing.B) {
				s := NewStore(2*time.Hour, n+1, 1000, func(context.Context, []Entry) error { return nil })
				now := time.Unix(0, 0)
				s.now = func() time.Time { return now }
				entries := make([]Entry, n)
				for i := range entries {
					entries[i] = fixture(i, "combined", 64)
					s.Observe(entries[i].Key, entries[i].Value)
				}
				s.Flush(context.Background())
				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					b.StopTimer()
					for _, e := range entries {
						s.Observe(e.Key, e.Value)
					}
					if mode == "expired" {
						now = now.Add(2 * time.Hour)
					}
					b.StartTimer()
					s.Flush(context.Background())
				}
			})
		}
	}
}

// TestMemory runs in a fresh process per configuration via run.sh.
func TestMemory(t *testing.T) {
	if os.Getenv("MEMORY_RUN") == "" {
		t.Skip("run with MEMORY_RUN")
	}
	readPositive := func(name string) int {
		t.Helper()
		value, err := strconv.Atoi(os.Getenv(name))
		if err != nil || value <= 0 {
			t.Fatalf("%s must be a positive integer", name)
		}
		return value
	}
	n, desc := readPositive("N"), readPositive("DESC")
	mode, axis := os.Getenv("MODE"), os.Getenv("AXIS")
	switch axis {
	case "combined", "dataid", "service", "group", "metric", "joint10k":
	case "all10k":
		if n != 10000 {
			t.Fatal("all10k requires N=10000")
		}
	default:
		t.Fatalf("unknown axis %q", axis)
	}
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	start := time.Now()
	var keep any
	var cleanup func()
	switch mode {
	case "go-cache":
		m := cache.New(2*time.Hour, 0)
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			k := fmt.Sprintf("%d/%s/%s/%s", e.Key.DataID, e.Key.ScopeType, e.Key.Scope, e.Key.Metric)
			m.Set(k, e.Value, cache.DefaultExpiration)
		}
		keep = m
	case "full":
		m := make(map[Key]sentEntry, n)
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			m[e.Key] = sentEntry{e.Value, time.Unix(7200, 0)}
		}
		keep = m
	case "sha256":
		m := make(map[Key]digestValue, n)
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			m[e.Key] = digestValue{valueDigest(e.Value), 7200}
		}
		keep = m
	case "bloom":
		m := newBloom(n)
		for i := 0; i < n; i++ {
			m.testAdd(digest(fixture(i, axis, desc)), true)
		}
		keep = m
	case "pipeline":
		s := NewStore(2*time.Hour, n+1, 1000, func(context.Context, []Entry) error { return nil })
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			s.Observe(e.Key, e.Value)
		}
		s.Flush(context.Background())
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			s.Observe(e.Key, e.Value)
		}
		keep = s
	case "inflight":
		s := NewStore(2*time.Hour, n+1, 1000, func(context.Context, []Entry) error { return nil })
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			s.Observe(e.Key, e.Value)
		}
		s.Flush(context.Background())
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			e.Value.Interval = 30000
			s.Observe(e.Key, e.Value)
		}
		entered, release, done := make(chan struct{}), make(chan struct{}), make(chan struct{})
		first := true
		s.export = func(context.Context, []Entry) error {
			if first {
				first = false
				close(entered)
				<-release
			}
			return nil
		}
		go func() { s.Flush(context.Background()); close(done) }()
		<-entered
		for i := 0; i < n; i++ {
			e := fixture(i, axis, desc)
			e.Value.Interval = 15000
			s.Observe(e.Key, e.Value)
		}
		keep = s
		cleanup = func() { close(release); <-done }
	default:
		t.Fatal("unknown mode")
	}
	build := time.Since(start)
	runtime.GC()
	runtime.ReadMemStats(&after)
	runtime.KeepAlive(keep)
	if cleanup != nil {
		cleanup()
	}
	row := map[string]any{"mode": mode, "axis": axis, "n": n, "description_bytes": desc, "heap_live_bytes": int64(after.HeapAlloc) - int64(before.HeapAlloc), "total_alloc_bytes": after.TotalAlloc - before.TotalAlloc, "heap_sys_bytes": after.HeapSys, "build_ms": float64(build.Microseconds()) / 1000, "go": runtime.Version()}
	js, _ := json.Marshal(row)
	fmt.Println(string(js))
}

func TestBloomFalsePositives(t *testing.T) {
	f := newBloom(100000)
	for i := 0; i < 100000; i++ {
		f.testAdd(digest(fixture(i, "metric", 64)), true)
	}
	fp := 0
	for i := 100000; i < 200000; i++ {
		if f.testAdd(digest(fixture(i, "metric", 64)), false) {
			fp++
		}
	}
	// Changing the value creates a new membership key but can still be falsely suppressed.
	changed := 0
	for i := 0; i < 100000; i++ {
		e := fixture(i, "metric", 64)
		e.Value.Unit = "ms"
		if f.testAdd(digest(e), false) {
			changed++
		}
	}
	fmt.Printf("bloom absent_false_positive=%d/100000 changed_false_positive=%d/100000\n", fp, changed)
	if fp == 0 || fp > 2000 || changed == 0 || changed > 2000 {
		t.Fatal("unexpected false positive rate")
	}
}

func TestTTLSimulation(t *testing.T) {
	if os.Getenv("TTL_RUN") == "" {
		t.Skip("run with TTL_RUN")
	}
	// Fake clock; 48h at one-minute intervals. Values repeat each minute, 100 new keys/minute.
	for _, ttl := range []int{15, 120, 1440} {
		now := time.Unix(0, 0)
		s := NewStore(time.Duration(ttl)*time.Minute, 1000000, 1000, func(context.Context, []Entry) error { return nil })
		s.now = func() time.Time { return now }
		total, maxBatch, peak := 0, 0, 0
		for minute := 0; minute < 2880; minute++ {
			now = time.Unix(int64(minute*60), 0)
			for i := 0; i < 1000; i++ {
				e := fixture(i, "metric", 64)
				s.Observe(e.Key, e.Value)
			}
			for i := 0; i < 100; i++ {
				e := fixture(1000+minute*100+i, "metric", 64)
				s.Observe(e.Key, e.Value)
			}
			n, err := s.Flush(context.Background())
			if err != nil {
				t.Fatal(err)
			}
			total += n
			if n > maxBatch {
				maxBatch = n
			}
			if len(s.sent) > peak {
				peak = len(s.sent)
			}
		}
		// Independent workload arithmetic: each stable key sends at t=0 and at TTL boundaries;
		// each one-shot key sends once and stays cached for exactly ttl ticks.
		wantExports := ((2880-1)/ttl+1)*1000 + 2880*100
		wantPeak := 1000 + ttl*100
		if total != wantExports || maxBatch != 1100 || peak != wantPeak {
			t.Fatalf("TTL %d: exports=%d peak=%d max=%d; want %d, %d, 1100", ttl, total, peak, maxBatch, wantExports, wantPeak)
		}
		fmt.Printf("ttl_minutes=%d active=1000 new_keys_per_minute=100 duration_minutes=2880 exports=%d max_exports_per_tick=%d peak_sent=%d\n", ttl, total, maxBatch, peak)
	}
}

func TestWireSize(t *testing.T) {
	for _, size := range []int{64, 1024} {
		total := 0
		for i := 0; i < 10000; i++ {
			e := fixture(i, "all10k", size)
			b, err := encodeEntry(e)
			if err != nil {
				t.Fatal(err)
			}
			total += len(b)
		}
		fmt.Printf("json description_bytes=%d records=10000 total_bytes=%d mean_bytes=%.2f\n", size, total, float64(total)/10000)
	}
}

func TestJointCardinality(t *testing.T) {
	if os.Getenv("JOINT_RUN") == "" {
		t.Skip("run with JOINT_RUN")
	}
	for _, n := range []int{10000, 100000, 1000000} {
		keys := make(map[Key]struct{}, n)
		dataids := make(map[int32]struct{})
		services, groups, metrics := make(map[string]struct{}), make(map[string]struct{}), make(map[string]struct{})
		for i := 0; i < n; i++ {
			e := fixture(i, "joint10k", 64)
			service, group, ok := strings.Cut(e.Key.Scope, "-")
			if !ok {
				t.Fatal("fixture scope missing separator")
			}
			keys[e.Key] = struct{}{}
			dataids[e.Key.DataID], services[service], groups[group], metrics[e.Key.Metric] = struct{}{}, struct{}{}, struct{}{}, struct{}{}
		}
		if len(keys) != n || len(dataids) != 10000 || len(services) != 10000 || len(groups) != 10000 || len(metrics) != 10000 {
			t.Fatalf("invalid joint fixture: keys=%d dataids=%d services=%d groups=%d metrics=%d", len(keys), len(dataids), len(services), len(groups), len(metrics))
		}
		fmt.Printf("joint10k keys=%d dataids=%d services=%d groups=%d metrics=%d\n", len(keys), len(dataids), len(services), len(groups), len(metrics))
	}
}
