"""Fluent builder: boot_script with steps."""

from __future__ import annotations

from substrate import Substrate
from substrate.declarative.manifest import BootScriptWorkloadSpec, Manifest


def build_manifest() -> Manifest:
    return (
        Substrate()
        .gpu("A4000")
        .boot_script(steps=["apt-get update -y", "echo ready", "nvidia-smi -L || true"])
        .budget(8)
        .to_manifest(name="fluent-boot-steps")
    )


def main() -> None:
    m = build_manifest()
    assert isinstance(m.workload, BootScriptWorkloadSpec)
    print(m.to_yaml())


if __name__ == "__main__":
    main()
