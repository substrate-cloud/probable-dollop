"""DockerWorkload — wraps the documented `type: "docker"` launch_configuration."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping
from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from substratecloud.models.launch_config import (
    EnvVar,
    LaunchConfiguration,
    PortMapping,
    docker,
)
from substratecloud.workloads.base import HealthCheck
from substratecloud.workloads.secret import Secret, resolve_value

# Conservative literal-secret detector — see plan doc §10.3.
_SECRET_LITERAL_PATTERNS = [
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
]


class DockerWorkload(BaseModel):
    """A workload that runs a single container.

    Maps to `launch_configuration.type = "docker"`. See plan doc §6.2.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str | Secret] = Field(default_factory=dict)
    ports: dict[int, int] = Field(default_factory=dict, description="{container: host}")
    estimated_boot_s: int = 120
    health_path: str | None = "/health"

    # -- Workload protocol ----------------------------------------------------

    def to_launch_configuration(self) -> LaunchConfiguration:
        envs = self._resolve_envs()
        port_mappings = [PortMapping(container_port=c, host_port=h) for c, h in self.ports.items()]
        args_str = " ".join(shlex.quote(a) for a in self.args) if self.args else None
        return docker(
            image=self.image,
            args=args_str,
            envs=envs,
            port_mappings=port_mappings,
        )

    def required_ports(self) -> list[int]:
        return list(self.ports.values())

    def health_check(self) -> HealthCheck | None:
        if not self.health_path:
            return None
        first_port = next(iter(self.ports.values()), None)
        if first_port is None:
            return None
        return HealthCheck(path=self.health_path, port=first_port)

    def estimated_boot_time(self) -> timedelta:
        return timedelta(seconds=self.estimated_boot_s)

    # -- helpers --------------------------------------------------------------

    def _resolve_envs(self) -> list[EnvVar]:
        out: list[EnvVar] = []
        for name, value in self.env.items():
            resolved = resolve_value(value)
            # Defence-in-depth — refuse to ship plain-literal secrets in launch_configuration.
            # The SubstrateCloud API persists this payload server-side (see plan doc §10.3).
            if not isinstance(value, Secret):
                _refuse_if_literal_secret(name, resolved)
            out.append(EnvVar(name=name, value=resolved))
        return out

    # safety: don't accidentally leak via repr
    def __repr__(self) -> str:
        return (
            f"DockerWorkload(image={self.image!r}, args={self.args!r}, "
            f"env_keys={list(self.env)}, ports={self.ports})"
        )


def _refuse_if_literal_secret(name: str, value: str) -> None:
    for pattern in _SECRET_LITERAL_PATTERNS:
        if pattern.search(value):
            raise ValueError(
                f"env[{name!r}] looks like a literal secret. "
                f"Wrap with Secret.from_env(...) so it isn't checked into source "
                f"or persisted in the SubstrateCloud launch_configuration."
            )


__all__ = ["DockerWorkload"]


def from_dict(spec: Mapping[str, object]) -> DockerWorkload:
    """Materialise a DockerWorkload from a plain dict (YAML loader)."""
    env_in = spec.get("env") or {}
    env: dict[str, str | Secret] = {}
    if isinstance(env_in, dict):
        for k, v in env_in.items():
            if isinstance(v, dict) and "env" in v:
                env[k] = Secret.from_env(str(v["env"]))
            else:
                env[k] = str(v)
    ports_in = spec.get("ports") or {}
    ports: dict[int, int] = {}
    if isinstance(ports_in, dict):
        for k, v in ports_in.items():
            ports[int(k)] = int(v)  # type: ignore[arg-type]
    args_in: Iterable[object] = spec.get("args") or []  # type: ignore[assignment]
    return DockerWorkload(
        image=str(spec["image"]),
        args=[str(a) for a in args_in],
        env=env,
        ports=ports,
    )
