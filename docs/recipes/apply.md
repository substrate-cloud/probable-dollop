# Idempotent apply

`Substrate.apply(...)` (CLI: `substrate apply`) is the idempotent way to launch.
The central cost-safety property: re-running `apply` against the same manifest
**never duplicate-launches**.

## How identity works

Every manifest has a required `name`. On apply, the SDK auto-tags the
instance with `manifest:<name>`. The next apply looks for an active
instance carrying that tag and reuses it if the config matches.

```yaml
# substrate.yaml
name: my-app          # ← identity key
gpu: { type: A4000 }
workload:
  type: docker
  image: nginx:latest
lifecycle:
  budget_limit_usd: 5
```

```sh
substrate apply substrate.yaml        # first run: launches
substrate apply substrate.yaml        # second run: reuses (no API write)
substrate apply substrate.yaml        # any number of times: still one instance
```

## Drift detection

If the existing instance's `launch_configuration` differs from the manifest
on any of the compared fields, `apply` refuses with a clear error.

**Compared:** `workload.image`, `workload.args`, `workload.env` *keys*,
`workload.ports`, `gpu.type`, `os`, `ssh_key`.

**Not compared:** env *values* (they may be secrets — see below), lifecycle
bounds (`budget`, `max_runtime`, `idle_timeout` — they are process-local
guards), auto-tags (`actor:`, `trace:`, `manifest:`).

To force a replacement on drift:

```sh
substrate apply substrate.yaml --force    # destroys + relaunches
```

## Known limitation: env values are not compared

If the only thing you change is an env var's *value*, `apply` will say
"no drift" and reuse the old instance. This is intentional — env values
may be secrets and we don't want to compare them.

If you care about value drift, either:

- `substrate destroy <name> && substrate apply substrate.yaml`, or
- Include a hash of the value in your tags so it shows up as a tag change
  on a future schema extension.

## Safety net required by default

`apply` refuses a manifest that has no `budget_limit_usd`, `max_runtime`,
or `idle_timeout`. Pass `--no-safety-net` to override; you'll get a
warning printed.
