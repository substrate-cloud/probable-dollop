"""Browse inventory — list and find_cheapest (read-only API)."""

from __future__ import annotations

from _common import is_live_run, require_live
from substratecloud import SubstrateCloud


def demo_offline_filters() -> dict[str, object]:
    """Document filter kwargs without calling the API."""
    return {
        "list_kwargs": {"gpu_type": "A100", "location": "europe", "gpu_count": 1, "max_price": 4},
        "find_cheapest_kwargs": {"gpu_type": "A100", "min_count": 1, "max_price": 4},
    }


def main() -> None:
    if not is_live_run():
        print("offline:", demo_offline_filters())
        print("Set SUBSTRATECLOUD_EXAMPLES_LIVE=1 to query inventory.")
        return
    require_live()
    client = SubstrateCloud()
    items = client.inventory.list(gpu_type="A100", max_price=5)
    print(f"found {len(items)} A100 listings under $5/hr")
    for item in items[:5]:
        print(f"  {item.gpu_type} x{item.gpu_count} @ {item.region} €{item.final_price_per_hour}/hr")
    cheapest = client.inventory.find_cheapest(gpu_type="A4000")
    print(f"cheapest A4000: {cheapest.id} €{cheapest.final_price_per_hour}/hr")


if __name__ == "__main__":
    main()
