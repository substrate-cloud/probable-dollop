"""Top-level SubstrateCloud client. The single entry point for SDK users."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import SecretStr

from substratecloud import config as config_module
from substratecloud._http.auth import resolve_base_url, resolve_token
from substratecloud._http.client import HttpClient
from substratecloud._http.logging import get_logger
from substratecloud._http.retries import RetryPolicy
from substratecloud.declarative.builder import Launch
from substratecloud.declarative.executor import lower_and_launch
from substratecloud.declarative.manifest import Manifest
from substratecloud.models.enums import InstanceStatus
from substratecloud.models.instance import Instance
from substratecloud.resources.instances import InstancesManager
from substratecloud.resources.inventory import InventoryManager
from substratecloud.resources.ssh_keys import SSHKeysManager
from substratecloud.workloads.secret import Secret

if TYPE_CHECKING:
    from substratecloud.workloads.base import Workload

_log = get_logger("substratecloud.client")


class SubstrateCloud:
    """The main SDK entry point.

    >>> client = SubstrateCloud()                    # uses env / config file
    >>> client = SubstrateCloud(token="mcp_...")     # explicit
    >>> client.inventory.list(gpu_type="A100")
    >>> client.instances.create(inventory_gpu_id=..., name="exp-1")
    """

    def __init__(
        self,
        *,
        token: str | SecretStr | None = None,
        base_url: str | None = None,
        profile: str | None = None,
        retry_policy: RetryPolicy | None = None,
        config_path: Any | None = None,
    ) -> None:
        cfg = config_module.load(config_path)
        prof = cfg.get_profile(profile)

        self._token = resolve_token(token, profile=prof)
        self._base_url = resolve_base_url(base_url, profile=prof)
        self._profile = prof

        self._http = HttpClient(
            base_url=self._base_url,
            token=self._token,
            retry_policy=retry_policy,
        )

        self.inventory = InventoryManager(self._http)
        self.instances = InstancesManager(self._http)
        self.ssh_keys = SSHKeysManager(self._http)

    @property
    def base_url(self) -> str:
        return self._base_url

    def close(self) -> None:
        self._http.close()

    async def aclose(self) -> None:
        await self._http.aclose()

    def __enter__(self) -> SubstrateCloud:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"SubstrateCloud(base_url={self._base_url!r}, token=***)"

    # ------------------------------------------------------------------------
    # Fluent builder entry points (immutable; each returns a fresh Launch).
    # See substratecloud.declarative.builder.Launch for the chain methods.
    # ------------------------------------------------------------------------

    def gpu(
        self,
        type: str,
        *,
        count: int = 1,
        max_price: float | Decimal | None = None,
        regions: list[str] | None = None,
    ) -> Launch:
        return Launch(_client=self).gpu(type, count=count, max_price=max_price, regions=regions)

    def docker(
        self,
        image: str,
        *,
        args: list[str] | None = None,
        env: dict[str, str | Secret] | None = None,
        ports: dict[int, int] | None = None,
    ) -> Launch:
        return Launch(_client=self).docker(image, args=args, env=env, ports=ports)

    def boot_script(
        self,
        *,
        steps: list[str] | None = None,
        body: str | None = None,
        ports: list[int] | None = None,
    ) -> Launch:
        return Launch(_client=self).boot_script(steps=steps, body=body, ports=ports)

    def from_yaml(self, path: str | Path) -> Launch:
        manifest = Manifest.from_yaml(path)
        return Launch.from_manifest(manifest, client=self)

    def launch(self, **manifest_kwargs: Any) -> Instance:
        """One-call form: build a Manifest from kwargs and launch in one shot.

        Required: `name`. Optional: any other manifest field (gpu, image, args,
        env, ports, budget, tags, ssh_key, os, ...).
        Convenience kwargs `image`/`args`/`env`/`ports` create a docker
        workload; pass `boot_script={...}` for boot scripts.
        """
        manifest = _build_manifest_from_kwargs(manifest_kwargs)
        return lower_and_launch(self, manifest)

    # ------------------------------------------------------------------------
    # Declarative: apply / plan / destroy.
    # ------------------------------------------------------------------------

    def plan(
        self,
        source: str | Path | Manifest | Launch,
        *,
        require_safety_net: bool = True,
    ) -> Any:
        """Dry-run an apply. Returns a `Plan` object (never calls POST /instances)."""
        from substratecloud.declarative.apply import plan as _plan

        manifest = source.to_manifest() if isinstance(source, Launch) else source
        return _plan(self, manifest, require_safety_net=require_safety_net)

    def apply(
        self,
        source: str | Path | Manifest | Launch,
        *,
        force: bool = False,
        require_safety_net: bool = True,
    ) -> Instance:
        """Idempotent launch. Looks up `manifest:<name>` and reuses if found.

        `force=True` destroys a drifted instance and relaunches.
        `require_safety_net=False` allows manifests with no budget/runtime/idle.
        """
        from substratecloud.declarative.apply import apply as _apply

        manifest = source.to_manifest() if isinstance(source, Launch) else source
        return _apply(self, manifest, force=force, require_safety_net=require_safety_net)

    def destroy(
        self,
        target: str | Path | Manifest | Launch,
        *,
        all_matches: bool = False,
    ) -> list[Instance]:
        """Tear down instance(s) by manifest name / path / tag.

        Returns the list of deleted instances.
        """
        from substratecloud.declarative.apply import destroy as _destroy

        name_target: str | Path | Manifest
        if isinstance(target, Launch):
            name_target = target.to_manifest()
        else:
            name_target = target
        return _destroy(self, name_target, all_matches=all_matches)

    # ------------------------------------------------------------------------
    # High-level facade: client.run() — pulls together inventory + create.
    # ------------------------------------------------------------------------

    def run(
        self,
        *,
        workload: Workload | None = None,
        gpu: str | None = None,
        region_preference: list[str] | None = None,
        max_price_per_hour: float | Decimal | None = None,
        min_count: int = 1,
        name: str,
        ssh_key: str | UUID | None = None,
        os: str | None = None,
        tags: list[str] | None = None,
        budget_limit: Decimal | None = None,  # noqa: ARG002  # recorded as budget:N tag for audit
        wait: bool = True,
        wait_timeout: float = 600.0,
    ) -> Instance:
        """Composite: find capacity → launch → optionally wait until active.

        - `gpu`: GPU family selector (e.g. "H100"). Resolved via inventory.
        - `region_preference`: ordered list of regions to try.
        - `ssh_key`: UUID or registered key name.
        - `budget_limit`: recorded as a `budget:N` tag for audit (does not auto-terminate).

        Returns the Instance handle. If `wait=True`, blocks until `active`.
        """
        item = self._pick_inventory(
            gpu=gpu,
            region_preference=region_preference,
            max_price=max_price_per_hour,
            min_count=min_count,
        )
        _log.info(
            "substratecloud.run.selected_inventory",
            inventory_id=str(item.id),
            gpu_type=item.gpu_type,
            region=item.region,
            price=str(item.final_price_per_hour),
        )

        ssh_key_id = self._resolve_ssh_key(ssh_key)
        final_tags = self._compose_tags(tags, budget_limit=budget_limit)

        launch_cfg = workload.to_launch_configuration() if workload else None

        instance = self.instances.create(
            inventory_gpu_id=item.id,
            name=name,
            ssh_key_id=ssh_key_id,
            os=os,
            tags=final_tags,
            launch_configuration=launch_cfg,
        )

        if wait:
            instance = self.instances.wait_until_active(
                instance.id, timeout=wait_timeout
            )

        return instance

    # ------------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------------

    def _pick_inventory(
        self,
        *,
        gpu: str | None,
        region_preference: list[str] | None,
        max_price: float | Decimal | None,
        min_count: int,
    ) -> Any:
        if region_preference:
            prefs = [
                {"gpu_type": gpu, "location": r, "min_count": min_count, "max_price": max_price}
                for r in region_preference
            ]
            return self.inventory.find_with_fallback(prefs)
        return self.inventory.find_cheapest(
            gpu_type=gpu, min_count=min_count, max_price=max_price
        )

    def _resolve_ssh_key(self, ssh_key: str | UUID | None) -> UUID | None:
        if ssh_key is None:
            if self._profile and self._profile.default_ssh_key_id:
                return UUID(self._profile.default_ssh_key_id)
            return None
        if isinstance(ssh_key, UUID):
            return ssh_key
        try:
            return UUID(ssh_key)
        except (ValueError, AttributeError):
            return self.ssh_keys.find_by_name(ssh_key).id

    def _compose_tags(
        self,
        explicit: list[str] | None,
        *,
        budget_limit: Decimal | None,
    ) -> list[str]:
        import getpass
        import uuid as _uuid

        tags = list(explicit or [])
        if self._profile and self._profile.default_tags:
            tags = list({*self._profile.default_tags, *tags})

        # Audit attribution — see plan doc §10.1.
        try:
            actor = getpass.getuser()
            tags.append(f"actor:{actor}")
        except Exception:  # pragma: no cover — non-tty environments
            pass
        tags.append(f"trace:{_uuid.uuid4().hex[:8]}")

        if budget_limit is not None:
            tags.append(f"budget:{budget_limit}")

        return tags


def _status_is_terminal(status: InstanceStatus) -> bool:
    return status in (InstanceStatus.DELETED, InstanceStatus.DELETING)


def _build_manifest_from_kwargs(kwargs: dict[str, Any]) -> Manifest:
    """Translate `SubstrateCloud.launch(**kwargs)` flat kwargs into a Manifest.

    Recognized keys (all optional except `name`):
      name, tags, ssh_key, os                          — top-level
      gpu, count, max_price, regions                   — folded into gpu spec
      image, args, env, ports                          — folded into docker workload
      boot_script (dict)                               — alternative workload
      budget, wait, wait_timeout  — lifecycle
    """
    data: dict[str, Any] = {}
    if "name" not in kwargs:
        raise ValueError("SubstrateCloud.launch(...) requires a `name` kwarg")
    data["name"] = kwargs.pop("name")
    if "tags" in kwargs:
        data["tags"] = list(kwargs.pop("tags"))
    if "ssh_key" in kwargs:
        data["ssh_key"] = str(kwargs.pop("ssh_key"))
    if "os" in kwargs:
        data["os"] = kwargs.pop("os")

    # GPU spec
    gpu_type = kwargs.pop("gpu", None)
    if gpu_type is not None:
        gpu_spec: dict[str, Any] = {"type": gpu_type, "count": kwargs.pop("count", 1)}
        if "max_price" in kwargs:
            gpu_spec["max_price_per_hour"] = str(kwargs.pop("max_price"))
        if "regions" in kwargs:
            gpu_spec["regions"] = list(kwargs.pop("regions"))
        data["gpu"] = gpu_spec

    # Workload (docker shorthand or explicit boot_script)
    if "image" in kwargs:
        from substratecloud.declarative.builder import _env_to_manifest

        wl: dict[str, Any] = {"type": "docker", "image": kwargs.pop("image")}
        if "args" in kwargs:
            wl["args"] = list(kwargs.pop("args"))
        if "env" in kwargs:
            wl["env"] = _env_to_manifest(kwargs.pop("env"))
        if "ports" in kwargs:
            wl["ports"] = {int(k): int(v) for k, v in kwargs.pop("ports").items()}
        data["workload"] = wl
    elif "boot_script" in kwargs:
        bs = kwargs.pop("boot_script")
        data["workload"] = {"type": "boot_script", **bs}

    # Lifecycle
    lc: dict[str, Any] = {}
    if "budget" in kwargs:
        lc["budget_limit_usd"] = str(kwargs.pop("budget"))
    if "wait" in kwargs:
        lc["wait_until_active"] = bool(kwargs.pop("wait"))
    if "wait_timeout" in kwargs:
        lc["wait_timeout"] = float(kwargs.pop("wait_timeout"))
    if lc:
        data["lifecycle"] = lc

    if kwargs:
        raise TypeError(
            f"SubstrateCloud.launch(...) got unexpected kwargs: {sorted(kwargs)}"
        )
    return Manifest.model_validate(data)
