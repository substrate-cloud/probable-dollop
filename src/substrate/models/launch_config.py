"""Launch configuration sub-objects passed in `POST /instances`.

Both Docker and script shapes are documented in ONDEMAND_MCP_ROUTES.md.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EnvVar(BaseModel):
    """An env var pair to inject into the Docker container."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: str


class PortMapping(BaseModel):
    """Container-to-host port mapping."""

    model_config = ConfigDict(extra="forbid")

    container_port: int = Field(ge=1, le=65535)
    host_port: int = Field(ge=1, le=65535)


class DockerConfiguration(BaseModel):
    """Inner `docker_configuration` object documented by the Substrate API."""

    model_config = ConfigDict(extra="forbid")

    image: str
    args: str | None = None
    envs: list[EnvVar] = Field(default_factory=list)
    port_mappings: list[PortMapping] = Field(default_factory=list)


class ScriptConfiguration(BaseModel):
    """Boot-script configuration (confirmed shape — staging docs 2026-05-21).

    Specify exactly one of `script` (plain bash; proxy base64-encodes for you)
    or `base64_script` (already base64-encoded). Decoded payload must be
    <= 64 KB. The script runs once during instance boot, before SSH is
    available; check `/var/log/cloud-init.log` or provider logs to confirm.
    """

    model_config = ConfigDict(extra="forbid")

    script: str | None = Field(
        default=None,
        description="Plain bash text. Max 64 KB after UTF-8 encoding.",
    )
    base64_script: str | None = Field(
        default=None,
        description="Pre-encoded base64 string. Decoded must be <= 64 KB.",
    )

    def model_post_init(self, __context: Any) -> None:  # noqa: D401
        from base64 import b64decode

        if (self.script is None) == (self.base64_script is None):
            raise ValueError(
                "ScriptConfiguration requires exactly one of `script` or `base64_script`"
            )
        if self.script is not None:
            encoded = self.script.encode("utf-8")
            if len(encoded) > 64 * 1024:
                raise ValueError(
                    f"script is {len(encoded)} bytes; max 65536 (64 KB)"
                )
        else:
            try:
                decoded = b64decode(self.base64_script or "", validate=True)
            except Exception as e:
                raise ValueError(f"base64_script is not valid base64: {e}") from e
            if len(decoded) > 64 * 1024:
                raise ValueError(
                    f"base64_script decodes to {len(decoded)} bytes; max 65536"
                )


class _DockerLaunch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["docker"] = "docker"
    docker_configuration: DockerConfiguration


class _ScriptLaunch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["script"] = "script"
    script_configuration: ScriptConfiguration


LaunchConfiguration = Annotated[
    _DockerLaunch | _ScriptLaunch,
    Field(discriminator="type"),
]
"""Top-level launch_configuration submitted with `POST /instances`."""


def docker(
    image: str,
    *,
    args: str | None = None,
    envs: list[EnvVar] | None = None,
    port_mappings: list[PortMapping] | None = None,
) -> _DockerLaunch:
    """Convenience constructor for a Docker launch configuration."""
    return _DockerLaunch(
        docker_configuration=DockerConfiguration(
            image=image,
            args=args,
            envs=envs or [],
            port_mappings=port_mappings or [],
        )
    )


def script(body: str | None = None, *, base64_script: str | None = None) -> _ScriptLaunch:
    """Convenience constructor for a boot-script launch configuration.

    Pass either `body` (plain bash) or `base64_script` — exactly one.
    """
    return _ScriptLaunch(
        script_configuration=ScriptConfiguration(
            script=body, base64_script=base64_script
        )
    )


__all__ = [
    "EnvVar",
    "PortMapping",
    "DockerConfiguration",
    "ScriptConfiguration",
    "LaunchConfiguration",
    "docker",
    "script",
]
