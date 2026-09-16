package metadata

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"testing"
	"time"
)

func TestBloomColdStart(t *testing.T) {
	if os.Getenv("BLOOM_COLD_RUN") == "" {
		t.Skip("run with BLOOM_COLD_RUN")
	}
	runBloomColdStart(t, func(i, desc int) Entry { return fixture(i, "joint10k", desc) }, "joint10k")
}

func TestIsolatedColdStart(t *testing.T) {
	if os.Getenv("ISOLATED_COLD_RUN") == "" {
		t.Skip("run with ISOLATED_COLD_RUN")
	}
	runBloomColdStart(t, performanceEntry, "unique-metric")
}

func runBloomColdStart(t *testing.T, entry func(int, int) Entry, fixtureName string) {
	t.Helper()
	for _, n := range []int{10000, 100000, 1000000} {
		for _, desc := range []int{64, 1024} {
			s := NewBloomStore(2*time.Hour, n, 1000, n, 1e-6, nil)
			for i := 0; i < n; i++ {
				e := entry(i, desc)
				if !s.Observe(e.Key, e.Value) {
					t.Fatal("fixture rejected")
				}
			}
			base := time.Now()
			now := base
			useBloomLogicalClock(s, &now)
			calls, records, maxBytes, maxEntries := 0, 0, 0, 0
			rounds, firstRound, maxCallsPerRound := 0, 0, 0
			var previous, last time.Time
			minimumGap := time.Duration(1<<63 - 1)
			sink := func(_ context.Context, body []byte) error {
				var batch []json.RawMessage
				if err := json.Unmarshal(body, &batch); err != nil {
					return err
				}
				if len(body) > coldLimits.MaxBytes || len(batch) > 1000 {
					t.Fatal("batch limit exceeded")
				}
				if !previous.IsZero() {
					gap := now.Sub(previous)
					if gap < coldLimits.MinInterval {
						t.Fatal("start interval violated", gap)
					}
					minimumGap = min(minimumGap, gap)
				}
				previous, last = now, now
				calls++
				records += len(batch)
				maxBytes, maxEntries = max(maxBytes, len(body)), max(maxEntries, len(batch))
				return nil
			}
			for len(s.pending) > 0 {
				now = base.Add(time.Duration(rounds) * time.Minute)
				ctx, cancel := context.WithDeadline(context.Background(), now.Add(5*time.Second))
				before := calls
				ack, err := s.FlushLimited(ctx, coldLimits, sink)
				cancel()
				if err != nil && !errors.Is(err, context.DeadlineExceeded) {
					t.Fatal(err)
				}
				if calls-before > 50 {
					t.Fatal("more than 50 starts in 5-second round")
				}
				if ack == 0 {
					t.Fatal("no progress")
				}
				maxCallsPerRound = max(maxCallsPerRound, calls-before)
				if rounds == 0 {
					firstRound = ack
				}
				rounds++
			}
			if records != n {
				t.Fatalf("records=%d want=%d", records, n)
			}
			row := map[string]any{"keys": n, "description_bytes": desc, "batches": calls, "records": records, "max_batch_bytes": maxBytes, "max_batch_records": maxEntries, "min_start_gap_ms": minimumGap.Milliseconds(), "max_starts_per_round": maxCallsPerRound, "first_round_records": firstRound, "rounds": rounds, "last_start_ms": last.Sub(base).Milliseconds(), "clock": "logical", "fixture": fixtureName, "mode": "bloom-force"}
			b, err := json.Marshal(row)
			if err != nil {
				t.Fatal(err)
			}
			fmt.Println(string(b))
		}
	}
}

func TestBloomStoreMemory(t *testing.T) {
	if os.Getenv("BLOOM_STORE_MEMORY_RUN") == "" {
		t.Skip("run with BLOOM_STORE_MEMORY_RUN")
	}
	n, nErr := strconv.Atoi(os.Getenv("N"))
	desc, dErr := strconv.Atoi(os.Getenv("DESC"))
	mode := os.Getenv("MODE")
	axis := os.Getenv("AXIS")
	if axis == "" {
		axis = "joint10k"
	}
	if nErr != nil || dErr != nil || n <= 0 || desc <= 0 {
		t.Fatal("invalid N/DESC")
	}
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	s := NewBloomStore(2*time.Hour, n, 1000, n, 1e-6, func(context.Context, []Entry) error { return nil })
	for i := 0; i < n; i++ {
		e := fixture(i, axis, desc)
		s.Observe(e.Key, e.Value)
	}
	if count, err := s.Flush(context.Background()); count != n || err != nil {
		t.Fatal(count, err)
	}
	for i := 0; i < n; i++ {
		e := fixture(i, axis, desc)
		if mode == "inflight" {
			e.Value.Interval = 30000
		}
		s.Observe(e.Key, e.Value)
	}
	var cleanup func()
	switch mode {
	case "pipeline":
	case "inflight":
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
		cleanup = func() { close(release); <-done }
	default:
		t.Fatal("unknown mode")
	}
	runtime.GC()
	runtime.ReadMemStats(&after)
	runtime.KeepAlive(s)
	if cleanup != nil {
		cleanup()
	}
	row := map[string]any{"mode": "bloom-" + mode, "axis": axis, "n": n, "description_bytes": desc, "target_fpr": 1e-6, "version_capacity": n, "heap_live_bytes": int64(after.HeapAlloc) - int64(before.HeapAlloc), "heap_sys_bytes": after.HeapSys, "total_alloc_bytes": after.TotalAlloc - before.TotalAlloc}
	b, err := json.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	fmt.Println(string(b))
}

func BenchmarkBloomStoreFlush(b *testing.B) {
	for _, n := range []int{10000, 100000, 1000000} {
		for _, mode := range []string{"stable", "forced"} {
			b.Run(fmt.Sprintf("%s/N=%d", mode, n), func(b *testing.B) {
				s := NewBloomStore(2*time.Hour, n, 1000, n, 1e-6, func(context.Context, []Entry) error { return nil })
				now := time.Now()
				useBloomLogicalClock(s, &now)
				entries := make([]Entry, n)
				for i := range entries {
					entries[i] = fixture(i, "joint10k", 64)
					s.Observe(entries[i].Key, entries[i].Value)
				}
				s.Flush(context.Background())
				b.ReportAllocs()
				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					b.StopTimer()
					for _, e := range entries {
						s.Observe(e.Key, e.Value)
					}
					if mode == "forced" {
						now = now.Add(2 * time.Hour)
					}
					b.StartTimer()
					s.Flush(context.Background())
				}
			})
		}
	}
}

func TestBloomTTLSimulation(t *testing.T) {
	if os.Getenv("BLOOM_TTL_RUN") == "" {
		t.Skip("run with BLOOM_TTL_RUN")
	}
	for _, ttl := range []int{15, 120, 1440} {
		now := time.Unix(0, 0)
		s := NewBloomStore(time.Duration(ttl)*time.Minute, 100000, 1000, 100000, 1e-6, func(context.Context, []Entry) error { return nil })
		useBloomLogicalClock(s, &now)
		total, peak, maximum := 0, 0, 0
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
			peak, maximum = max(peak, s.versions), max(maximum, n)
		}
		if peak > 100000 || maximum > 1100 {
			t.Fatal("unbounded version count or per-tick observations")
		}
		fmt.Printf("ttl_minutes=%d active=1000 new_keys_per_minute=100 duration_minutes=2880 exports=%d max_exports_per_tick=%d peak_versions=%d bitmap_bytes=%d generations=%d\n", ttl, total, maximum, peak, len(s.filter.bits)*8, s.generation)
	}
}
