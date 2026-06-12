"""BootScriptWorkload — wraps a BootScript into a Workload-protocol instance."""

from __future__ import annotations

from datetime import timedelta

from substratecloud.models.launch_config import LaunchConfiguration, script
from substratecloud.workloads.base import HealthCheck
from substratecloud.workloads.boot_script.builder import BootScript


class BootScriptWorkload:
    """A workload defined by a bash boot script.

    # API-OPEN-QUESTION (plan doc §11.1): the launch_configuration shape for
    # boot scripts is not yet documented. See substratecloud.models.launch_config.
    """

    def __init__(
        self,
        script: BootScript,
        *,
        ports: list[int] | None = None,
        health: HealthCheck | None = None,
        estimated_boot_s: int = 300,
    ) -> None:
        self._script = script
        self._ports = ports or []
        self._health = health
        self._estimated_boot_s = estimated_boot_s

    @property
    def script(self) -> BootScript:
        return self._script

    def to_launch_configuration(self) -> LaunchConfiguration:
        return script(self._script.render())  # type: ignore[arg-type]

    def required_ports(self) -> list[int]:
        return list(self._ports)

    def health_check(self) -> HealthCheck | None:
        return self._health

    def estimated_boot_time(self) -> timedelta:
        return timedelta(seconds=self._estimated_boot_s)

    def __repr__(self) -> str:
        return f"BootScriptWorkload({self._script!r}, ports={self._ports})"
