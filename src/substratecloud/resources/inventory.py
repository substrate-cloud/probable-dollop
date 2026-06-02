"""Inventory manager — find available GPUs."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from substratecloud._http.client import HttpClient
from substratecloud._http.errors import NoCapacityError
from substratecloud.models.inventory import InventoryItem
from substratecloud.resources._base import unwrap


class InventoryManager:
    """Wraps `GET /inventory`. Read-only."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http

    def list(
        self,
        *,
        gpu_type: str | None = None,
        location: str | None = None,
        gpu_count: int | None = None,
        max_price: float | Decimal | None = None,
    ) -> list[InventoryItem]:
        """List currently-available GPU configurations, sorted by price ascending."""
        params = {
            "gpu_type": gpu_type,
            "location": location,
            "gpu_count": gpu_count,
            "max_price": float(max_price) if max_price is not None else None,
        }
        data = unwrap(self._http.request("GET", "/inventory", params=params), route="/inventory")
        return [InventoryItem.model_validate(item) for item in data]

    def find_cheapest(
        self,
        *,
        gpu_type: str | None = None,
        location: str | None = None,
        min_count: int = 1,
        max_price: float | Decimal | None = None,
    ) -> InventoryItem:
        """Return the cheapest item matching the filters.

        Raises NoCapacityError if no item is available.
        """
        items = self.list(gpu_type=gpu_type, location=location, max_price=max_price)
        matches = [i for i in items if i.gpu_count >= min_count]
        if not matches:
            raise NoCapacityError(
                f"No inventory matched gpu_type={gpu_type!r} location={location!r} "
                f"min_count={min_count} max_price={max_price}"
            )
        return matches[0]

    def find_with_fallback(self, preferences: Iterable[dict[str, object]]) -> InventoryItem:
        """Try multiple specs in order; return the first match.

        Each preference dict accepts the same kwargs as `find_cheapest`.
        Critical for spot-like UX since regional availability fluctuates.
        """
        last_exc: NoCapacityError | None = None
        for pref in preferences:
            try:
                return self.find_cheapest(**pref)  # type: ignore[arg-type]
            except NoCapacityError as exc:
                last_exc = exc
                continue
        raise NoCapacityError(
            f"No inventory matched any of the {len(list(preferences))} fallback preferences. "
            f"Last error: {last_exc}"
        )

    # -- async parity ---------------------------------------------------------

    async def alist(
        self,
        *,
        gpu_type: str | None = None,
        location: str | None = None,
        gpu_count: int | None = None,
        max_price: float | Decimal | None = None,
    ) -> list[InventoryItem]:
        params = {
            "gpu_type": gpu_type,
            "location": location,
            "gpu_count": gpu_count,
            "max_price": float(max_price) if max_price is not None else None,
        }
        data = unwrap(
            await self._http.arequest("GET", "/inventory", params=params),
            route="/inventory",
        )
        return [InventoryItem.model_validate(item) for item in data]
