"""SubstrateCloud Python SDK — typed, composable client for the SubstrateCloud On-Demand GPU API."""

from substratecloud._http.errors import (
    AuthError,
    NoCapacityError,
    NotFoundError,
    QuotaError,
    ServerError,
    SubstrateCloudError,
    TransportError,
    ValidationError,
    WorkloadTimeoutError,
)
from substratecloud._version import __version__
from substratecloud.client import SubstrateCloud
from substratecloud.models import (
    GPUType,
    Instance,
    InstanceStatus,
    InventoryItem,
    Region,
    SSHKey,
)
from substratecloud.workloads import (
    BootScript,
    BootScriptWorkload,
    DockerWorkload,
    HealthCheck,
    Secret,
    Workload,
)
from substratecloud.workloads.presets import InferenceServer

__all__ = [
    "__version__",
    "SubstrateCloud",
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
    "SubstrateCloudError",
    "AuthError",
    "NotFoundError",
    "ValidationError",
    "QuotaError",
    "ServerError",
    "TransportError",
    "NoCapacityError",
    "WorkloadTimeoutError",
]
