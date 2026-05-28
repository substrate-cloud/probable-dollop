# Examples

Copy-paste-able demos for the Substrate SDK. Set `SUBSTRATE_MCP_TOKEN`
in your environment (or run `substrate config init`) before any of these.

## Headline examples — start here

| File | What it shows |
|---|---|
| [`quickstart.py`](quickstart.py) | The shortest possible Substrate program. One line of business logic. |
| [`apply_lifecycle.py`](apply_lifecycle.py) | `plan` → `apply` → reuse → `destroy`. Proves idempotency. |
| [`prototype_to_yaml.py`](prototype_to_yaml.py) | Build a manifest in Python, dump it as YAML, commit to git. |
| [`idempotent_ci.py`](idempotent_ci.py) | CI-safe redeploy pattern with drift detection. |

## YAML manifests

| File | What it shows |
|---|---|
| [`manifests/minimal.yaml`](manifests/minimal.yaml) | Smallest valid manifest — `name`, `gpu`, `workload`, one safety net. |
| [`manifests/vllm-inference.yaml`](manifests/vllm-inference.yaml) | Production-shaped vLLM deploy: region preference, secrets, ports, health check, budget + max-runtime. |
| [`manifests/boot-script.yaml`](manifests/boot-script.yaml) | Boot-script workload (preview): plain GPU box with extras installed at boot. |

Deploy any of them:

```sh
substrate plan    examples/manifests/vllm-inference.yaml   # dry-run + cost
substrate apply   examples/manifests/vllm-inference.yaml   # idempotent launch
substrate destroy vllm-mistral                              # by manifest name
```

## Escape-hatch examples

The original imperative API still works. See [`launch_docker.py`](launch_docker.py)
and [`launch_boot_script.py`](launch_boot_script.py) for the typed-manager style.

## Before / after

[`before/`](before) and [`after/`](after) hold paired scripts that power the
"Adoption / friction" section of [`docs/FEATURE-METRICS.md`](../docs/FEATURE-METRICS.md).
The build script line-counts them and inserts the numbers.

## Conventions

- Every example sets at least one safety net (`budget`, `max_runtime`, or
  `idle_timeout`). `apply` refuses manifests without one by default.
- `$VAR` inside an `env:` value is shorthand for reading from the
  environment at submit time (`Secret.from_env(VAR)`). Use `\$literal`
  to pass a literal string that happens to start with `$`.
- All examples use `name:` as the identity key. Re-running `apply` with
  the same `name` is safe; re-running `instance launch --name x` is not.
