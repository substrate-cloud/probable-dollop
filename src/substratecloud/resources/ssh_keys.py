"""SSH keys manager — read-only (keys are added via the SubstrateCloud console)."""

from __future__ import annotations

from substratecloud._http.client import HttpClient
from substratecloud._http.errors import NotFoundError
from substratecloud.models.ssh_key import SSHKey
from substratecloud.resources._base import unwrap


class SSHKeysManager:
    """Wraps `GET /ssh-keys`. The SDK never reads, writes, or transmits private
    key material — operations go through the user's ssh-agent.
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(self) -> list[SSHKey]:
        data = unwrap(self._http.request("GET", "/ssh-keys"), route="/ssh-keys")
        return [SSHKey.model_validate(item) for item in data]

    def find_by_name(self, name: str) -> SSHKey:
        """Return the first key with the given name. Raises NotFoundError if absent."""
        for k in self.list():
            if k.name == name:
                return k
        raise NotFoundError(f"No SSH key registered with name {name!r}")

    async def alist(self) -> list[SSHKey]:
        data = unwrap(
            await self._http.arequest("GET", "/ssh-keys"), route="/ssh-keys"
        )
        return [SSHKey.model_validate(item) for item in data]
