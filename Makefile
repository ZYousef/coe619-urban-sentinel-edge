# Makefile

IMAGE_NAME := urban-sentinel-edge

# Pick host-IP on Darwin vs Linux
ifeq ($(shell uname -s),Darwin)
  ADVERTISE_ADDR := $(shell ipconfig getifaddr en0)
else
  ADVERTISE_ADDR := $(shell hostname -I 2>/dev/null | awk '{print $$1}')
endif

.PHONY: build run-bash simulate print-addr swarm-init swarm-up swarm-down

build:
	docker build -t $(IMAGE_NAME) .

run-bash:
	docker run -it --rm $(IMAGE_NAME) bash

simulate:
	@echo "Starting 100 edge-node containers…"
	@for i in $$(seq 1 100); do \
		docker run -d --rm --name edge_node_$$i $(IMAGE_NAME); \
	done

print-addr:
	@echo "ADVERTISE_ADDR=$(ADVERTISE_ADDR)"

swarm-init:
	@echo "Initializing Swarm manager on this host…"
	@docker swarm init --advertise-addr $(ADVERTISE_ADDR) || true

swarm-up: swarm-init
	@echo "Creating Swarm service 'edge-sim' with 10 replicas…"
	docker service create \
		--name edge-sim \
		--replicas 10 \
		$(IMAGE_NAME)

swarm-down:
	@echo "Removing Swarm service 'edge-sim'…"
	docker service rm edge-sim