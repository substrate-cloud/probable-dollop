# CLI command reference (examples)

All commands assume `substratecloud config init` or `SUBSTRATECLOUD_MCP_TOKEN` is set.

## Auth and inventory

```sh
substratecloud check
substratecloud show-gpus
substratecloud show-gpus --max-price 3
substratecloud inventory ls --gpu a100 --gpu-count 1
substratecloud inventory cheapest --gpu a4000
```

## Declarative deploy

```sh
substratecloud plan  examples/manifests/minimal-docker.yaml
substratecloud apply examples/manifests/minimal-docker.yaml
substratecloud apply examples/manifests/minimal-docker.yaml   # idempotent reuse
substratecloud apply examples/manifests/minimal-docker.yaml --force
substratecloud destroy minimal-docker
```

## Imperative instances

```sh
substratecloud instance launch --name exp-1 --gpu a4000 --yes
substratecloud instance ls
substratecloud instance get exp-1
substratecloud instance terminate exp-1 --yes
```

## Cost

```sh
substratecloud cost
substratecloud cost --tag manifest:minimal-docker
```

## One-shot run

```sh
substratecloud run workload.json --name exp-1 --gpu a4000
```

Billing stops only on `destroy` / `terminate`. The SDK does not stream instance logs.
