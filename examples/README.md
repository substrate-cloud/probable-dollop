# Substrate SDK examples

Runnable recipes for the Python SDK and CLI. All examples are validated in CI via
`tests/test_examples.py` (manifest parsing + dry-run `plan` without billing).

## Setup

```sh
pip install "substrate[cli]"
substrate config init
# or:
export SUBSTRATE_MCP_TOKEN=mcp_...
```

**Offline (default in CI):** examples only build manifests or print `plan` output.

**Live launches** (starts billing):

```sh
export SUBSTRATE_EXAMPLES_LIVE=1
python examples/python/04_plan_apply_destroy.py
```

Always tear down when finished: `substrate destroy <manifest-name>`.

## Layout

| Path | Contents |
|------|----------|
| [`manifests/`](manifests/) | YAML for `substrate plan` / `apply` / `destroy` |
| [`python/`](python/) | SDK scripts (`01`–`14`) |
| [`cli/COMMANDS.md`](cli/COMMANDS.md) | CLI command cheat sheet |

## Python examples

| Script | What it demonstrates |
|--------|----------------------|
| `01_quickstart_launch.py` | Fluent builder → `plan` / `apply` |
| `02_inventory_browse.py` | `inventory.list` / `find_cheapest` |
| `03_imperative_lifecycle.py` | `instances.create` → `wait_until_active` → `delete` |
| `04_plan_apply_destroy.py` | YAML manifest lifecycle |
| `05_fluent_docker_builder.py` | Docker chain + `to_yaml` |
| `06_fluent_boot_script.py` | Boot script steps |
| `07_secrets_and_env.py` | `Secret`, `$VAR`, `{from_env: ...}` |
| `08_context_manager.py` | `with Substrate()` cleanup |
| `09_from_yaml.py` | `client.from_yaml` + `plan` |
| `10_prototype_to_yaml.py` | Export builder output to disk |
| `11_docker_workload_direct.py` | `DockerWorkload` + `client.run` |
| `12_inventory_region_fallback.py` | `find_with_fallback` |
| `13_ssh_keys_list.py` | `ssh_keys.list` |
| `14_client_run_composite.py` | One-shot `client.run` |
| `15_deploy_git_repo.py` | Clone a git repo at boot (`BootScript.git_clone`) |

## YAML manifests

```sh
substrate plan  examples/manifests/minimal-docker.yaml
substrate apply examples/manifests/minimal-docker.yaml
substrate destroy minimal-docker
```

| Manifest | Workload |
|----------|----------|
| `minimal-docker.yaml` | nginx on A4000 |
| `docker-with-secrets.yaml` | Docker env + secrets |
| `boot-script-steps.yaml` | Boot script (steps) |
| `boot-script-body.yaml` | Boot script (body) |
| `vllm-inference.yaml` | vLLM + health check |
| `multi-region-gpu.yaml` | Region preference list |
| `deploy-git-repo.yaml` | Clone a public repo at boot (YAML `git clone`) |

## Deploy your repository onto the VM

Yes — the SDK supports deploying code from git onto the GPU box. Three patterns:

| Pattern | Best for |
|---------|----------|
| **boot_script + `git clone`** | Bare VM, training scripts, system packages |
| **`BootScript().git_clone(url, dest)`** | Same, composed in Python |
| **Docker + clone in `args`** | Containerized apps (see `scripts/live_test_docker.py`) |

Set your repo URL:

```sh
export SUBSTRATE_DEPLOY_REPO=https://github.com/your-org/your-repo.git
python examples/python/15_deploy_git_repo.py   # with SUBSTRATE_EXAMPLES_LIVE=1
```

Or edit `examples/manifests/deploy-git-repo.yaml` and `substrate apply` it.

**Private repos:** use a deploy key or `GIT_TOKEN` in a boot step / Docker `env` with
`{from_env: GIT_TOKEN}` — secrets are resolved at submit time (see `07_secrets_and_env.py`).

**Live E2E verifier:** `python scripts/e2e_deploy_repo.py` (SSH-checks clone on the VM).
