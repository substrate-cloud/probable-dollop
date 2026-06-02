"""Lower a Manifest to the existing typed workload classes.

Keeps the Manifest free of dependencies on `substratecloud.workloads.*` so the
schema layer can be reasoned about in isolation. The reverse direction
(workload object -> manifest spec) lives on the workload classes via
`Workload.from_manifest()` (see TODO in workloads/base.py).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from substratecloud.declarative.manifest import (
    BootScriptWorkloadSpec,
    DockerWorkloadSpec,
    EnvValue,
    Manifest,
    _FromEnv,
    _FromVault,
    _Literal,
)
from substratecloud.workloads.base import HealthCheck
from substratecloud.workloads.docker import DockerWorkload
from substratecloud.workloads.secret import Secret

if TYPE_CHECKING:
    from substratecloud.workloads.base import Workload


# A `$VARNAME` shorthand for `Secret.from_env(VARNAME)`. Backslash-escape
# (`\$literal`) opts out and produces the literal value (without the
# backslash).
_DOLLAR_SHORTHAND = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")
_ESCAPED_DOLLAR = re.compile(r"^\\\$(.*)$")


def resolve_env_value(value: EnvValue) -> str | Secret:
    """Convert a Manifest env value to either a plain str or a `Secret`.

    Rules:
      `$VARNAME`            → Secret.from_env("VARNAME")
      `\\$foo`              → literal `$foo` (escape)
      `{from_env: X}`       → Secret.from_env(X)
      `{from_vault: PATH}`  → Secret with lazy vault reader (provider unset
                              raises at submit time)
      `{literal: X}`        → Secret.literal(X)
      any other str         → returned as-is (NOT a secret)
    """
    if isinstance(value, _FromEnv):
        return Secret.from_env(value.from_env)
    if isinstance(value, _FromVault):
        path = value.from_vault
        return Secret.from_callable(
            _vault_provider(path),
            label=f"vault:{path}",
            origin=f"vault:{path}",
        )
    if isinstance(value, _Literal):
        return Secret.literal(value.literal)
    # Plain string: check for $VAR shorthand or escape.
    m = _DOLLAR_SHORTHAND.match(value)
    if m:
        return Secret.from_env(m.group(1))
    m = _ESCAPED_DOLLAR.match(value)
    if m:
        return f"${m.group(1)}"
    return value


def _vault_provider(path: str):
    """Placeholder vault reader; users wire their own via `Secret.from_callable`."""

    def _read() -> str:
        raise RuntimeError(
            f"Vault provider not configured. To use `from_vault: {path}`, "
            f"install and configure a vault provider, or replace with "
            f"`Secret.from_callable(...)` in code."
        )

    return _read


def docker_workload_from_spec(spec: DockerWorkloadSpec) -> DockerWorkload:
    """Convert a manifest's Docker workload spec to a `DockerWorkload`."""
    env: dict[str, str | Secret] = {k: resolve_env_value(v) for k, v in spec.env.items()}
    return DockerWorkload(
        image=spec.image,
        args=list(spec.args),
        env=env,
        ports=dict(spec.ports),
        health_path=(spec.health.path if spec.health else "/health"),
    )


def workload_from_manifest(manifest: Manifest) -> "Workload | None":
    """Lower a manifest's workload spec to an existing workload class.

    Returns None if the manifest has no workload (the instance launches
    without a launch_configuration — billable but no container started).
    """
    if manifest.workload is None:
        return None
    if isinstance(manifest.workload, DockerWorkloadSpec):
        return docker_workload_from_spec(manifest.workload)
    if isinstance(manifest.workload, BootScriptWorkloadSpec):
        return _boot_script_workload_from_spec(manifest.workload)
    raise TypeError(f"unknown workload spec type: {type(manifest.workload).__name__}")


def _boot_script_workload_from_spec(spec: BootScriptWorkloadSpec):
    """Build a BootScriptWorkload from the manifest spec.

    # API-OPEN-QUESTION (open #1): the `launch_configuration` shape for
    # boot scripts is still preview; this lowering may evolve.

    The manifest's `steps:` (a list of bash lines) and `body:` (one blob)
    are both lowered to a single `BootScript().custom(...)` command. For
    structured steps (pip_install, pull_hf_model, etc.) use the
    `BootScriptWorkload` class directly.
    """
    from substratecloud.workloads.boot_script.builder import BootScript
    from substratecloud.workloads.boot_script.workload import BootScriptWorkload

    body = spec.body if spec.body is not None else "\n".join(spec.steps)
    script = BootScript().custom(body, step_id="manifest")
    health = None
    if spec.health is not None:
        health = HealthCheck(
            path=spec.health.path,
            port=spec.health.port,
            expected_status=spec.health.expected_status,
            timeout_s=spec.health.timeout_s,
        )
    return BootScriptWorkload(script=script, ports=list(spec.ports), health=health)


__all__ = [
    "resolve_env_value",
    "docker_workload_from_spec",
    "workload_from_manifest",
]
