"""SSH key reference returned by `GET /ssh-keys`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SSHKey(BaseModel):
    """An SSH key registered to the org. Private key material never crosses this SDK."""

    model_config = ConfigDict(extra="ignore")

    id: UUID
    name: str
    created_at: datetime

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"
