package metadata

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"strings"
	"sync"
	"time"
)

type pendingValue struct {
	Value Value
	Force bool
}

// BloomStore trades exact last-value knowledge for bounded membership memory.
// Only pending/snapshot retain full values. Force survives until the latest value
// is acknowledged; the independent periodic snapshot bypasses membership checks.
type BloomStore struct {
	oversizeDrops      uint64
	mu, flushMu        sync.Mutex
	pending            map[Key]pendingValue
	filter             *bloom
	versions, capacity int
	generation         uint64
	ttl                time.Duration
	nextForce          time.Time
	limit, batchSize   int
	export             ExportFunc
	now                func() time.Time
	wait               func(context.Context, time.Duration) error
	lastStart          time.Time
}

func NewBloomStore(ttl time.Duration, limit, batchSize, capacity int, probability float64, export ExportFunc) *BloomStore {
	if ttl <= 0 || limit <= 0 || batchSize <= 0 || capacity <= 0 || probability <= 0 || probability >= 1 {
		panic("invalid experiment configuration")
	}
	if export == nil {
		export = func(context.Context, []Entry) error { return ErrUnconfigured }
	}
	return &BloomStore{pending: make(map[Key]pendingValue), filter: newBloomWithProbability(capacity, probability), capacity: capacity, ttl: ttl, nextForce: time.Now(), limit: limit, batchSize: batchSize, export: export, now: time.Now, wait: waitContext}
}

func (s *BloomStore) Observe(k Key, v Value) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	old, exists := s.pending[k]
	if exists && old.Value == v {
		return true
	}
	if !exists && len(s.pending) >= s.limit {
		return false
	}
	k.ScopeType, k.Scope, k.Metric = strings.Clone(k.ScopeType), strings.Clone(k.Scope), strings.Clone(k.Metric)
	v.Name, v.Unit, v.Description = strings.Clone(v.Name), strings.Clone(v.Unit), strings.Clone(v.Description)
	v.Type, v.Temporality, v.Usage = strings.Clone(v.Type), strings.Clone(v.Temporality), strings.Clone(v.Usage)
	s.pending[k] = pendingValue{Value: v, Force: old.Force}
	return true
}

func (s *BloomStore) fingerprint(e Entry) [32]byte {
	var salted [40]byte
	binary.LittleEndian.PutUint64(salted[:8], s.generation)
	d := digest(e)
	copy(salted[8:], d[:])
	return sha256.Sum256(salted[:])
}

func (s *BloomStore) rotate() {
	clear(s.filter.bits)
	s.versions = 0
	s.generation++
}

func (s *BloomStore) restore(current map[Key]pendingValue) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for k, v := range current {
		if newer, exists := s.pending[k]; exists {
			newer.Force = newer.Force || v.Force
			s.pending[k] = newer
		} else if len(s.pending) < s.limit {
			s.pending[k] = v
		}
	}
}

func (s *BloomStore) deadlineError(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if deadline, ok := ctx.Deadline(); ok && !s.now().Before(deadline) {
		return context.DeadlineExceeded
	}
	return nil
}

func (s *BloomStore) Flush(ctx context.Context) (int, error) {
	return s.flush(ctx, ExportLimits{}, func(ctx context.Context, entries []Entry, _ []byte) error { return s.export(ctx, entries) })
}

func (s *BloomStore) FlushLimited(ctx context.Context, limits ExportLimits, export ExportJSONFunc) (int, error) {
	if limits.MaxBytes < 2 || limits.MinInterval < 0 {
		panic("invalid experiment export limits")
	}
	return s.flush(ctx, limits, func(ctx context.Context, _ []Entry, body []byte) error {
		if export == nil {
			return ErrUnconfigured
		}
		return export(ctx, body)
	})
}

func (s *BloomStore) flush(ctx context.Context, limits ExportLimits, export func(context.Context, []Entry, []byte) error) (int, error) {
	s.flushMu.Lock()
	defer s.flushMu.Unlock()
	s.mu.Lock()
	current := s.pending
	s.pending = make(map[Key]pendingValue)
	s.mu.Unlock()
	defer func() {
		if len(current) > 0 {
			s.restore(current)
		}
	}()
	if now := s.now(); !now.Before(s.nextForce) {
		s.rotate()
		for k, v := range current {
			v.Force = true
			current[k] = v
		}
		// Keep the cadence anchored, even after a long suspension or capacity rotation.
		s.nextForce = s.nextForce.Add((now.Sub(s.nextForce)/s.ttl + 1) * s.ttl)
	}
	batch := make([]Entry, 0, s.batchSize)
	var body []byte
	if limits.MaxBytes > 0 {
		body = []byte{'['}
	}
	total := 0
	send := func() error {
		if len(batch) == 0 {
			return nil
		}
		if err := s.deadlineError(ctx); err != nil {
			return err
		}
		if !s.lastStart.IsZero() && limits.MinInterval > 0 {
			if delay := s.lastStart.Add(limits.MinInterval).Sub(s.now()); delay > 0 {
				if err := s.wait(ctx, delay); err != nil {
					return err
				}
			}
		}
		if err := s.deadlineError(ctx); err != nil {
			return err
		}
		if limits.MaxBytes > 0 {
			body = append(body, ']')
		}
		s.lastStart = s.now()
		if err := export(ctx, batch, body); err != nil {
			return err
		}
		total += len(batch)
		for _, e := range batch {
			if s.versions == s.capacity {
				s.rotate()
			}
			s.filter.testAdd(s.fingerprint(e), true)
			s.versions++ // Conservative: duplicate forced acknowledgments also count.
			if current[e.Key].Force {
				s.mu.Lock()
				if newer, exists := s.pending[e.Key]; exists && newer.Value != e.Value {
					newer.Force = true
					s.pending[e.Key] = newer
				}
				s.mu.Unlock()
			}
			delete(current, e.Key)
		}
		batch = batch[:0]
		if limits.MaxBytes > 0 {
			body = body[:1]
		}
		return nil
	}
	for k, v := range current {
		if err := s.deadlineError(ctx); err != nil {
			return total, err
		}
		e := Entry{Key: k, Value: v.Value}
		if !v.Force && s.filter.testAdd(s.fingerprint(e), false) {
			delete(current, k)
			continue
		}
		if limits.MaxBytes > 0 {
			encoded, err := encodeEntry(e)
			if err != nil {
				return total, err
			}
			if len(encoded)+2 > limits.MaxBytes {
				delete(current, k)
				s.oversizeDrops++
				continue
			}
			comma := 0
			if len(batch) > 0 {
				comma = 1
			}
			if len(body)+comma+len(encoded)+1 > limits.MaxBytes {
				if err := send(); err != nil {
					return total, err
				}
			}
			if len(batch) > 0 {
				body = append(body, ',')
			}
			body = append(body, encoded...)
		}
		batch = append(batch, e)
		if len(batch) == s.batchSize {
			if err := send(); err != nil {
				return total, err
			}
		}
	}
	err := send()
	return total, err
}
