"""Declarative lifecycle: plan → apply → destroy (idempotent by manifest name)."""

from __future__ import annotations

from pathlib import Path

from _common import is_live_run, is_offline_ci, require_live
from substrate import Substrate
from substrate.declarative.manifest import Manifest

MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "minimal-docker.yaml"


def load_manifest() -> Manifest:
    return Manifest.from_yaml(MANIFEST)


def main() -> None:
    manifest = load_manifest()
    if is_offline_ci():
        print(manifest.to_yaml())
        return
    client = Substrate()
    print(client.plan(manifest).summary())
    if not is_live_run():
        print(f"live: substrate apply {MANIFEST}")
        return
    require_live()
    inst = client.apply(manifest)
    print(f"applied {inst.name} ({inst.id})")
    deleted = client.destroy(manifest.name)
    print(f"destroyed {len(deleted)} instance(s)")


if __name__ == "__main__":
    main()
