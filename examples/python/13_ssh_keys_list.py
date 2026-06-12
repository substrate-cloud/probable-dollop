"""List org SSH key references (public metadata only)."""

from __future__ import annotations

from _common import is_live_run, require_live
from substratecloud import SubstrateCloud


def main() -> None:
    if not is_live_run():
        print("offline: client.ssh_keys.list() returns registered key ids/names")
        return
    require_live()
    keys = SubstrateCloud().ssh_keys.list()
    for key in keys:
        print(f"  {key.id}  {key.name}")


if __name__ == "__main__":
    main()
