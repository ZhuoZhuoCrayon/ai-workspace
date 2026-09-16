package metadata

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"
)

func useBloomLogicalClock(s *BloomStore, now *time.Time) {
	s.now = func() time.Time { return *now }
	s.nextForce = *now
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

func TestBloomStoreRepairsHistoricalVersion(t *testing.T) {
	now := time.Now()
	s := NewBloomStore(2*time.Hour, 10, 10, 100000, 1e-6, func(context.Context, []Entry) error { return nil })
	useBloomLogicalClock(s, &now)
	a := fixture(0, "metric", 64)
	b := a
	b.Value.Usage = "max"
	counts := make([]int, 0, 4)
	for _, e := range []Entry{a, b, a} {
		s.Observe(e.Key, e.Value)
		n, err := s.Flush(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		counts = append(counts, n)
	}
	now = now.Add(2 * time.Hour)
	s.Observe(a.Key, a.Value)
	n, err := s.Flush(context.Background())
	counts = append(counts, n)
	if err != nil || fmt.Sprint(counts) != "[1 1 0 1]" {
		t.Fatal(counts, err)
	}
	fmt.Println("bloom_store sequence=A,B,A,force_A exports=1,1,0,1")
}

func TestBloomStoreForceSurvivesDeadline(t *testing.T) {
	now := time.Now()
	s := NewBloomStore(2*time.Hour, 3, 1, 100, 1e-6, nil)
	useBloomLogicalClock(s, &now)
	for i := 0; i < 3; i++ {
		e := fixture(i, "metric", 64)
		s.Observe(e.Key, e.Value)
	}
	ctx, cancel := context.WithDeadline(context.Background(), now.Add(100*time.Millisecond))
	n, err := s.FlushLimited(ctx, coldLimits, func(context.Context, []byte) error { return nil })
	cancel()
	if n != 1 || !errors.Is(err, context.DeadlineExceeded) || len(s.pending) != 2 {
		t.Fatal(n, err)
	}
	for _, e := range s.pending {
		if !e.Force {
			t.Fatal("lost force across timeout")
		}
	}
	// Deterministically inject membership false positives; forced items must ignore them.
	for i := range s.filter.bits {
		s.filter.bits[i] = ^uint64(0)
	}
	now = now.Add(time.Minute)
	n, err = s.FlushLimited(context.Background(), coldLimits, func(context.Context, []byte) error { return nil })
	if n != 2 || err != nil || len(s.pending) != 0 {
		t.Fatal(n, err)
	}
}

func TestBloomStoreForcedAckTransfersToNewerValue(t *testing.T) {
	now := time.Now()
	a := fixture(0, "metric", 64)
	b := a
	b.Value.Usage = "max"
	var s *BloomStore
	calls := 0
	s = NewBloomStore(2*time.Hour, 10, 10, 100, 1e-6, func(context.Context, []Entry) error {
		calls++
		if calls == 1 {
			// B was seen earlier in this generation, while forced A is in flight.
			s.filter.testAdd(s.fingerprint(b), true)
			s.Observe(b.Key, b.Value)
		}
		return nil
	})
	useBloomLogicalClock(s, &now)
	s.Observe(a.Key, a.Value)
	if n, err := s.Flush(context.Background()); n != 1 || err != nil {
		t.Fatal(n, err)
	}
	if v := s.pending[b.Key]; v.Value != b.Value || !v.Force {
		t.Fatal("ack lost the newer value's force")
	}
	if n, err := s.Flush(context.Background()); n != 1 || err != nil {
		t.Fatal(n, err)
	}
}

func TestBloomStoreFailureRestoresForceToNewerValue(t *testing.T) {
	now := time.Now()
	a := fixture(0, "metric", 64)
	b := a
	b.Value.Usage = "max"
	var s *BloomStore
	s = NewBloomStore(2*time.Hour, 10, 10, 100, 1e-6, func(context.Context, []Entry) error {
		s.Observe(b.Key, b.Value)
		return errors.New("offline")
	})
	useBloomLogicalClock(s, &now)
	s.Observe(a.Key, a.Value)
	if n, err := s.Flush(context.Background()); n != 0 || err == nil {
		t.Fatal(n, err)
	}
	if v := s.pending[b.Key]; v.Value != b.Value || !v.Force || s.versions != 0 {
		t.Fatal("failure lost latest value/force or acknowledged it")
	}
}

func TestBloomStoreCapacityDoesNotDelayForce(t *testing.T) {
	now := time.Now()
	s := NewBloomStore(2*time.Hour, 10, 1, 2, 1e-6, func(context.Context, []Entry) error { return nil })
	useBloomLogicalClock(s, &now)
	for i := 0; i < 5; i++ {
		e := fixture(i, "metric", 64)
		s.Observe(e.Key, e.Value)
	}
	if n, err := s.Flush(context.Background()); n != 5 || err != nil {
		t.Fatal(n, err)
	}
	if s.versions > s.capacity || !s.nextForce.Equal(now.Add(2*time.Hour)) || s.generation != 3 {
		t.Fatal("capacity rotation changed cadence or exceeded capacity")
	}
	now = now.Add(2 * time.Hour)
	e := fixture(4, "metric", 64)
	s.Observe(e.Key, e.Value)
	if n, err := s.Flush(context.Background()); n != 1 || err != nil {
		t.Fatal(n, err)
	}
}

func TestBloomStoreOversizedDoesNotBlockOthers(t *testing.T) {
	s := NewBloomStore(time.Hour, 10, 10, 100, 1e-6, nil)
	large, valid := fixture(0, "metric", 1024), fixture(1, "metric", 64)
	s.Observe(large.Key, large.Value)
	s.Observe(valid.Key, valid.Value)
	ack, err := s.FlushLimited(context.Background(), ExportLimits{MaxBytes: 512}, func(_ context.Context, body []byte) error {
		if len(body) > 512 || !strings.Contains(string(body), valid.Key.Metric) {
			t.Fatal("wrong batch")
		}
		return nil
	})
	if ack != 1 || err != nil || s.oversizeDrops != 1 || len(s.pending) != 0 || s.versions != 1 {
		t.Fatal(ack, err, s.oversizeDrops)
	}
}

func TestBloomStoreConcurrentObserveAndFlush(t *testing.T) {
	exported := make(map[Key]Value)
	s := NewBloomStore(time.Hour, 100, 10, 100000, 1e-6, func(_ context.Context, batch []Entry) error {
		for _, e := range batch {
			exported[e.Key] = e.Value
		}
		return nil
	})
	var wg sync.WaitGroup
	for g := 0; g < 8; g++ {
		wg.Add(1)
		go func(g int) {
			defer wg.Done()
			for i := 0; i < 1000; i++ {
				s.Observe(Key{DataID: int32(g), Metric: "m"}, Value{Temporality: "delta", Interval: int64(i)})
			}
		}(g)
	}
	for i := 0; i < 20; i++ {
		s.Flush(context.Background())
	}
	wg.Wait()
	s.nextForce = s.now() // Complete any outstanding latest-value obligation without probabilistic suppression.
	s.Flush(context.Background())
	if len(exported) != 8 {
		t.Fatal("lost keys", len(exported))
	}
	for _, v := range exported {
		if v.Interval != 999 {
			t.Fatal("lost final update")
		}
	}
}
