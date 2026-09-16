.PHONY: test demo bench experiment bloom bloom-store sent buffer

test:
	go test -race ./...
	go vet ./...

demo:
	go run ./cmd/demo

bench:
	go test -run '^$$' -bench 'Benchmark(Lookup|Observe)$$' -benchmem -benchtime=200ms -count=3

experiment:
	bash run.sh

bloom:
	bash bloom.sh

bloom-store:
	bash bloom-store.sh

sent:
	bash performance.sh sent

buffer:
	bash performance.sh buffer
