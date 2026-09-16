package metadata

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"
)

var coldLimits = ExportLimits{MaxBytes: 256 << 10, MinInterval: 100 * time.Millisecond}

func useLogicalClock(s *Store, now *time.Time) {
	s.now = func() time.Time { return *now }
	s.wait = func(ctx context.Context, d time.Duration) error {
		next := now.Add(d)
		if deadline, ok := ctx.Deadline(); ok && !next.Before(deadline) {
			*now = deadline
			return context.DeadlineExceeded
		}
		*now = next
		return ctx.Err()
	}
}

// All timing below uses a logical clock. Real JSON encoding, limits and Store
// transitions execute; transport/serialization duration is deliberately zero.
func TestColdStart(t *testing.T) {
	if os.Getenv("COLD_RUN") == "" {
		t.Skip("run with COLD_RUN")
	}
	for _, n := range []int{10000, 100000, 1000000} {
		for _, desc := range []int{64, 1024} {
			s := NewStore(2*time.Hour, n, 1000, nil)
			for i := 0; i < n; i++ {
				e := fixture(i, "joint10k", desc)
				if !s.Observe(e.Key, e.Value) {
					t.Fatal("fixture rejected")
				}
			}
			base := time.Now()
			now := base
			useLogicalClock(s, &now)
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
			if records != n || len(s.sent) != n {
				t.Fatalf("sent=%d records=%d want=%d", len(s.sent), records, n)
			}
			row := map[string]any{"keys": n, "description_bytes": desc, "batches": calls, "records": records, "max_batch_bytes": maxBytes, "max_batch_records": maxEntries, "min_start_gap_ms": minimumGap.Milliseconds(), "max_starts_per_round": maxCallsPerRound, "first_round_records": firstRound, "rounds": rounds, "last_start_ms": last.Sub(base).Milliseconds(), "clock": "logical", "axis": "joint10k"}
			b, err := json.Marshal(row)
			if err != nil {
				t.Fatal(err)
			}
			fmt.Println(string(b))
		}
	}
}

func TestLimitedExportDeadlineAndNewerValue(t *testing.T) {
	s := NewStore(time.Hour, 3, 1, nil)
	for i := 0; i < 3; i++ {
		e := fixture(i, "metric", 64)
		s.Observe(e.Key, e.Value)
	}
	now := time.Now()
	useLogicalClock(s, &now)
	ctx, cancel := context.WithDeadline(context.Background(), now.Add(100*time.Millisecond))
	defer cancel()
	calls := 0
	var changed Entry
	ack, err := s.FlushLimited(ctx, coldLimits, func(_ context.Context, _ []byte) error {
		calls++
		// Pick an unsent value. A newer observation must survive timeout restoration.
		for i := 0; i < 3; i++ {
			candidate := fixture(i, "metric", 64)
			candidate.Value.Usage = "max"
			s.Observe(candidate.Key, candidate.Value)
			changed = candidate
		}
		return nil
	})
	if calls != 1 || ack != 1 || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatal(calls, ack, err)
	}
	if s.pending[changed.Key].Usage != "max" || len(s.sent) != 1 || len(s.pending) != 3 {
		t.Fatal("timeout overwrote new observations")
	}
}

func TestLimitedExportFailure(t *testing.T) {
	s := NewStore(time.Hour, 10, 1, nil)
	for i := 0; i < 3; i++ {
		e := fixture(i, "metric", 64)
		s.Observe(e.Key, e.Value)
	}
	calls := 0
	ack, err := s.FlushLimited(context.Background(), coldLimits, func(context.Context, []byte) error { calls++; return errors.New("offline") })
	if err == nil || ack != 0 || calls != 1 || len(s.sent) != 0 || len(s.pending) != 3 {
		t.Fatal(ack, err, calls)
	}
}

func TestLimitedExportEscaping(t *testing.T) {
	s := NewStore(time.Hour, 1000, 1000, nil)
	for i := 0; i < 1000; i++ {
		e := fixture(i, "metric", 64)
		e.Value.Description = strings.Repeat("\x00", 1024) // Each byte becomes six JSON bytes.
		s.Observe(e.Key, e.Value)
	}
	now := time.Now()
	useLogicalClock(s, &now)
	calls, maxBytes := 0, 0
	ack, err := s.FlushLimited(context.Background(), coldLimits, func(_ context.Context, body []byte) error {
		calls++
		maxBytes = max(maxBytes, len(body))
		if len(body) > coldLimits.MaxBytes || !json.Valid(body) {
			t.Fatal("invalid bounded JSON")
		}
		return nil
	})
	if err != nil || ack != 1000 || calls < 20 {
		t.Fatal(ack, err, calls)
	}
	fmt.Printf("escaping description_bytes=1024 records=%d batches=%d max_batch_bytes=%d\n", ack, calls, maxBytes)
}

func TestLimitedExportStartsAfterSlowSink(t *testing.T) {
	s := NewStore(time.Hour, 3, 1, nil)
	for i := 0; i < 3; i++ {
		e := fixture(i, "metric", 64)
		s.Observe(e.Key, e.Value)
	}
	now := time.Now()
	useLogicalClock(s, &now)
	var starts []time.Time
	ack, err := s.FlushLimited(context.Background(), coldLimits, func(context.Context, []byte) error {
		starts = append(starts, now)
		now = now.Add(250 * time.Millisecond)
		return nil
	})
	if err != nil || ack != 3 || len(starts) != 3 {
		t.Fatal(ack, err)
	}
	for i := 1; i < len(starts); i++ {
		if gap := starts[i].Sub(starts[i-1]); gap != 250*time.Millisecond {
			t.Fatalf("starts are %v apart; should not wait another 100ms after completion", gap)
		}
	}
}
