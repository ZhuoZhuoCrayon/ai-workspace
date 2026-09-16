// Package protocolcheck checks upstream protocol behavior without importing collector.
package protocolcheck

import (
	"bytes"
	"io"
	"testing"

	"github.com/gogo/protobuf/proto"
	"github.com/prometheus/prometheus/model/labels"
	"github.com/prometheus/prometheus/model/textparse"
	"github.com/prometheus/prometheus/prompb"
)

func TestCounterFamilyNameAmbiguity(t *testing.T) {
	fixtures := []struct {
		name, contentType, body, wantSeries string
	}{
		{"prometheus-text", "text/plain;version=0.0.4", "# TYPE requests counter\nrequests 17\n", "requests"},
		{"openmetrics", "application/openmetrics-text;version=1.0.0", "# TYPE requests counter\nrequests_total 17\n# EOF\n", "requests_total"},
	}
	var previous []byte
	for _, f := range fixtures {
		p, err := textparse.New([]byte(f.body), f.contentType)
		if err != nil {
			t.Fatal(err)
		}
		family, series := "", ""
		for {
			entry, err := p.Next()
			if err == io.EOF {
				break
			}
			if err != nil {
				t.Fatal(err)
			}
			switch entry {
			case textparse.EntryType:
				name, kind := p.Type()
				family = string(name)
				if kind != textparse.MetricTypeCounter {
					t.Fatal(kind)
				}
			case textparse.EntrySeries:
				var ls labels.Labels
				p.Metric(&ls)
				series = ls.Get(labels.MetricName)
			}
		}
		if family != "requests" || series != f.wantSeries {
			t.Fatalf("%s: family=%s series=%s", f.name, family, series)
		}
		// Mirrors QueueManager.AppendMetadata: the original exposition format and
		// TimeSeries labels are not fields of MetricMetadata.
		wire, err := proto.Marshal(&prompb.WriteRequest{Metadata: []prompb.MetricMetadata{{MetricFamilyName: family, Type: prompb.MetricMetadata_COUNTER}}})
		if err != nil {
			t.Fatal(err)
		}
		if previous != nil && !bytes.Equal(previous, wire) {
			t.Fatal("expected identical metadata-only requests")
		}
		previous = wire
		t.Logf("%s: family=%s series=%s metadata_wire=%x", f.name, family, series, wire)
	}
}

func TestMetadataOnlyRequest(t *testing.T) {
	want := prompb.MetricMetadata{MetricFamilyName: "duration_seconds", Type: prompb.MetricMetadata_HISTOGRAM, Help: "Request duration", Unit: "seconds"}
	wire, err := proto.Marshal(&prompb.WriteRequest{Metadata: []prompb.MetricMetadata{want}})
	if err != nil {
		t.Fatal(err)
	}
	var got prompb.WriteRequest
	if err := proto.Unmarshal(wire, &got); err != nil {
		t.Fatal(err)
	}
	if len(got.Timeseries) != 0 || len(got.Metadata) != 1 || !proto.Equal(&got.Metadata[0], &want) {
		t.Fatal("metadata-only round trip failed")
	}
	t.Logf("metadata=%d timeseries=%d family=%s unit=%s", len(got.Metadata), len(got.Timeseries), got.Metadata[0].MetricFamilyName, got.Metadata[0].Unit)
}
