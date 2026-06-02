"""One-call launch via SubstrateCloud.launch(**kwargs)."""

from __future__ import annotations

from _common import is_live_run, is_offline_ci, require_live
from substratecloud import SubstrateCloud
from substratecloud.declarative.builder import Launch
from substratecloud.declarative.manifest import Manifest


def build_manifest() -> Manifest:
    return (
        Launch()
        .gpu("A4000", max_price=1)
        .docker("nginx:latest", ports={80: 80})
        .budget(2)
        .tags("example:quickstart")
        .to_manifest(name="quickstart-demo")
    )


def main() -> None:
    manifest = build_manifest()
    if is_offline_ci():
        print(manifest.to_yaml())
        return
    client = SubstrateCloud()
    print(client.plan(manifest).summary())
    if is_live_run():
        require_live()
        inst = client.apply(manifest)
        print(f"active: {inst.name} @ {inst.ip_address}")
        print(f"destroy: substratecloud destroy {inst.name}")


if __name__ == "__main__":
    main()
