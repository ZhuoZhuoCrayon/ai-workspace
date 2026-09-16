package metadata

import "encoding/json"

// encodeEntry is the experiment's uncompressed JSON record, not a destination protocol.
// The batch body is a JSON array; callers include its brackets and commas in the byte limit.
func encodeEntry(e Entry) ([]byte, error) {
	var unit, description, interval, usage any
	if e.Value.Present&1 != 0 {
		unit = e.Value.Unit
	}
	if e.Value.Present&2 != 0 {
		description = e.Value.Description
	}
	if e.Value.Present&4 != 0 {
		interval = e.Value.Interval
	}
	if e.Value.Present&8 != 0 {
		usage = e.Value.Usage
	}
	return json.Marshal(map[string]any{
		"dataid": e.Key.DataID, "__scope_type": e.Key.ScopeType, "__scope": e.Key.Scope,
		"__metric": e.Key.Metric, "__name": e.Value.Name, "__unit": unit,
		"__description": description, "__type": e.Value.Type,
		"__temporality": e.Value.Temporality, "__usage": usage, "__interval": interval,
	})
}
