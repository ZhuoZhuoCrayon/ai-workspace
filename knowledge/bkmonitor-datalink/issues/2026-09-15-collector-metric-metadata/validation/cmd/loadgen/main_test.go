package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWorkloadIdentityCoverage(t *testing.T) {
	c := Config{Service: "load", Group: "group", Services: 10, Groups: 10, Metrics: 1000, Mode: "steady"}
	identities := map[string]bool{}
	for i := 0; i < c.Services*c.Groups; i++ {
		var decoded struct {
			ResourceMetrics []struct {
				Resource struct {
					Attributes []struct {
						Key   string
						Value struct{ StringValue string }
					}
				}
				ScopeMetrics []struct {
					Scope   struct{ Name string }
					Metrics []struct {
						Name        string
						Description string
					}
				}
			}
		}
		if err := json.Unmarshal(body(c, i), &decoded); err != nil {
			t.Fatal(err)
		}
		r := decoded.ResourceMetrics[0]
		service := r.Resource.Attributes[0].Value.StringValue
		s := r.ScopeMetrics[0]
		for _, m := range s.Metrics {
			identities[fmt.Sprintf("%s/%s/%s", service, s.Scope.Name, m.Name)] = true
		}
	}
	if len(identities) != 100000 {
		t.Fatalf("distinct metadata keys: %d", len(identities))
	}
}

func TestScrapeIsolatesMetricEvidenceAndOmitsCredentials(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		fmt.Fprintln(w, `bk_collector_exporter_queue_pop_batch_size_sum{id="7",record_type="metrics"} 20
bk_collector_exporter_queue_pop_batch_size_sum{id="8",record_type="metrics"} 900
bk_collector_exporter_queue_pop_batch_size_sum{id="7",record_type="traces"} 800
bk_collector_pipeline_dropped_total{id="7",record_type="metrics",processor="ratelimiter"} 4
bk_collector_pipeline_dropped_total{id="8",record_type="metrics",processor="ratelimiter"} 700
bk_collector_throttle_requests_total{decision="denied",record_type="traces"} 99
bk_collector_throttle_requests_total{decision="denied",record_type="metrics"} 2
bk_collector_receiver_precheck_failed_total{record_type="metrics",token="test-credential"} 3
bk_collector_receiver_precheck_failed_total{record_type="metrics",token="other"} 88`)
	}))
	defer server.Close()
	sample, err := scrape(Config{Admin: server.URL, DataID: 7, Token: "test-credential"})
	if err != nil {
		t.Fatal(err)
	}
	for k, want := range map[string]float64{"dataid_output_points_total": 20, "dataid_pipeline_dropped_total": 4, "metrics_throttle_denied_total": 2, "metrics_precheck_failed_total": 3} {
		if sample.Values[k] != want {
			t.Fatalf("%s: got %v, want %v", k, sample.Values[k], want)
		}
	}
	encoded, err := json.Marshal(sample)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "test-credential") || strings.Contains(string(encoded), "token=") {
		t.Fatal("credentials leaked into evidence")
	}
}
