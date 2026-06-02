"""Region fallback preferences for spot-like capacity."""

from __future__ import annotations

from _common import is_live_run, require_live
from substratecloud import SubstrateCloud


def fallback_prefs() -> list[dict[str, object]]:
    return [
        {"gpu_type": "H100", "location": "north america", "min_count": 1, "max_price": 5},
        {"gpu_type": "H100", "location": "europe", "min_count": 1, "max_price": 5},
        {"gpu_type": "A100", "min_count": 1, "max_price": 4},
    ]


def main() -> None:
    prefs = fallback_prefs()
    if not is_live_run():
        print("offline preferences:", prefs)
        return
    require_live()
    item = SubstrateCloud().inventory.find_with_fallback(prefs)
    print(f"selected {item.gpu_type} in {item.region} @ €{item.final_price_per_hour}/hr")


if __name__ == "__main__":
    main()
