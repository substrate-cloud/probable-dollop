"""Immutable fluent builder that produces a `Manifest`.

Each builder method returns a new `Launch` with one more field set. Terminals
are `Launch.launch(name=...)` (lowers the manifest and calls the existing
`client.run()`) and `Launch.to_manifest()` / `Launch.to_yaml()`.

`apply` / `plan` / `destroy` live on the `SubstrateCloud` client itself (not on
`Launch`) and accept either a YAML path or a `Manifest` / `Launch`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from substratecloud.declarative.manifest import (
    Manifest,
)
from substratecloud.workloads.secret import Secret

if TYPE_CHECKING:
    from substratecloud.client import SubstrateCloud
    from substratecloud.models.instance import Instance


_NULL = object()  # sentinel for unset (None is meaningful for some fields)


@dataclass(frozen=True)
class Launch:
    """Immutable manifest-builder. Returned by builder methods on `SubstrateCloud`.

    Use `.launch(name=...)` to actually launch, or `.to_manifest(name=...)`
    to extract the Manifest without calling the API.
    """

    _client: SubstrateCloud | None = None
    _partial: dict[str, Any] = field(default_factory=dict)

    # ── selection ─────────────────────────────────────────────────────────

    def gpu(
        self,
        type: str,
        *,
        count: int = 1,
        max_price: float | Decimal | None = None,
        regions: list[str] | None = None,
    ) -> Launch:
        spec: dict[str, Any] = {"type": type, "count": count}
        if max_price is not None:
            spec["max_price_per_hour"] = str(max_price)
        if regions:
            spec["regions"] = list(regions)
        return self._with(gpu=spec)

    def ssh_key(self, key: str | UUID) -> Launch:
        return self._with(ssh_key=str(key))

    def os(self, os: str) -> Launch:
        return self._with(os=os)

    def tags(self, *tags: str) -> Launch:
        existing = list(self._partial.get("tags", []))
        existing.extend(tags)
        return self._with(tags=existing)

    # ── workload (docker) ─────────────────────────────────────────────────

    def docker(
        self,
        image: str,
        *,
        args: list[str] | None = None,
        env: dict[str, str | Secret] | None = None,
        ports: dict[int, int] | None = None,
    ) -> Launch:
        wl: dict[str, Any] = {"type": "docker", "image": image}
        if args:
            wl["args"] = list(args)
        if env:
            wl["env"] = _env_to_manifest(env)
        if ports:
            wl["ports"] = dict(ports)
        return self._with(workload=wl)

    def args(self, *args: str) -> Launch:
        wl = dict(self._partial.get("workload", {"type": "docker", "image": ""}))
        wl["args"] = list(wl.get("args", [])) + list(args)
        return self._with(workload=wl)

    def env(self, **kwargs: str | Secret) -> Launch:
        wl = dict(self._partial.get("workload", {"type": "docker", "image": ""}))
        env_existing = dict(wl.get("env", {}))
        env_existing.update(_env_to_manifest(kwargs))
        wl["env"] = env_existing
        return self._with(workload=wl)

    def ports(self, *ports: int | dict[int, int]) -> Launch:
        wl = dict(self._partial.get("workload", {"type": "docker", "image": ""}))
        existing = dict(wl.get("ports", {}))
        for p in ports:
            if isinstance(p, dict):
                existing.update({int(k): int(v) for k, v in p.items()})
            else:
                existing[int(p)] = int(p)
        wl["ports"] = existing
        return self._with(workload=wl)

    # ── workload (boot script) ────────────────────────────────────────────

    def boot_script(
        self,
        *,
        steps: list[str] | None = None,
        body: str | None = None,
        ports: list[int] | None = None,
    ) -> Launch:
        if (steps is None) == (body is None):
            raise ValueError("boot_script requires exactly one of `steps` or `body`")
        wl: dict[str, Any] = {"type": "boot_script"}
        if steps is not None:
            wl["steps"] = list(steps)
        if body is not None:
            wl["body"] = body
        if ports:
            wl["ports"] = list(ports)
        return self._with(workload=wl)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def budget(self, usd: float | Decimal) -> Launch:
        return self._lifecycle(budget_limit_usd=str(usd))

    def wait(self, *, until_active: bool = True, timeout: float | None = None) -> Launch:
        kw: dict[str, Any] = {"wait_until_active": until_active}
        if timeout is not None:
            kw["wait_timeout"] = float(timeout)
        return self._lifecycle(**kw)

    # ── loaders / exporters ───────────────────────────────────────────────

    @classmethod
    def from_manifest(cls, manifest: Manifest, *, client: SubstrateCloud | None = None) -> Launch:
        data = manifest.model_dump(mode="json", exclude_none=True)
        return cls(_client=client, _partial=data)

    def to_manifest(self, *, name: str | None = None) -> Manifest:
        """Materialize the partial state into a validated `Manifest`.

        Pass `name` to set/override the manifest name. Required if the
        builder doesn't already have one.
        """
        data = dict(self._partial)
        if name is not None:
            data["name"] = name
        if "name" not in data:
            raise ValueError(
                "Manifest requires a `name`. Pass it as `.launch(name=...)` "
                "or `.to_manifest(name=...)`."
            )
        return Manifest.model_validate(data)

    def to_yaml(self, path: str | Path | None = None, *, name: str | None = None) -> str:
        return self.to_manifest(name=name).to_yaml(path)

    # ── terminals ─────────────────────────────────────────────────────────

    def launch(
        self,
        name: str | None = None,
        *,
        wait: bool | None = None,
        wait_timeout: float | None = None,
    ) -> Instance:
        """Lower the manifest and call the existing imperative launch path."""
        from substratecloud.declarative.executor import lower_and_launch

        if self._client is None:
            raise RuntimeError(
                "Launch is detached from a client. Use SubstrateCloud().gpu(...) "
                "instead of constructing Launch directly."
            )
        m = self.to_manifest(name=name)
        return lower_and_launch(self._client, m, wait=wait, wait_timeout=wait_timeout)

    # ── internals ─────────────────────────────────────────────────────────

    def _with(self, **kwargs: Any) -> Launch:
        merged = dict(self._partial)
        for k, v in kwargs.items():
            if v is _NULL:
                merged.pop(k, None)
            else:
                merged[k] = v
        return dataclasses.replace(self, _partial=merged)

    def _lifecycle(self, **kwargs: Any) -> Launch:
        lc = dict(self._partial.get("lifecycle", {}))
        lc.update(kwargs)
        return self._with(lifecycle=lc)


def _env_to_manifest(env: dict[str, str | Secret]) -> dict[str, Any]:
    """Convert a builder env dict to manifest-shaped values.

    - `str` passes through (the `$VAR` shorthand is resolved at lower time).
    - `Secret.from_env(X)` lowers to `{from_env: X}` (lossless round-trip).
    - Other `Secret` kinds raise; users should pass the manifest dict form.
    """
    out: dict[str, Any] = {}
    for k, v in env.items():
        if isinstance(v, Secret):
            if v.origin.startswith("env:"):
                out[k] = {"from_env": v.origin.split(":", 1)[1]}
            elif v.origin == "literal":
                out[k] = {"literal": v.resolve()}
            else:
                raise ValueError(
                    f"env[{k!r}]: Secret with origin {v.origin!r} cannot be encoded "
                    f"in a manifest. Use `$VAR` shorthand, `{{from_env: ...}}`, "
                    f"or pass the manifest dict directly."
                )
        else:
            out[k] = v
    return out


__all__ = ["Launch"]
