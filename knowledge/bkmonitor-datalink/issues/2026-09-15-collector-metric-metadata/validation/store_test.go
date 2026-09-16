package metadata

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestRefreshAndReversion(t *testing.T) {
	now := time.Unix(0, 0)
	s := NewStore(2*time.Hour, 100, 10, func(context.Context, []Entry) error { return nil })
	s.now = func() time.Time { return now }
	k, a := Key{DataID: 1, ScopeType: "APM", Scope: "s-g", Metric: "m"}, Value{Name: "m", Unit: "s"}
	b := a
	b.Unit = "ms"
	check := func(want int) {
		t.Helper()
		n, err := s.Flush(context.Background())
		if err != nil || n != want {
			t.Fatalf("got %d, %v; want %d", n, err, want)
		}
	}
	s.Observe(k, a)
	check(1)
	now = now.Add(time.Hour)
	s.Observe(k, a)
	check(0)
	s.Observe(k, b)
	s.Observe(k, a)
	check(0)
	s.Observe(k, b)
	check(1)
	now = now.Add(time.Hour)
	s.Observe(k, b)
	check(0)
	now = now.Add(time.Hour)
	s.Observe(k, b)
	check(1)
}

func TestFailureDoesNotOverwriteNewer(t *testing.T) {
	k, a := Key{Metric: "m"}, Value{Unit: "s"}
	b := Value{Unit: "ms"}
	var s *Store
	s = NewStore(time.Hour, 100, 10, func(context.Context, []Entry) error { s.Observe(k, b); return errors.New("offline") })
	s.Observe(k, a)
	if n, err := s.Flush(context.Background()); n != 0 || err == nil {
		t.Fatal("expected failure")
	}
	if len(s.sent) != 0 || s.pending[k] != b {
		t.Fatal("failed export acknowledged or overwrote newer value")
	}
	s.export = func(_ context.Context, es []Entry) error {
		if len(es) != 1 || es[0].Value != b {
			t.Fatal(es)
		}
		return nil
	}
	if n, err := s.Flush(context.Background()); n != 1 || err != nil {
		t.Fatal(n, err)
	}
}

func TestBoundsAndUnconfigured(t *testing.T) {
	s := NewStore(time.Hour, 1, 1, nil)
	if !s.Observe(Key{Metric: "a"}, Value{}) || s.Observe(Key{Metric: "b"}, Value{}) {
		t.Fatal("limit")
	}
	if n, err := s.Flush(context.Background()); n != 0 || !errors.Is(err, ErrUnconfigured) || len(s.sent) != 0 {
		t.Fatal(n, err)
	}
	if !s.Observe(Key{Metric: "a"}, Value{Unit: "s"}) {
		t.Fatal("existing key update blocked")
	}
}

func TestMissingVersusExplicitEmpty(t *testing.T) {
	s := NewStore(time.Hour, 10, 10, func(context.Context, []Entry) error { return nil })
	k := Key{Metric: "m"}
	s.Observe(k, Value{})
	s.Flush(context.Background())
	s.Observe(k, Value{Present: 2}) // Explicit empty description differs from unknown.
	if n, err := s.Flush(context.Background()); n != 1 || err != nil {
		t.Fatal(n, err)
	}
}

func TestConcurrentObserveAndFlush(t *testing.T) {
	s := NewStore(time.Hour, 100, 10, func(context.Context, []Entry) error { return nil })
	var wg sync.WaitGroup
	for g := 0; g < 8; g++ {
		wg.Add(1)
		go func(g int) {
			defer wg.Done()
			for i := 0; i < 1000; i++ {
				s.Observe(Key{DataID: int32(g), Metric: "m"}, Value{Interval: int64(i)})
			}
		}(g)
	}
	for i := 0; i < 20; i++ {
		s.Flush(context.Background())
	}
	wg.Wait()
	s.Flush(context.Background())
	if len(s.sent) != 8 {
		t.Fatalf("got %d final keys; want 8", len(s.sent))
	}
	for _, v := range s.sent {
		if v.Value.Interval != 999 {
			t.Fatal("lost final update")
		}
	}
}

// Usage is a default query aggregation, independent of the physical metric type.
func TestUsageAndTemporalityChanges(t *testing.T) {
	for _, field := range []string{"usage", "temporality"} {
		t.Run(field, func(t *testing.T) {
			var exported []Entry
			s := NewStore(time.Hour, 10, 10, func(_ context.Context, batch []Entry) error {
				exported = append(exported, batch...)
				return nil
			})
			e := fixture(0, "metric", 64)
			e.Value.Type, e.Value.Usage = "gauge", "max"
			s.Observe(e.Key, e.Value)
			if n, err := s.Flush(context.Background()); n != 1 || err != nil {
				t.Fatal(n, err)
			}
			before := e
			if field == "usage" {
				e.Value.Usage = "min"
			} else {
				e.Value.Temporality = "cumulative"
			}
			if digest(before) == digest(e) || valueDigest(before.Value) == valueDigest(e.Value) {
				t.Fatal("changed field omitted from cache digest")
			}
			s.Observe(e.Key, e.Value)
			if n, err := s.Flush(context.Background()); n != 1 || err != nil {
				t.Fatal(n, err)
			}
			s.Observe(e.Key, e.Value)
			if n, err := s.Flush(context.Background()); n != 0 || err != nil {
				t.Fatal(n, err)
			}
			if len(exported) != 2 || exported[1].Value != e.Value {
				t.Fatal(exported)
			}
		})
	}
}
