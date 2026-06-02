"""Imperative API: inventory → create → wait → delete."""

from __future__ import annotations

from _common import is_live_run, require_live
from substrate import Substrate


def main() -> None:
    if not is_live_run():
        print("offline: would create/delete via client.instances.*")
        return
    require_live()
    client = Substrate()
    item = client.inventory.find_cheapest(gpu_type="A4000")
    inst = client.instances.create(inventory_gpu_id=item.id, name="imperative-demo", tags=["example:imperative"])
    try:
        active = client.instances.wait_until_active(inst.id, timeout=900)
        print(f"active {active.name} ip={active.ip_address}")
    finally:
        deleted = client.instances.delete(inst.id)
        print(f"deleted {deleted.id}")


if __name__ == "__main__":
    main()
