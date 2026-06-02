"""Instances manager — the core of the SDK. Cost-safety lives here."""

from __future__ import annotations

import time
from collections.abc import Iterable
from uuid import UUID

from substratecloud._http.client import HttpClient
from substratecloud._http.errors import NotFoundError, SubstrateCloudError
from substratecloud._http.logging import get_logger
from substratecloud.models.enums import InstanceStatus
from substratecloud.models.instance import Instance, InstanceCreate, InstanceUpdate
from substratecloud.models.launch_config import LaunchConfiguration
from substratecloud.resources._base import unwrap

_log = get_logger("substratecloud.instances")


class InstancesManager:
    """Wraps `POST/GET/PATCH/DELETE /instance(s)`.

    Cost-safety design rules baked in:
      * `POST /instances` is never auto-retried — see retries.py.
      * `create()` logs cost_per_hour at INFO level so a billed action is always
        visible in logs.
      * `wait_until_active` requires an explicit timeout; no infinite default.
    """

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    # -- create ---------------------------------------------------------------

    def create(
        self,
        *,
        inventory_gpu_id: UUID | str,
        name: str,
        ssh_key_id: UUID | str | None = None,
        os: str | None = None,
        tags: list[str] | None = None,
        launch_configuration: LaunchConfiguration | None = None,
    ) -> Instance:
        """Launch a new instance. **Billing starts immediately.**

        The SDK does not auto-retry this call. A 5xx may have already created
        a billed instance; retrying could duplicate it.
        """
        body = InstanceCreate(
            inventory_gpu_id=UUID(str(inventory_gpu_id)),
            name=name,
            ssh_key_id=UUID(str(ssh_key_id)) if ssh_key_id else None,
            os=os,
            tags=tags or [],
            launch_configuration=launch_configuration,
        ).model_dump(mode="json", exclude_none=True)

        data = unwrap(
            self._http.request("POST", "/instances", json=body),
            route="/instances",
        )
        instance = Instance.model_validate(data)
        _log.info(
            "substratecloud.instance.created",
            id=str(instance.id),
            name=instance.name,
            gpu_type=instance.gpu_type,
            cost_per_hour=str(instance.cost_per_hour),
            tags=instance.tags,
        )
        return instance

    # -- list / get -----------------------------------------------------------

    def list(self) -> list[Instance]:
        data = unwrap(self._http.request("GET", "/instances"), route="/instances")
        return [Instance.model_validate(item) for item in data]

    def get(self, instance_id: UUID | str) -> Instance:
        route = f"/instance/{instance_id}"
        data = unwrap(self._http.request("GET", route), route=route)
        return Instance.model_validate(data)

    def find_by_name(self, name: str) -> list[Instance]:
        """Names are NOT unique per the API. Returns all matches.

        Prefer tag-based lookups for production code.
        """
        return [i for i in self.list() if i.name == name]

    def find_by_tag(self, tag: str) -> list[Instance]:
        return [i for i in self.list() if tag in i.tags]

    # -- update ---------------------------------------------------------------

    def update(
        self,
        instance_id: UUID | str,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> Instance:
        """PATCH /instance/:id — only name and tags are mutable.

        NOTE: per docs, `tags` REPLACES the array. # API-OPEN-QUESTION: confirm merge semantics.
        """
        upd = InstanceUpdate(name=name, tags=tags)
        if not upd.has_changes():
            raise ValueError("update() requires at least one of name or tags")
        route = f"/instance/{instance_id}"
        body = upd.model_dump(mode="json", exclude_none=True)
        data = unwrap(self._http.request("PATCH", route, json=body), route=route)
        return Instance.model_validate(data)

    # -- delete ---------------------------------------------------------------

    def delete(self, instance_id: UUID | str) -> Instance:
        """Terminate an instance. **Irreversible.** Stops billing."""
        route = f"/instance/{instance_id}"
        data = unwrap(self._http.request("DELETE", route), route=route)
        instance = Instance.model_validate(data)
        _log.info(
            "substratecloud.instance.deleted",
            id=str(instance.id),
            name=instance.name,
        )
        return instance

    def delete_many(self, instance_ids: Iterable[UUID | str]) -> list[Instance]:
        """Best-effort bulk delete. Continues on individual failures and
        re-raises with a summary at the end.
        """
        deleted: list[Instance] = []
        errors: list[tuple[str, SubstrateCloudError]] = []
        for iid in instance_ids:
            try:
                deleted.append(self.delete(iid))
            except SubstrateCloudError as exc:
                errors.append((str(iid), exc))
        if errors:
            summary = "; ".join(f"{iid}: {e.message}" for iid, e in errors)
            raise SubstrateCloudError(
                f"delete_many: {len(deleted)} deleted, {len(errors)} failed — {summary}"
            )
        return deleted

    # -- polling helpers ------------------------------------------------------

    def wait_until_active(
        self,
        instance_id: UUID | str,
        *,
        timeout: float,
        poll_interval: float = 5.0,
    ) -> Instance:
        """Poll until the instance reports `active`.

        Raises:
          TimeoutError: deadline exceeded.
          SubstrateCloudError: if the instance enters `deleting` or `deleted`.
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                instance = self.get(instance_id)
            except NotFoundError as exc:
                raise SubstrateCloudError(
                    f"Instance {instance_id} no longer exists (was it deleted?)"
                ) from exc
            if instance.status == InstanceStatus.ACTIVE and instance.ip_address is not None:
                return instance
            if instance.status in (
                InstanceStatus.DELETING,
                InstanceStatus.DELETED,
                InstanceStatus.FAILED,
                InstanceStatus.ERROR,
            ):
                raise SubstrateCloudError(
                    f"Instance {instance_id} entered terminal status {instance.status.value}"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Instance {instance_id} did not become active within {timeout}s "
                    f"(last status: {instance.status.value})"
                )
            time.sleep(poll_interval)

    # -- async parity ---------------------------------------------------------

    async def alist(self) -> list[Instance]:
        data = unwrap(await self._http.arequest("GET", "/instances"), route="/instances")
        return [Instance.model_validate(item) for item in data]

    async def aget(self, instance_id: UUID | str) -> Instance:
        route = f"/instance/{instance_id}"
        data = unwrap(await self._http.arequest("GET", route), route=route)
        return Instance.model_validate(data)

    async def adelete(self, instance_id: UUID | str) -> Instance:
        route = f"/instance/{instance_id}"
        data = unwrap(await self._http.arequest("DELETE", route), route=route)
        return Instance.model_validate(data)
