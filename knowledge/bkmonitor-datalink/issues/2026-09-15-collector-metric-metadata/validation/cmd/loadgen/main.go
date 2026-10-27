// loadgen 从 stdin 读取配置，从集群内发送 OTLP 指标并记录采集端资源和元信息统计。
// Token 只用于请求头，不写入结果；Warmup 指定不计入结果的预热秒数。
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Config struct {
	Target, Admin, Token, Service, Group, Mode      string
	Seconds, Warmup, RPS, Metrics, Services, Groups int
	ScrapeSeconds, DataID                           int
}
type Sample struct {
	Time   float64            `json:"time"`
	Values map[string]float64 `json:"values"`
}

var client = &http.Client{Timeout: 10 * time.Second}

func scrape(c Config) (Sample, error) {
	r, e := client.Get(c.Admin + "/metrics")
	if e != nil {
		return Sample{}, e
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return Sample{}, fmt.Errorf("scrape HTTP %d", r.StatusCode)
	}
	v := map[string]float64{}
	s := bufio.NewScanner(r.Body)
	s.Buffer(make([]byte, 4096), 1024*1024)
	for s.Scan() {
		line := s.Text()
		if strings.HasPrefix(line, "bk_collector_metric_metadata_info{") {
			v["info_series"]++
			continue
		}
		if strings.HasPrefix(line, "#") {
			continue
		}
		f := strings.Fields(line)
		if len(f) < 2 {
			continue
		}
		name := f[0]
		n, err := strconv.ParseFloat(f[1], 64)
		if err != nil {
			continue
		}
		if strings.Contains(name, `record_type="metrics"`) {
			switch {
			case strings.HasPrefix(name, "bk_collector_exporter_queue_pop_batch_size_sum{") && strings.Contains(name, fmt.Sprintf(`id="%d"`, c.DataID)):
				v["dataid_output_points_total"] += n
			case strings.HasPrefix(name, "bk_collector_pipeline_dropped_total{") && strings.Contains(name, fmt.Sprintf(`id="%d"`, c.DataID)):
				v["dataid_pipeline_dropped_total"] += n
			case strings.HasPrefix(name, "bk_collector_throttle_requests_total{") && strings.Contains(name, `decision="denied"`):
				v["metrics_throttle_denied_total"] += n
			case strings.HasPrefix(name, "bk_collector_receiver_precheck_failed_total{") && strings.Contains(name, `token="`+c.Token+`"`):
				v["metrics_precheck_failed_total"] += n
			case strings.HasPrefix(name, "bk_collector_receiver_dropped_total{"):
				v["metrics_receiver_dropped_total"] += n
			case strings.HasPrefix(name, "bk_collector_receiver_internal_error_total{"):
				v["metrics_receiver_errors_total"] += n
			}
		}
		if strings.HasPrefix(name, "bk_collector_metric_metadata_") || name == "process_cpu_seconds_total" || name == "process_resident_memory_bytes" || name == "go_memstats_heap_alloc_bytes" {
			v[name] = n
		}
	}
	return Sample{float64(time.Now().UnixNano()) / 1e9, v}, s.Err()
}
func body(c Config, index int) []byte {
	version := 0
	if c.Mode == "churn" {
		version = index
	}
	metrics := make([]any, 0, c.Metrics)
	stamp := "1111111111111111111"
	service, group := c.Service, c.Group
	if c.Services > 1 {
		service = fmt.Sprintf("%s-%02d", c.Service, index/c.Groups%c.Services)
	}
	if c.Groups > 1 {
		group = fmt.Sprintf("%s-%02d", c.Group, index%c.Groups)
	}
	for i := 0; i < c.Metrics; i++ {
		metrics = append(metrics, map[string]any{"name": fmt.Sprintf("metricmeta_acceptance_%d", i), "description": fmt.Sprintf("acceptance version %d", version), "unit": "1", "gauge": map[string]any{"dataPoints": []any{map[string]any{"asDouble": i, "timeUnixNano": stamp}}}})
	}
	data := map[string]any{"resourceMetrics": []any{map[string]any{"resource": map[string]any{"attributes": []any{map[string]any{"key": "service.name", "value": map[string]any{"stringValue": service}}}}, "scopeMetrics": []any{map[string]any{"scope": map[string]any{"name": group}, "metrics": metrics}}}}}
	b, _ := json.Marshal(data)
	return b
}
func main() {
	var c Config
	if e := json.NewDecoder(os.Stdin).Decode(&c); e != nil {
		panic(e)
	}
	if c.ScrapeSeconds == 0 {
		c.ScrapeSeconds = 30
	}
	if c.Services == 0 {
		c.Services = 1
	}
	if c.Groups == 0 {
		c.Groups = 1
	}
	if c.Group == "" {
		c.Group = "metricmeta.acceptance"
	}
	if c.ScrapeSeconds < 1 || c.ScrapeSeconds > 60 || c.RPS < 1 || c.RPS > 1000 || c.Seconds < 1 || c.Seconds > 1800 || c.Warmup < 0 || c.Warmup >= c.Seconds || c.Metrics < 1 || c.Metrics > 10000 || c.Services < 1 || c.Services > 100 || c.Groups < 1 || c.Groups > 100 || c.Services*c.Groups*c.Metrics > 1000000 || c.Service == "" || c.Token == "" || !(strings.HasPrefix(c.Target, "http://") || strings.HasPrefix(c.Target, "https://")) {
		panic("invalid load bounds")
	}
	payloads := make([][]byte, c.Services*c.Groups)
	if c.Mode != "churn" {
		for i := range payloads {
			payloads[i] = body(c, i)
		}
	}
	first, e := scrape(c)
	if e != nil {
		panic(e)
	}
	samples := []Sample{first}
	stop := make(chan struct{})
	done := make(chan struct{})
	go func() {
		defer close(done)
		t := time.NewTicker(time.Duration(c.ScrapeSeconds) * time.Second)
		defer t.Stop()
		for {
			select {
			case <-stop:
				return
			case <-t.C:
				s, e := scrape(c)
				if e == nil {
					samples = append(samples, s)
				}
			}
		}
	}()
	codes := map[string]int{}
	latency := []float64{}
	partial := 0
	var mu sync.Mutex
	var wg sync.WaitGroup
	slots := make(chan struct{}, 8)
	start := time.Now()
	for i := 0; i < c.Seconds*c.RPS; i++ {
		time.Sleep(time.Until(start.Add(time.Duration(i) * time.Second / time.Duration(c.RPS))))
		slots <- struct{}{}
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			defer func() { <-slots }()
			b := payloads[i%len(payloads)]
			if c.Mode == "churn" {
				b = body(c, i)
			}
			b = bytes.ReplaceAll(b, []byte("1111111111111111111"), []byte(strconv.FormatInt(time.Now().UnixNano(), 10)))
			req, err := http.NewRequest("POST", c.Target+"/v1/metrics", bytes.NewReader(b))
			if err != nil {
				panic(err)
			}
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("X-BK-TOKEN", c.Token)
			now := time.Now()
			r, e := client.Do(req)
			code := "transport_error"
			p := false
			if e == nil {
				code = strconv.Itoa(r.StatusCode)
				b, _ := io.ReadAll(io.LimitReader(r.Body, 4096))
				r.Body.Close()
				var x map[string]any
				_ = json.Unmarshal(b, &x)
				_, p = x["partialSuccess"]
			}
			if i >= c.Warmup*c.RPS {
				mu.Lock()
				codes[code]++
				latency = append(latency, float64(time.Since(now))/float64(time.Millisecond))
				if p {
					partial++
				}
				mu.Unlock()
			}
		}(i)
	}
	wg.Wait()
	close(stop)
	<-done
	last, e := scrape(c)
	if e != nil {
		panic(e)
	}
	samples = append(samples, last)
	selected := samples[:0]
	for _, s := range samples {
		if s.Time >= first.Time+float64(c.Warmup) {
			selected = append(selected, s)
		}
	}
	samples = selected
	if len(samples) == 0 {
		panic("no measurement samples")
	}
	first = samples[0]
	peak := map[string]float64{}
	for _, s := range samples {
		for k, v := range s.Values {
			if v > peak[k] {
				peak[k] = v
			}
		}
	}
	sort.Float64s(latency)
	p99 := 0.
	if len(latency) > 0 {
		p99 = latency[int(math.Ceil(float64(len(latency))*.99))-1]
	}
	out := map[string]any{"service": c.Service, "group": c.Group, "services": c.Services, "groups_per_service": c.Groups, "metrics_per_group": c.Metrics, "metadata_keys": c.Services * c.Groups * c.Metrics, "target_rps": c.RPS, "scrape_seconds": c.ScrapeSeconds, "measurement_seconds": c.Seconds - c.Warmup, "actual_rps": float64(len(latency)) / (time.Since(start).Seconds() - float64(c.Warmup)), "samples": samples, "mode": c.Mode, "requests": len(latency), "points": len(latency) * c.Metrics, "status": codes, "partial_success": partial, "p99_ms": p99, "first": first, "last": last, "peak": peak, "average_cores": (last.Values["process_cpu_seconds_total"] - first.Values["process_cpu_seconds_total"]) / (last.Time - first.Time)}
	_ = json.NewEncoder(os.Stdout).Encode(out)
}
