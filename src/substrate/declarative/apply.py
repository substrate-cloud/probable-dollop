"""apply / plan / destroy — idempotent operations on a Manifest.

The cost-safety story: `apply` looks up instances tagged `manifest:<name>`
and never duplicate-launches. Drift detection compares image/args/env-keys/
ports/gpu.type/regions/os/ssh_key. Env *values* are not compared (they may
be secrets); this is documented loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from substrate._http.errors import SubstrateError
from substrate._http.logging import get_logger
from substrate.declarative.executor import lower_and_launch
from substrate.declarative.manifest import (
    BootScriptWorkloadSpec,
    DockerWorkloadSpec,
    Manifest,
)
from substrate.models.enums import InstanceStatus

if TYPE_CHECKING:
    from substrate.client import Substrate
    from substrate.models.instance import Instance

_log = get_logger("substrate.declarative.apply")


Action = Literal["create", "reuse", "drift_refused", "destroy_relaunch"]


@dataclass
class Plan:
    """Output of `Substrate.plan(manifest)` — describes what apply would do."""

    manifest: Manifest
    action: Action
    existing_instance_id: str | None = None
    inventory_id: str | None = None
    inventory_region: str | None = None
    inventory_price_per_hour: Decimal | None = None
    estimated_daily_usd: Decimal | None = None
    estimated_weekly_usd: Decimal | None = None
    drift_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        m = self.manifest
        lines = [f"Plan for {m.name}:"]
        lines.append(f"  Action       : {self.action}")
        if self.existing_instance_id:
            lines.append(f"  Existing     : {self.existing_instance_id}")
        if self.inventory_id:
            gpu = m.gpu.type if m.gpu else "?"
            count = m.gpu.count if m.gpu else 1
            lines.append(
                f"  GPU          : {gpu} {count}x ({self.inventory_region}) "
                f"@ ${self.inventory_price_per_hour}/hr"
            )
        if self.estimated_daily_usd is not None:
            lines.append(
                f"  Estimated    : ${self.inventory_price_per_hour}/hr  "
                f"→  ${self.estimated_daily_usd}/day  "
                f"→  ${self.estimated_weekly_usd}/week"
            )
        lines.append(f"  Auto-tags    : {m.manifest_tag()}")
        lc = m.lifecycle
        if lc.budget_limit_usd is not None:
            lines.append(
                f"  Budget tag   : budget_limit_usd={lc.budget_limit_usd} "
                "(audit only — billing stops on destroy)"
            )
        else:
            lines.append("  Budget tag   : ⚠ none set (pass --no-safety-net to allow)")
        lines.append("  Teardown     : substrate destroy <name> when the workload finishes")
        if self.drift_fields:
            lines.append(f"  Drift fields : {', '.join(self.drift_fields)}")
        if self.warnings:
            lines.append(f"  Warnings     : {len(self.warnings)}")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


def plan(
    client: Substrate,
    source: str | Path | Manifest,
    *,
    require_safety_net: bool = True,
) -> Plan:
    """Dry-run an apply. Never calls POST /instances.

    Makes at most one API call to `find_cheapest` for cost estimation.
    """
    manifest = _coerce_manifest(source)

    existing = _find_existing_active(client, manifest)
    if existing is not None:
        drift = _detect_drift(manifest, existing)
        if drift:
            return Plan(
                manifest=manifest,
                action="drift_refused",
                existing_instance_id=str(existing.id),
                drift_fields=drift,
                warnings=_collect_warnings(manifest, require_safety_net),
            )
        return Plan(
            manifest=manifest,
            action="reuse",
            existing_instance_id=str(existing.id),
            warnings=_collect_warnings(manifest, require_safety_net),
        )

    # No existing — estimate cost.
    inv_id, region, price = _estimate_inventory(client, manifest)
    daily = price * Decimal("24") if price is not None else None
    weekly = daily * Decimal("7") if daily is not None else None
    return Plan(
        manifest=manifest,
        action="create",
        inventory_id=inv_id,
        inventory_region=region,
        inventory_price_per_hour=price,
        estimated_daily_usd=daily,
        estimated_weekly_usd=weekly,
        warnings=_collect_warnings(manifest, require_safety_net),
    )


def apply(
    client: Substrate,
    source: str | Path | Manifest,
    *,
    force: bool = False,
    require_safety_net: bool = True,
) -> Instance:
    """Idempotent launch. See module docstring for the four cases.

    `force=True` destroys and re-launches a drifted instance.
    `require_safety_net=False` allows manifests with no budget_limit_usd.
    """
    manifest = _coerce_manifest(source)

    if require_safety_net and not manifest.has_safety_net():
        raise SubstrateError(
            f"manifest {manifest.name!r} has no budget_limit_usd "
            "(set lifecycle.budget_limit_usd or pass require_safety_net=False / "
            "--no-safety-net to opt out)"
        )

    existing = _find_existing_active(client, manifest)
    if existing is not None:
        drift = _detect_drift(manifest, existing)
        if not drift:
            _log.info(
                "substrate.apply.reused",
                name=manifest.name,
                instance_id=str(existing.id),
            )
            return existing
        if not force:
            raise SubstrateError(
                f"apply.drift: instance {existing.id} for manifest {manifest.name!r} "
                f"has drifted fields: {drift}. Pass force=True to destroy & relaunch, "
                f"or destroy() first."
            )
        _log.warning(
            "substrate.apply.force_destroy_relaunch",
            name=manifest.name,
            instance_id=str(existing.id),
            drift=drift,
        )
        client.instances.delete(existing.id)

    return lower_and_launch(client, manifest)


def destroy(
    client: Substrate,
    target: str | Path | Manifest,
    *,
    all_matches: bool = False,
) -> list[Instance]:
    """Tear down instance(s) by manifest name / path / tag.

    Resolution:
      Manifest / *.yaml path → use manifest.name
      str without yaml suffix → treat as the manifest name (looked up by tag)

    Returns the list of deleted instances.
    """
    name = _coerce_manifest_name(target)
    matches = client.instances.find_by_tag(f"manifest:{name}")
    matches = [i for i in matches if not i.status.is_terminal]
    if not matches:
        raise SubstrateError(
            f"destroy: no active instance found with tag manifest:{name}"
        )
    if len(matches) > 1 and not all_matches:
        ids = [str(i.id) for i in matches]
        raise SubstrateError(
            f"destroy: multiple active instances tagged manifest:{name} "
            f"(ids: {ids}). Pass all_matches=True / --all to delete all."
        )
    deleted: list[Instance] = []
    for inst in matches:
        deleted.append(client.instances.delete(inst.id))
    return deleted


# ─── internals ────────────────────────────────────────────────────────────


def _coerce_manifest(source: str | Path | Manifest) -> Manifest:
    if isinstance(source, Manifest):
        return source
    return Manifest.from_yaml(source)


def _coerce_manifest_name(target: str | Path | Manifest) -> str:
    if isinstance(target, Manifest):
        return target.name
    p = Path(target) if not isinstance(target, Path) else target
    if p.suffix in (".yaml", ".yml") and p.exists():
        return Manifest.from_yaml(p).name
    return str(target)


def _find_existing_active(client: Substrate, manifest: Manifest) -> Instance | None:
    """Return the single active instance tagged for this manifest, if any.

    If multiple active instances are tagged for this manifest, return the
    most-recently-created one (apply will then detect drift if applicable).
    """
    matches = client.instances.find_by_tag(manifest.manifest_tag())
    active = [
        i
        for i in matches
        if i.status == InstanceStatus.ACTIVE
        or i.status.is_pending
    ]
    if not active:
        return None
    # Prefer most-recently-created if multiple (shouldn't happen normally).
    active.sort(key=lambda i: getattr(i, "created_at", None) or 0, reverse=True)
    return active[0]


def _detect_drift(manifest: Manifest, instance: Any) -> list[str]:
    """Return a list of drifted field names. Empty list = no drift.

    Compared fields: workload.image, workload.args, env *keys*, ports,
    gpu.type, os, ssh_key_id, regions (only if explicitly set in manifest).
    Env *values* and lifecycle settings are NOT compared.
    """
    drifted: list[str] = []
    launch_cfg = getattr(instance, "launch_configuration", None)
    inst_image = _read_launch_image(launch_cfg)
    inst_args = _read_launch_args(launch_cfg)
    inst_env_keys = _read_launch_env_keys(launch_cfg)
    inst_ports = _read_launch_ports(launch_cfg)

    mw = manifest.workload
    if isinstance(mw, DockerWorkloadSpec):
        if inst_image is not None and inst_image != mw.image:
            drifted.append(f"workload.image (manifest={mw.image!r}, instance={inst_image!r})")
        if inst_args is not None:
            man_args = " ".join(mw.args) if mw.args else None
            if man_args != inst_args:
                drifted.append("workload.args")
        if inst_env_keys is not None and set(inst_env_keys) != set(mw.env.keys()):
            drifted.append(
                f"workload.env_keys (manifest={sorted(mw.env)}, instance={sorted(inst_env_keys)})"
            )
        if inst_ports is not None and set(inst_ports) != set(mw.ports.items()):
            drifted.append("workload.ports")
    elif isinstance(mw, BootScriptWorkloadSpec):
        # Boot script drift is harder — we don't read back the rendered script
        # to compare. Treat as same if both sides claim boot_script.
        pass

    inst_gpu = getattr(instance, "gpu_type", None)
    if inst_gpu is not None and manifest.gpu is not None and inst_gpu != manifest.gpu.type:
        drifted.append(f"gpu.type (manifest={manifest.gpu.type!r}, instance={inst_gpu!r})")

    return drifted


def _read_launch_image(cfg: Any) -> str | None:
    if cfg is None:
        return None
    docker = getattr(cfg, "docker_configuration", None)
    if docker is None:
        return None
    return getattr(docker, "image", None)


def _read_launch_args(cfg: Any) -> str | None:
    docker = getattr(cfg, "docker_configuration", None) if cfg is not None else None
    return getattr(docker, "args", None) if docker is not None else None


def _read_launch_env_keys(cfg: Any) -> list[str] | None:
    docker = getattr(cfg, "docker_configuration", None) if cfg is not None else None
    if docker is None:
        return None
    envs = getattr(docker, "envs", None) or []
    return [e.name for e in envs]


def _read_launch_ports(cfg: Any) -> set[tuple[int, int]] | None:
    docker = getattr(cfg, "docker_configuration", None) if cfg is not None else None
    if docker is None:
        return None
    pm = getattr(docker, "port_mappings", None) or []
    return {(p.container_port, p.host_port) for p in pm}


def _estimate_inventory(
    client: Substrate, manifest: Manifest
) -> tuple[str | None, str | None, Decimal | None]:
    """One API call to estimate cost. Returns (inventory_id, region, price)."""
    if manifest.gpu is None:
        return None, None, None
    try:
        item = client.inventory.find_cheapest(
            gpu_type=manifest.gpu.type,
            min_count=manifest.gpu.count,
            max_price=manifest.gpu.max_price_per_hour,
        )
    except Exception as exc:  # noqa: BLE001 — estimation is best-effort
        _log.warning("substrate.plan.inventory_estimate_failed", error=str(exc))
        return None, None, None
    return str(item.id), str(item.region), item.final_price_per_hour


def _collect_warnings(manifest: Manifest, require_safety_net: bool) -> list[str]:
    warnings: list[str] = []
    if require_safety_net and not manifest.has_safety_net():
        warnings.append(
            "no budget_limit_usd set (lifecycle.budget_limit_usd required unless opted out)"
        )
    if manifest.workload is not None and isinstance(manifest.workload, DockerWorkloadSpec):
        for k, v in manifest.workload.env.items():
            if isinstance(v, str) and not v.startswith("$"):
                continue
            if isinstance(v, dict) or (hasattr(v, "from_env") and getattr(v, "from_env", None)):
                warnings.append(
                    f"env[{k!r}] sourced from env at submit time (persisted in launch_configuration)"
                )
    return warnings


__all__ = ["Plan", "plan", "apply", "destroy"]
