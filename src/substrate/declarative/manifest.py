"""Manifest — the canonical Pydantic representation of a launch intent.

A `Manifest` is the single source of truth that both the YAML loader and the
fluent builder produce. `apply`, `plan`, and `destroy` operate on it.

Bijection: `Manifest.from_yaml(p).to_yaml(p2)` produces a file equivalent
to `p` (modulo formatting / key order).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from substrate.declarative.duration import is_valid_duration


# ─── Secret references inside env: ─────────────────────────────────────────


class _FromEnv(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_env: str = Field(min_length=1)


class _FromVault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_vault: str = Field(min_length=1)


class _Literal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    literal: str


EnvValue = Union[str, _FromEnv, _FromVault, _Literal]
"""An env-var value: a plain string (with `$VAR` shorthand), or a typed ref."""


# ─── GPU / workload / lifecycle sub-specs ──────────────────────────────────


class GPUSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, description="GPU family, e.g. 'A100', 'H100'.")
    count: int = Field(default=1, ge=1)
    max_price_per_hour: Decimal | None = None
    regions: list[str] = Field(default_factory=list)


class HealthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = "/health"
    port: int = Field(ge=1, le=65535)
    expected_status: int = 200
    timeout_s: int = Field(default=5, ge=1)


class DockerWorkloadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["docker"] = "docker"
    image: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, EnvValue] = Field(default_factory=dict)
    ports: dict[int, int] = Field(default_factory=dict, description="{container: host}")
    health: HealthSpec | None = None


class BootScriptWorkloadSpec(BaseModel):
    """Boot script workload (preview — see open API question #1)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["boot_script"] = "boot_script"
    steps: list[str] = Field(default_factory=list)
    body: str | None = None
    ports: list[int] = Field(default_factory=list)
    health: HealthSpec | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> BootScriptWorkloadSpec:
        if not self.steps and self.body is None:
            raise ValueError("boot_script requires either `steps` or `body`")
        if self.steps and self.body is not None:
            raise ValueError(
                "boot_script must specify exactly one of `steps` or `body`, not both"
            )
        return self


WorkloadSpec = Annotated[
    Union[DockerWorkloadSpec, BootScriptWorkloadSpec],
    Field(discriminator="type"),
]


class LifecycleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_limit_usd: Decimal | None = Field(
        default=None, description="BudgetGuard auto-attaches when running via apply."
    )
    max_runtime: str | None = Field(
        default=None, description="Client-side timer; format '4h', '30m', '1d'."
    )
    idle_timeout: str | None = Field(
        default=None, description="Client-side idle timer; same format."
    )
    wait_until_active: bool = True
    wait_timeout: float = Field(default=600.0, ge=1.0)

    @field_validator("max_runtime", "idle_timeout", mode="after")
    @classmethod
    def _validate_duration(cls, v: str | None) -> str | None:
        if v is not None and not is_valid_duration(v):
            raise ValueError(
                f"duration must be like '60s', '30m', '4h', '1d'; got {v!r}"
            )
        return v

    def has_safety_net(self) -> bool:
        return (
            self.budget_limit_usd is not None
            or self.max_runtime is not None
            or self.idle_timeout is not None
        )


# ─── Top-level Manifest ────────────────────────────────────────────────────


class Manifest(BaseModel):
    """The canonical launch-intent document.

    YAML form is loaded with `Manifest.from_yaml(path)`. The fluent builder
    (`substrate.declarative.builder.Launch`) produces the same type.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$",
        description="Identity key. apply looks up by `manifest:<name>` tag.",
    )
    tags: list[str] = Field(default_factory=list)
    gpu: GPUSpec | None = None
    ssh_key: str | None = Field(
        default=None, description="SSH key name or UUID."
    )
    os: str | None = None
    workload: WorkloadSpec | None = None
    lifecycle: LifecycleSpec = Field(default_factory=LifecycleSpec)

    # -- I/O ---------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> Manifest:
        """Load and validate a manifest from a YAML file."""
        import yaml

        text = Path(path).read_text()
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"manifest at {path!s} must be a YAML mapping, got {type(data).__name__}")
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path | None = None) -> str:
        """Serialize to YAML. If `path` is given, write to it; always return the string."""
        import yaml

        data = self.model_dump(mode="json", exclude_none=True)
        text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
        if path is not None:
            Path(path).write_text(text)
        return text

    # -- helpers -----------------------------------------------------------

    def has_safety_net(self) -> bool:
        """True iff at least one of budget/max_runtime/idle_timeout is set."""
        return self.lifecycle.has_safety_net()

    def manifest_tag(self) -> str:
        """The auto-tag used as identity key by apply."""
        return f"manifest:{self.name}"


__all__ = [
    "Manifest",
    "GPUSpec",
    "HealthSpec",
    "DockerWorkloadSpec",
    "BootScriptWorkloadSpec",
    "WorkloadSpec",
    "LifecycleSpec",
    "EnvValue",
]
