# Idempotent apply

`SubstrateCloud.apply(...)` (CLI: `substratecloud apply`) is the idempotent way to launch.
The central cost-safety property: re-running `apply` against the same manifest
**never duplicate-launches**.

## How identity works

Every manifest has a required `name`. On apply, the SDK auto-tags the
instance with `manifest:<name>`. The next apply looks for an active
instance carrying that tag and reuses it if the config matches.

```yaml
# substratecloud.yaml
name: my-app          # ← identity key
gpu: { type: A4000 }
workload:
  type: docker
  image: nginx:latest
lifecycle:
  budget_limit_usd: 5
```

```sh
substratecloud apply substratecloud.yaml        # first run: launches
substratecloud apply substratecloud.yaml        # second run: reuses (no API write)
substratecloud apply substratecloud.yaml        # any number of times: still one instance
```

## Drift detection

If the existing instance's `launch_configuration` differs from the manifest
on any of the compared fields, `apply` refuses with a clear error.

**Compared:** `workload.image`, `workload.args`, `workload.env` *keys*,
`workload.ports`, `gpu.type`, `os`, `ssh_key`.

**Not compared:** env *values* (they may be secrets — see below), lifecycle
`budget_limit_usd` (audit tag only), auto-tags (`actor:`, `trace:`, `manifest:`).

To force a replacement on drift:

```sh
substratecloud apply substratecloud.yaml --force    # destroys + relaunches
```

## Known limitation: env values are not compared

If the only thing you change is an env var's *value*, `apply` will say
"no drift" and reuse the old instance. This is intentional — env values
may be secrets and we don't want to compare them.

If you care about value drift, either:

- `substratecloud destroy <name> && substratecloud apply substratecloud.yaml`, or
- Include a hash of the value in your tags so it shows up as a tag change
  on a future schema extension.

## Safety net required by default

`apply` refuses a manifest that has no `budget_limit_usd`. Pass
`--no-safety-net` to override; you'll get a billing warning printed.

Billing stops only on `substratecloud destroy` — the SDK does not auto-terminate
instances when a workload finishes.
