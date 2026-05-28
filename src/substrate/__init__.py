"""Substrate Python SDK — typed, composable client for the Substrate On-Demand GPU API."""

from substrate._http.errors import (
    AuthError,
    NoCapacityError,
    NotFoundError,
    QuotaError,
    ServerError,
    SubstrateError,
    TransportError,
    ValidationError,
    WorkloadTimeoutError,
)
from substrate._version import __version__
from substrate.client import Substrate
from substrate.models import (
    GPUType,
    Instance,
    InstanceStatus,
    InventoryItem,
    Region,
    SSHKey,
)
from substrate.workloads import (
    BootScript,
    BootScriptWorkload,
    DockerWorkload,
    HealthCheck,
    Secret,
    Workload,
)
from substrate.workloads.presets import InferenceServer

__all__ = [
    "__version__",
    "Substrate",
    # models
    "Instance",
    "InstanceStatus",
    "InventoryItem",
    "SSHKey",
    "GPUType",
    "Region",
    # workloads
    "Workload",
    "HealthCheck",
    "Secret",
    "DockerWorkload",
    "BootScript",
    "BootScriptWorkload",
    "InferenceServer",
    # errors
    "SubstrateError",
    "AuthError",
    "NotFoundError",
    "ValidationError",
    "QuotaError",
    "ServerError",
    "TransportError",
    "NoCapacityError",
    "WorkloadTimeoutError",
]
