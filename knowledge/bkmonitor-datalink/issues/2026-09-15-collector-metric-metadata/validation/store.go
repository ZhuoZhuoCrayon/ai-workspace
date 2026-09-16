// Package metadata is an isolated design experiment, not collector production code.
package metadata

import (
	"context"
	"errors"
	"strings"
	"sync"
	"time"
)

type Key struct {
	DataID    int32
	ScopeType string
	Scope     string
	Metric    string
}

type Value struct {
	Name        string
	Unit        string
	Description string
	Type        string
	Temporality string
	Usage       string
	Interval    int64
	Present     uint8 // bit 0: unit; bit 1: description; bit 2: interval; bit 3: usage
}

type Entry struct {
	Key   Key
	Value Value
}

type sentEntry struct {
	Value   Value
	Expires time.Time
}

var ErrUnconfigured = errors.New("metadata export is not configured")

type ExportFunc func(context.Context, []Entry) error

// Store coalesces observations; only the serialized Flush accesses sent.
type Store struct {
	mu        sync.Mutex
	flushMu   sync.Mutex
	pending   map[Key]Value
	sent      map[Key]sentEntry
	ttl       time.Duration
	limit     int
	batchSize int
	export    ExportFunc
	now       func() time.Time
	wait      func(context.Context, time.Duration) error
	lastStart time.Time
}

func NewStore(ttl time.Duration, limit, batchSize int, export ExportFunc) *Store {
	if ttl <= 0 || limit <= 0 || batchSize <= 0 {
		panic("invalid experiment configuration")
	}
	if export == nil {
		export = func(context.Context, []Entry) error { return ErrUnconfigured }
	}
	return &Store{pending: make(map[Key]Value), sent: make(map[Key]sentEntry), ttl: ttl, limit: limit, batchSize: batchSize, export: export, now: time.Now, wait: waitContext}
}

// Observe owns copied strings on insertion/change, so request buffers can be freed.
// A full pending map refuses only previously unseen keys.
func (s *Store) Observe(k Key, v Value) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	old, ok := s.pending[k]
	if ok && old == v {
		return true
	}
	if !ok && len(s.pending) >= s.limit {
		return false
	}
	k.ScopeType, k.Scope, k.Metric = strings.Clone(k.ScopeType), strings.Clone(k.Scope), strings.Clone(k.Metric)
	v.Name, v.Unit, v.Description = strings.Clone(v.Name), strings.Clone(v.Unit), strings.Clone(v.Description)
	v.Type, v.Temporality, v.Usage = strings.Clone(v.Type), strings.Clone(v.Temporality), strings.Clone(v.Usage)
	s.pending[k] = v
	return true
}

// ExportLimits bounds the actual uncompressed JSON body and Export start frequency.
type ExportLimits struct {
	MaxBytes    int
	MinInterval time.Duration
}

type ExportJSONFunc func(context.Context, []byte) error

var ErrEntryTooLarge = errors.New("metadata entry exceeds batch byte limit")

func waitContext(ctx context.Context, duration time.Duration) error {
	timer := time.NewTimer(duration)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// Flush measures cache processing without encoding or pacing.
func (s *Store) Flush(ctx context.Context) (int, error) {
	return s.flush(ctx, ExportLimits{}, func(ctx context.Context, entries []Entry, _ []byte) error {
		return s.export(ctx, entries)
	})
}

// FlushLimited uses the same cache transitions, but sends bounded JSON payloads.
// The caller sets a deadline for the whole round. Export must obey that context.
func (s *Store) FlushLimited(ctx context.Context, limits ExportLimits, export ExportJSONFunc) (int, error) {
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

func (s *Store) deadlineError(ctx context.Context) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	// The explicit clock check also supports deterministic deadline experiments.
	if deadline, ok := ctx.Deadline(); ok && !s.now().Before(deadline) {
		return context.DeadlineExceeded
	}
	return nil
}

func (s *Store) restore(entries map[Key]Value) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for k, v := range entries {
		if _, exists := s.pending[k]; !exists && len(s.pending) < s.limit {
			s.pending[k] = v
		}
	}
}

// A single serialized Flush owns sent. Failure/timeout returns unsent values only
// when no newer observation exists; acknowledged batches remain in sent.
func (s *Store) flush(ctx context.Context, limits ExportLimits, export func(context.Context, []Entry, []byte) error) (int, error) {
	s.flushMu.Lock()
	defer s.flushMu.Unlock()
	s.mu.Lock()
	current := s.pending
	s.pending = make(map[Key]Value)
	s.mu.Unlock()
	defer func() {
		if len(current) > 0 {
			s.restore(current)
		}
	}()
	now := s.now()
	for k, v := range s.sent {
		if !now.Before(v.Expires) {
			delete(s.sent, k)
		}
	}
	if len(s.sent) == 0 {
		s.sent = make(map[Key]sentEntry)
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
		if limits.MinInterval > 0 && !s.lastStart.IsZero() {
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
			delete(current, e.Key)
			if _, exists := s.sent[e.Key]; exists || len(s.sent) < s.limit {
				s.sent[e.Key] = sentEntry{e.Value, s.now().Add(s.ttl)}
			}
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
		if old, ok := s.sent[k]; ok && now.Before(old.Expires) && old.Value == v {
			delete(current, k)
			continue
		}
		var encoded []byte
		if limits.MaxBytes > 0 {
			var err error
			encoded, err = encodeEntry(Entry{k, v})
			if err != nil {
				return total, err
			}
			if len(encoded)+2 > limits.MaxBytes {
				return total, ErrEntryTooLarge
			}
			// Current '[' + candidate + optional comma + closing ']'.
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
		batch = append(batch, Entry{k, v})
		if len(batch) == s.batchSize {
			if err := send(); err != nil {
				return total, err
			}
		}
	}
	err := send()
	return total, err
}
