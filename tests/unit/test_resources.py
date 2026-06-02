"""Layer 3 resource managers — happy path + key helpers."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from substratecloud._http.errors import NoCapacityError


def test_inventory_list_parses_decimal_price(client, mock_api, sample_inventory_item):
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    items = client.inventory.list()
    assert len(items) == 1
    item = items[0]
    assert isinstance(item.final_price_per_hour, Decimal)
    assert item.final_price_per_hour == Decimal("0.14")


def test_find_cheapest_raises_no_capacity(client, mock_api):
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    with pytest.raises(NoCapacityError):
        client.inventory.find_cheapest(gpu_type="H100")


def test_instances_create_includes_required_fields(client, mock_api, sample_instance):
    """Verify the POST body matches the documented schema."""
    route = mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": sample_instance})
    )
    inst = client.instances.create(
        inventory_gpu_id="5ec7b784-fa6c-448c-a842-957d6d27b898",
        name="exp-1",
    )
    assert inst.name == "training-run-1"
    req = route.calls.last.request
    import json
    body = json.loads(req.content)
    assert body["inventory_gpu_id"] == "5ec7b784-fa6c-448c-a842-957d6d27b898"
    assert body["name"] == "exp-1"


def test_instance_estimated_spend_uses_decimal(sample_instance):
    """Money math stays Decimal — no float drift."""
    from substratecloud.models.instance import Instance

    inst = Instance.model_validate(sample_instance)
    assert isinstance(inst.estimated_spend, Decimal)


def test_find_by_name_returns_all_matches(client, mock_api, sample_instance):
    # API allows duplicate names. The SDK must return all of them.
    second = dict(sample_instance, id="11111111-1111-1111-1111-111111111111", name="dup")
    sample_instance["name"] = "dup"
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_instance, second]})
    )
    matches = client.instances.find_by_name("dup")
    assert len(matches) == 2
