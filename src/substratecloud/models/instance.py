"""Instance resource model. Includes Decimal-money computed properties."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substratecloud.models.enums import InstanceStatus
from substratecloud.models.launch_config import LaunchConfiguration


class Instance(BaseModel):
    """A SubstrateCloud GPU instance.

    Note: instance names are NOT unique per the API spec. Use `id` (UUID) for
    identity. Use tags (`actor:*`, `trace:*`) for grouping.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: UUID
    name: str
    status: InstanceStatus
    gpu_type: str | None = None
    gpu_count: int | None = None
    ip_address: IPv4Address | IPv6Address | None = None
    ssh_user: str | None = None
    ssh_port: int | None = None
    cost_per_hour: Decimal = Decimal(0)
    tags: list[str] = Field(default_factory=list)
    # Slim responses (e.g. DELETE) omit timestamps — keep optional.
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Populated by GET /instance/:id when the API includes it; used by
    # `SubstrateCloud.apply()` drift detection.
    launch_configuration: LaunchConfiguration | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_empty_ip(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("ip_address") in ("", None):
            data["ip_address"] = None
        return data

    @property
    def is_ready(self) -> bool:
        return self.status == InstanceStatus.ACTIVE and self.ip_address is not None

    @property
    def uptime(self) -> timedelta:
        if self.created_at is None:
            return timedelta(0)
        now = datetime.now(timezone.utc)
        return now - self.created_at

    @property
    def estimated_spend(self) -> Decimal:
        hours = Decimal(self.uptime.total_seconds()) / Decimal(3600)
        return (self.cost_per_hour * hours).quantize(Decimal("0.0001"))

    def __str__(self) -> str:
        return f"{self.name} [{self.status.value}] ({self.id})"


class InstanceCreate(BaseModel):
    """Request body for `POST /instances`."""

    model_config = ConfigDict(extra="forbid")

    inventory_gpu_id: UUID
    name: str = Field(max_length=50)
    ssh_key_id: UUID | None = None
    os: str | None = None
    tags: list[str] = Field(default_factory=list)
    launch_configuration: LaunchConfiguration | None = None


class InstanceUpdate(BaseModel):
    """Request body for `PATCH /instance/:id`. Only name + tags are mutable."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=50)
    tags: list[str] | None = None

    def has_changes(self) -> bool:
        return self.name is not None or self.tags is not None
