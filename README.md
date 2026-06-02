# SubstrateCloud Python SDK & CLI

Typed, composable Python SDK and command-line interface for the [SubstrateCloud](https://substratecloud.ai) On-Demand GPU platform.

> **Status:** alpha (v0.1.0). Layers 1–3 (HTTP, models, resources) and a Typer CLI are stable. Workload abstractions (Docker / BootScript) ship as previews — the boot-script `launch_configuration` shape is not yet documented by the API and may change.

## Install

```sh
# Full install (recommended) — SDK + CLI
pip install "substratecloud[cli]"

# SDK only
pip install substratecloud
```

## Examples

See [`examples/README.md`](examples/README.md) for YAML manifests, Python recipes (`01`–`14`),
and a CLI cheat sheet. CI validates every example without launching GPUs.

## Quick start (CLI)

```sh
# Interactive: enter MCP token, API base URL, default region
substratecloud config init

# Inventory
substratecloud inventory ls --gpu h100 --max-price 3
substratecloud inventory cheapest --gpu a100

# Launch
substratecloud instance launch --gpu a100 --name exp-1
substratecloud instance ls
substratecloud instance terminate exp-1

# Full lifecycle (launch → wait → run workload → cleanup)
substratecloud run ./workload.yaml --gpu h100 --name exp-1
```

The first `substratecloud config init` writes a TOML file to `~/.config/substratecloud/config.toml`. You can also point at it with `SUBSTRATECLOUD_MCP_TOKEN` / `SUBSTRATECLOUD_API_BASE_URL` env vars, or pass `--token` / `--base-url` on every command.

## Quick start (SDK)

```python
from substratecloud import SubstrateCloud

client = SubstrateCloud()  # picks up token from env or config

# 1. Find capacity
item = client.inventory.find_cheapest(gpu_type="A100")

# 2. Launch
instance = client.instances.create(
    inventory_gpu_id=item.id,
    name="exp-1",
)

# 3. Wait
client.instances.wait_until_active(instance.id, timeout=600)

# 4. Use it (SSH via ip_address) ...

# 5. Stop billing
client.instances.delete(instance.id)
```

### One-shot with a Docker workload

```python
from substratecloud import SubstrateCloud, DockerWorkload, Secret

client = SubstrateCloud()

wl = DockerWorkload(
    image="vllm/vllm-openai:latest",
    args=["--model", "mistralai/Mistral-7B-v0.1"],
    env={"HF_TOKEN": Secret.from_env("HF_TOKEN")},
    ports={8000: 8000},
)

inst = client.run(
    workload=wl,
    gpu="A100",
    name="vllm-mistral",
    tags=["team:platform"],
)
print("Endpoint:", inst.endpoint)
```

## Architecture

Six layers, each independently usable:

| Layer | Module | What it does |
|---|---|---|
| 6 | `substratecloud.cli` | Typer-based CLI |
| 5 | `substratecloud.orchestration` | `JobRunner`, `InstancePool` (planned) |
| 4 | `substratecloud.workloads` | `DockerWorkload`, `BootScript`, presets |
| 3 | `substratecloud.resources` | `inventory`, `instances`, `ssh_keys` managers |
| 2 | `substratecloud.models` | Pydantic v2 resource types |
| 1 | `substratecloud._http` | httpx client with auth, retries, errors |

See [docs/architecture.md](docs/architecture.md) for the detailed plan.

## Cost safety

Billing starts on `POST /instances` and only stops on `DELETE`. The SDK is designed around this:

- **`POST /instances` is never auto-retried** — the SDK surfaces the error and lets you decide. Retrying a 5xx on launch is how you end up paying for two instances.
- **`apply` requires `budget_limit_usd`** in the manifest (or `--no-safety-net`). The budget is an audit tag only — billing stops on `substratecloud destroy`.
- **CLI prints estimated daily/weekly spend** on every `launch`.

> The SubstrateCloud API has a `max 3 active tokens per org` limit. Tokens are org-scoped, not user-scoped. The SDK auto-tags every launch with `actor:<user>` and `trace:<uuid>` so internal audit can attribute, but for SOC2-grade attribution you need a broker in front of the SDK. See `docs/recipes/multi-user-attribution.md`.

## Secrets

The `Secret` type is a sentinel — it never appears in `__repr__`, gets resolved (env / Vault / AWS SM / GCP SM) at the point of API submission, and is redacted from structured logs.

```python
from substratecloud import Secret

Secret.from_env("HF_TOKEN")                     # read at submit time
Secret.from_vault("kv/data/substrate#hf_token") # any callable provider
Secret.literal("hf_xxx")                        # tests/dev only — warned
```

Note: the SubstrateCloud API persists `launch_configuration` server-side, so any secret rendered into a launch payload is recoverable via `GET /instance/:id`. Prefer the "fetch at boot" pattern for production — see `docs/recipes/secrets.md`.

## Open questions tracked against the API

The SDK ships with `Docker` workloads fully supported (documented API path). The following items are flagged inline in the code as `# API-OPEN-QUESTION` and may change:

1. Non-Docker `launch_configuration` shape (`type: "script"` field name and structure).
2. Boot-script logs endpoint — use SSH outside the SDK until the API exposes logs.
3. Webhooks / event streaming — currently polling-only.
4. Server-side `max_runtime` / `max_spend` enforcement.
5. Instance metadata service (for self-identifying status beacons).

See [docs/architecture.md §11](docs/architecture.md) for the full list.

## Development

```sh
git clone https://github.com/substrate-ai/substrate-sdk
cd substrate-sdk
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,cli]"

ruff check src tests
mypy src
pytest
```

Integration tests are opt-in and require a real MCP token:

```sh
SUBSTRATECLOUD_MCP_TOKEN=mcp_... pytest -m integration
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
