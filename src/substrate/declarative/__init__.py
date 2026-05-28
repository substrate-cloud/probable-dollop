"""Declarative manifest layer for the Substrate SDK.

A `Manifest` is the canonical launch intent. Both the YAML loader and the
fluent builder produce instances of it. `apply`/`plan`/`destroy` (on
`substrate.Substrate`) operate on it.
"""

from __future__ import annotations

from substrate.declarative.apply import Plan, apply, destroy, plan
from substrate.declarative.builder import Launch
from substrate.declarative.duration import parse_duration
from substrate.declarative.manifest import (
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
