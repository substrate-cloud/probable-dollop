"""Load a manifest from YAML and plan it."""

from __future__ import annotations

from pathlib import Path

from _common import is_offline_ci
from substrate import Substrate
from substrate.declarative.manifest import Manifest

MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "boot-script-body.yaml"


def main() -> None:
    if is_offline_ci():
        print(Manifest.from_yaml(MANIFEST).to_yaml())
        return
    client = Substrate()
    launch = client.from_yaml(MANIFEST)
    print(client.plan(launch).summary())


if __name__ == "__main__":
    main()
