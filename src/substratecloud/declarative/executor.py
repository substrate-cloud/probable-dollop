"""Lower a Manifest to existing imperative-API calls.

This is the only module that bridges the declarative layer to the existing
`client.run()` path. Apply, plan, and the fluent terminal `Launch.launch()`
all call into here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from substratecloud.declarative.lower import workload_from_manifest
from substratecloud.declarative.manifest import Manifest

if TYPE_CHECKING:
    from substratecloud.client import SubstrateCloud
    from substratecloud.models.instance import Instance


def lower_and_launch(
    client: SubstrateCloud,
    manifest: Manifest,
    *,
    wait: bool | None = None,
    wait_timeout: float | None = None,
) -> Instance:
    """Lower the manifest and call `client.run(...)`.

    `wait` and `wait_timeout` override `manifest.lifecycle.wait_until_active`
    and `wait_timeout` when given.
    """
    workload = workload_from_manifest(manifest)
    gpu = manifest.gpu.type if manifest.gpu else None
    regions = (manifest.gpu.regions if manifest.gpu else None) or None
    max_price: Decimal | None = (
        manifest.gpu.max_price_per_hour if manifest.gpu else None
    )
    min_count = manifest.gpu.count if manifest.gpu else 1

    final_tags = list(manifest.tags)
    final_tags.append(manifest.manifest_tag())

    lifecycle = manifest.lifecycle
    effective_wait = lifecycle.wait_until_active if wait is None else wait
    effective_timeout = lifecycle.wait_timeout if wait_timeout is None else wait_timeout

    return client.run(
        workload=workload,
        gpu=gpu,
        region_preference=regions,
        max_price_per_hour=max_price,
        min_count=min_count,
        name=manifest.name,
        ssh_key=manifest.ssh_key,
        os=manifest.os,
        tags=final_tags,
        budget_limit=lifecycle.budget_limit_usd,
        wait=effective_wait,
        wait_timeout=effective_timeout,
    )


__all__ = ["lower_and_launch"]
