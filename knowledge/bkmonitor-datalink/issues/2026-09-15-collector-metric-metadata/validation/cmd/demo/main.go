// Command demo shows metadata coalescing with an in-memory export sink.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"time"

	metadata "collector-metadata-lab"
)

func main() {
	ttl := flag.Duration("ttl", 100*time.Millisecond, "forced refresh interval used by the demonstration")
	flag.Parse()
	if *ttl <= 0 {
		log.Fatal("ttl must be positive")
	}
	s := metadata.NewBloomStore(*ttl, 100, 10, 100000, 1e-6, func(_ context.Context, es []metadata.Entry) error {
		for _, e := range es {
			fmt.Printf("  export: dataid=%d scope=%s metric=%s unit=%s usage=%s\n", e.Key.DataID, e.Key.Scope, e.Key.Metric, e.Value.Unit, e.Value.Usage)
		}
		return nil
	})
	k := metadata.Key{DataID: 1001, ScopeType: "APM", Scope: "checkout-http", Metric: "request_latency"}
	v := metadata.Value{Name: "request.latency", Unit: "s", Type: "gauge", Temporality: "delta", Usage: "max", Present: 9}
	step := func(label string, want int) {
		fmt.Println(label)
		s.Observe(k, v)
		n, err := s.Flush(context.Background())
		if err != nil || n != want {
			log.Fatalf("got %d exported, err=%v; want %d", n, err, want)
		}
		fmt.Printf("  acknowledged: %d\n", n)
	}
	step("1. First observation", 1)
	step("2. Same metadata", 0)
	v.Unit = "ms"
	step("3. Unit changed", 1)
	v.Usage = "min"
	step("4. Usage changed", 1)
	time.Sleep(*ttl + 10*time.Millisecond)
	step("5. Same metadata at forced refresh", 1)
}
