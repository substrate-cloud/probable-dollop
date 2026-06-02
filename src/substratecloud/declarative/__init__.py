"""Declarative manifest layer for the SubstrateCloud SDK.

A `Manifest` is the canonical launch intent. Both the YAML loader and the
fluent builder produce instances of it. `apply`/`plan`/`destroy` (on
`substratecloud.SubstrateCloud`) operate on it.
"""

from __future__ import annotations

from substratecloud.declarative.apply import Plan, apply, destroy, plan
from substratecloud.declarative.builder import Launch
from substratecloud.declarative.duration import parse_duration
from substratecloud.declarative.manifest import (
    BootScriptWorkloadSpec,
    DockerWorkloadSpec,
    EnvValue,
    GPUSpec,
    HealthSpec,
    LifecycleSpec,
    Manifest,
    WorkloadSpec,
)

__all__ = [
    "Manifest",
    "Launch",
    "Plan",
    "apply",
    "destroy",
    "plan",
    "GPUSpec",
    "HealthSpec",
    "DockerWorkloadSpec",
    "BootScriptWorkloadSpec",
    "WorkloadSpec",
    "LifecycleSpec",
    "EnvValue",
    "parse_duration",
]
