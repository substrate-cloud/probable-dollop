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


def test_find_cheapest_names_cheapest_when_priced_out(client, mock_api, sample_inventory_item):
    # When a max_price cap filters out everything, the error should name the
    # actual cheapest price so the user understands *why*, instead of a bare
    # "no inventory matched".
    expensive = dict(sample_inventory_item, final_price_per_hour=0.54)

    def responder(request):
        # The capped query returns nothing; an uncapped query reveals the real price.
        if request.url.params.get("max_price"):
            return httpx.Response(200, json={"success": True, "data": []})
        return httpx.Response(200, json={"success": True, "data": [expensive]})

    mock_api.get("/inventory").mock(side_effect=responder)
    with pytest.raises(NoCapacityError) as exc_info:
        client.inventory.find_cheapest(gpu_type="A4000", max_price=0.50)
    msg = str(exc_info.value)
    assert "0.54" in msg  # the real cheapest price
    assert "0.50" in msg  # the user's cap


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


def test_instance_accepts_null_cost_per_hour(sample_instance):
    # The API sends an explicit null while an instance is provisioning; that
    # must coerce to Decimal(0), not fail validation (it takes down every
    # command that lists instances).
    from substratecloud.models.instance import Instance

    sample_instance["cost_per_hour"] = None
    inst = Instance.model_validate(sample_instance)
    assert inst.cost_per_hour == Decimal(0)


def test_find_by_name_returns_all_matches(client, mock_api, sample_instance):
    # API allows duplicate names. The SDK must return all of them.
    second = dict(sample_instance, id="11111111-1111-1111-1111-111111111111", name="dup")
    sample_instance["name"] = "dup"
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_instance, second]})
    )
    matches = client.instances.find_by_name("dup")
    assert len(matches) == 2


def test_wait_until_active_timeout_raises_substratecloud_and_timeout(client, mock_api, sample_instance):
    # On timeout wait_until_active must raise a SubstrateCloudError subclass, so
    # the CLI's handle_errors prints a clean message instead of a traceback —
    # and it must stay a TimeoutError so existing `except TimeoutError` callers
    # keep working unchanged.
    from substratecloud._http.errors import SubstrateCloudError

    pending = dict(sample_instance, status="pending", ip_address=None)
    mock_api.get(f"/instance/{sample_instance['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": pending})
    )
    with pytest.raises(SubstrateCloudError) as exc_info:
        client.instances.wait_until_active(sample_instance["id"], timeout=0)
    assert isinstance(exc_info.value, TimeoutError)


def test_run_timeout_names_billing_instance_and_how_to_stop(
    client, mock_api, sample_instance, sample_inventory_item
):
    # On a slow provision, run(wait=True) times out but the instance is already
    # live and billing. The error must say which instance and how to stop it.
    from substratecloud._http.errors import WaitTimeoutError

    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": sample_instance})
    )
    pending = dict(sample_instance, status="pending", ip_address=None)
    mock_api.get(f"/instance/{sample_instance['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": pending})
    )
    with pytest.raises(WaitTimeoutError) as exc_info:
        client.run(gpu="A4000", name="exp-1", wait=True, wait_timeout=0)
    msg = str(exc_info.value)
    assert sample_instance["id"] in msg  # which instance is live
    assert "terminate" in msg.lower()  # how to stop billing
