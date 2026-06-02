"""Enums for resource attributes. Open to extension as the platform grows."""

from __future__ import annotations

import logging
from enum import Enum

_log = logging.getLogger("substratecloud.models")


class GPUType(str, Enum):
    """Known GPU families. The API matches case-insensitively on the string value."""

    H100 = "H100"
    H200 = "H200"
    A100 = "A100"
    A6000 = "A6000"
    A5000 = "A5000"
    A4000 = "A4000"
    L40S = "L40S"
    L40 = "L40"
    L4 = "L4"
    RTX4090 = "RTX4090"
    RTX3090 = "RTX3090"
    V100 = "V100"
    T4 = "T4"


class InstanceStatus(str, Enum):
    CREATING = "creating"
    PENDING = "pending"
    # The dev API also emits internal lifecycle values like `pending_provider`
    # while waiting for hardware allocation. Keep these listed so they round-trip
    # cleanly; any future additions fall back to UNKNOWN via _missing_.
    PENDING_PROVIDER = "pending_provider"
    PENDING_PAYMENT = "pending_payment"
    ACTIVE = "active"
    DELETING = "deleting"
    DELETED = "deleted"
    FAILED = "failed"
    ERROR = "error"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value: object) -> InstanceStatus:
        """Forward-compat: unknown statuses log a warning and map to UNKNOWN.

        The wait_until_active loop only short-circuits on ACTIVE, DELETING, and
        DELETED — every other status (known or unknown) means "keep polling".
        """
        _log.warning(
            "substratecloud.models.unknown_status",
            extra={"value": str(value)},
        )
        return cls.UNKNOWN

    @property
    def is_terminal(self) -> bool:
        return self in (InstanceStatus.DELETED, InstanceStatus.FAILED, InstanceStatus.ERROR)

    @property
    def is_running(self) -> bool:
        return self == InstanceStatus.ACTIVE

    @property
    def is_pending(self) -> bool:
        return self in (
            InstanceStatus.CREATING,
            InstanceStatus.PENDING,
            InstanceStatus.PENDING_PROVIDER,
            InstanceStatus.PENDING_PAYMENT,
            InstanceStatus.UNKNOWN,
        )


class Region(str, Enum):
    EUROPE = "Europe"
    NORTH_AMERICA = "North America"
    ASIA_PACIFIC = "Asia Pacific"
    AUSTRALIA = "Australia"
    SOUTH_AMERICA = "South America"
    MIDDLE_EAST = "Middle East"
    AFRICA = "Africa"
