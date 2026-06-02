# CLI command reference (examples)

All commands assume `substrate config init` or `SUBSTRATE_MCP_TOKEN` is set.

## Auth and inventory

```sh
substrate check
substrate show-gpus
substrate show-gpus --max-price 3
substrate inventory ls --gpu a100 --gpu-count 1
substrate inventory cheapest --gpu a4000
```

## Declarative deploy

```sh
substrate plan  examples/manifests/minimal-docker.yaml
substrate apply examples/manifests/minimal-docker.yaml
substrate apply examples/manifests/minimal-docker.yaml   # idempotent reuse
substrate apply examples/manifests/minimal-docker.yaml --force
substrate destroy minimal-docker
```

## Imperative instances

```sh
substrate instance launch --name exp-1 --gpu a4000 --yes
substrate instance ls
substrate instance get exp-1
substrate instance terminate exp-1 --yes
```

## Cost

```sh
substrate cost
substrate cost --tag manifest:minimal-docker
```

## One-shot run

```sh
substrate run workload.json --name exp-1 --gpu a4000
```

Billing stops only on `destroy` / `terminate`. The SDK does not stream instance logs.
