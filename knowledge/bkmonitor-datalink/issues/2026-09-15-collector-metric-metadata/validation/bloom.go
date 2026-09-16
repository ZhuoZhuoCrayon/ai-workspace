package metadata

import (
	"crypto/sha256"
	"encoding/binary"
	"math"
)

// Canonical length-prefix encoding covers every key/value field without ambiguity.
func digest(e Entry) [32]byte {
	buf := make([]byte, 0, 256+len(e.Value.Description))
	buf = binary.LittleEndian.AppendUint32(buf, uint32(e.Key.DataID))
	for _, v := range []string{e.Key.ScopeType, e.Key.Scope, e.Key.Metric, e.Value.Name, e.Value.Unit, e.Value.Description, e.Value.Type, e.Value.Temporality, e.Value.Usage} {
		buf = binary.LittleEndian.AppendUint32(buf, uint32(len(v)))
		buf = append(buf, v...)
	}
	buf = binary.LittleEndian.AppendUint64(buf, uint64(e.Value.Interval))
	buf = append(buf, e.Value.Present)
	return sha256.Sum256(buf)
}

func valueDigest(v Value) [32]byte {
	buf := make([]byte, 0, 128+len(v.Description))
	for _, s := range []string{v.Name, v.Unit, v.Description, v.Type, v.Temporality, v.Usage} {
		buf = binary.LittleEndian.AppendUint32(buf, uint32(len(s)))
		buf = append(buf, s...)
	}
	buf = binary.LittleEndian.AppendUint64(buf, uint64(v.Interval))
	buf = append(buf, v.Present)
	return sha256.Sum256(buf)
}

// Bloom is a standard double-hashing experiment, not the bits-and-blooms library.
type bloom struct {
	bits []uint64
	k    uint64
}

func newBloom(n int) *bloom { return newBloomWithProbability(n, .01) }

func newBloomWithProbability(n int, probability float64) *bloom {
	m := uint64(math.Ceil(-float64(n) * math.Log(probability) / (math.Ln2 * math.Ln2)))
	k := uint64(math.Round(float64(m) / float64(n) * math.Ln2))
	return &bloom{make([]uint64, (m+63)/64), k}
}
func (b *bloom) testAdd(h [32]byte, add bool) bool {
	a, step := binary.LittleEndian.Uint64(h[:8]), binary.LittleEndian.Uint64(h[8:16])|1
	present := true
	for i := uint64(0); i < b.k; i++ {
		p := (a + i*step) % uint64(len(b.bits)*64)
		mask := uint64(1) << (p % 64)
		if b.bits[p/64]&mask == 0 {
			present = false
		}
		if add {
			b.bits[p/64] |= mask
		}
	}
	return present
}
