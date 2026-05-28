"""Inventory item — a currently-available GPU configuration."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InventoryItem(BaseModel):
    """One row from `GET /inventory`. `id` is the value to pass as `inventory_gpu_id`."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: UUID
    gpu_type: str  # "CPU" for non-GPU nodes; otherwise a GPU family name
    gpu_count: int = Field(ge=0)  # 0 for CPU-only inventory
    gpu_vram_gb: int = Field(ge=0)
    final_price_per_hour: Decimal
    region: str
    os_options: list[str] = Field(default_factory=list)

    @property
    def is_gpu(self) -> bool:
        return self.gpu_count > 0 and self.gpu_type.upper() != "CPU"

    @property
    def price_per_gpu_hour(self) -> Decimal:
        return self.final_price_per_hour / self.gpu_count if self.gpu_count else Decimal(0)

    @property
    def default_os(self) -> str | None:
        return self.os_options[0] if self.os_options else None

    def __str__(self) -> str:
        return (
            f"{self.gpu_count}x{self.gpu_type} {self.gpu_vram_gb}GB "
            f"@ €{self.final_price_per_hour}/hr ({self.region})"
        )
