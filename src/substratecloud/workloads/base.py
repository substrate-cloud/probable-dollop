"""The Workload protocol every workload type implements."""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from substratecloud.models.launch_config import LaunchConfiguration


class HealthCheck(BaseModel):
    """Declarative health-check spec. Used by `instance.wait_until_healthy()`."""

    path: str = "/health"
    port: int = 80
    expected_status: int = 200
    timeout_s: int = Field(default=5, ge=1)


@runtime_checkable
class Workload(Protocol):
    """Declarative spec for what runs on the box.

    Implementations:
      - DockerWorkload      (documented API path: type="docker")
      - BootScriptWorkload  (speculative, # API-OPEN-QUESTION)
      - presets (InferenceServer, TrainingJob, ...) — built on BootScriptWorkload
    """

    def to_launch_configuration(self) -> LaunchConfiguration: ...

    def required_ports(self) -> list[int]: ...

    def health_check(self) -> HealthCheck | None: ...

    def estimated_boot_time(self) -> timedelta: ...
