"""apply / plan / destroy — idempotency, drift detection, multi-match destroy."""

from __future__ import annotations

import copy

import httpx
import pytest

from substrate._http.errors import SubstrateError
from substrate.declarative import Manifest, Plan


# ─── helpers ──────────────────────────────────────────────────────────────


def _docker_manifest(**over) -> Manifest:
    data = {
        "name": "demo",
        "gpu": {"type": "A4000"},
        "workload": {
            "type": "docker",
            "image": "nginx:latest",
            "ports": {80: 80},
        },
        "lifecycle": {"budget_limit_usd": "5"},
    }
    data.update(over)
    return Manifest.model_validate(data)


def _instance_dict_for(name: str, *, with_launch_cfg: dict | None = None, **over) -> dict:
    d = {
        "id": "9745a7b7-a2e9-40c3-ad88-e8fc0f5ccbad",
        "name": name,
        "gpu_type": "A4000",
        "gpu_count": 1,
        "status": "active",
        "ip_address": "94.101.98.107",
        "ssh_user": "substrate",
        "ssh_port": 22,
        "cost_per_hour": 0.14,
        "tags": [f"manifest:{name}", "actor:test"],
        "created_at": "2026-03-23T12:56:38.605254+00:00",
        "updated_at": "2026-03-23T13:05:46.626072+00:00",
    }
    if with_launch_cfg is not None:
        d["launch_configuration"] = with_launch_cfg
    d.update(over)
    return d


def _matching_launch_cfg(manifest: Manifest) -> dict:
    """Construct a launch_configuration shape that matches the manifest."""
    wl = manifest.workload
    return {
        "type": "docker",
        "docker_configuration": {
            "image": wl.image,
            "args": " ".join(wl.args) if wl.args else None,
            "envs": [{"name": k, "value": "***"} for k in wl.env.keys()],
            "port_mappings": [
                {"container_port": c, "host_port": h} for c, h in wl.ports.items()
            ],
        },
    }


# ─── plan ──────────────────────────────────────────────────────────────────


def test_plan_create_when_no_existing(client, mock_api, sample_inventory_item):
    m = _docker_manifest()
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    p: Plan = client.plan(m)
    assert p.action == "create"
    assert p.existing_instance_id is None
    assert p.inventory_id is not None
    assert p.estimated_daily_usd is not None


def test_plan_never_creates_instance(client, mock_api, sample_inventory_item):
    m = _docker_manifest()
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    create_route = mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {}})
    )
    client.plan(m)
    assert create_route.call_count == 0


def test_plan_reuse_when_existing_matches(client, mock_api):
    m = _docker_manifest()
    inst = _instance_dict_for("demo", with_launch_cfg=_matching_launch_cfg(m))
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    p = client.plan(m)
    assert p.action == "reuse"
    assert p.existing_instance_id == inst["id"]


def test_plan_drift_when_image_differs(client, mock_api):
    m = _docker_manifest()
    drifted_cfg = _matching_launch_cfg(m)
    drifted_cfg["docker_configuration"]["image"] = "other:image"
    inst = _instance_dict_for("demo", with_launch_cfg=drifted_cfg)
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    p = client.plan(m)
    assert p.action == "drift_refused"
    assert any("image" in f for f in p.drift_fields)


# ─── apply ─────────────────────────────────────────────────────────────────


def test_apply_create_path(client, mock_api, sample_inventory_item):
    m = _docker_manifest()
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    created = _instance_dict_for("demo")
    mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": created})
    )
    # apply uses wait_until_active, so it'll GET /instance/:id at least once
    mock_api.get(f"/instance/{created['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": created})
    )
    inst = client.apply(m)
    assert inst.name == "demo"


def test_apply_reuse_path(client, mock_api):
    m = _docker_manifest()
    inst = _instance_dict_for("demo", with_launch_cfg=_matching_launch_cfg(m))
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    create_route = mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {}})
    )
    out = client.apply(m)
    assert out.name == "demo"
    assert create_route.call_count == 0  # crucial cost-safety assertion


def test_apply_drift_refused_without_force(client, mock_api):
    m = _docker_manifest()
    drifted_cfg = _matching_launch_cfg(m)
    drifted_cfg["docker_configuration"]["image"] = "other:image"
    inst = _instance_dict_for("demo", with_launch_cfg=drifted_cfg)
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    with pytest.raises(SubstrateError, match="apply.drift"):
        client.apply(m)


def test_apply_force_destroys_and_relaunches(
    client, mock_api, sample_inventory_item
):
    m = _docker_manifest()
    drifted_cfg = _matching_launch_cfg(m)
    drifted_cfg["docker_configuration"]["image"] = "other:image"
    old = _instance_dict_for("demo", with_launch_cfg=drifted_cfg)
    new = _instance_dict_for("demo", id="11111111-2222-3333-4444-555555555555")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [old]})
    )
    delete_route = mock_api.delete(f"/instance/{old['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": old})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": new})
    )
    mock_api.get(f"/instance/{new['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": new})
    )
    out = client.apply(m, force=True)
    assert str(out.id) == new["id"]
    assert delete_route.call_count == 1


def test_apply_requires_safety_net_by_default(client, mock_api):
    m = Manifest.model_validate({"name": "demo", "gpu": {"type": "A4000"}})
    with pytest.raises(SubstrateError, match="no safety net"):
        client.apply(m)


def test_apply_no_safety_net_with_opt_out(
    client, mock_api, sample_inventory_item
):
    m = Manifest.model_validate({"name": "demo", "gpu": {"type": "A4000"}})
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    created = _instance_dict_for("demo")
    mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": created})
    )
    mock_api.get(f"/instance/{created['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": created})
    )
    inst = client.apply(m, require_safety_net=False)
    assert inst.name == "demo"


# ─── destroy ──────────────────────────────────────────────────────────────


def test_destroy_single_match(client, mock_api):
    inst = _instance_dict_for("demo")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    delete_route = mock_api.delete(f"/instance/{inst['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": inst})
    )
    out = client.destroy("demo")
    assert len(out) == 1
    assert delete_route.call_count == 1


def test_destroy_multi_match_raises_without_all_flag(client, mock_api):
    a = _instance_dict_for("demo")
    b = _instance_dict_for("demo", id="11111111-1111-1111-1111-111111111111")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [a, b]})
    )
    with pytest.raises(SubstrateError, match="multiple active"):
        client.destroy("demo")


def test_destroy_multi_match_with_all_flag(client, mock_api):
    a = _instance_dict_for("demo")
    b = _instance_dict_for("demo", id="11111111-1111-1111-1111-111111111111")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [a, b]})
    )
    mock_api.delete(f"/instance/{a['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": a})
    )
    mock_api.delete(f"/instance/{b['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": b})
    )
    out = client.destroy("demo", all_matches=True)
    assert len(out) == 2


def test_destroy_no_match_raises(client, mock_api):
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    with pytest.raises(SubstrateError, match="no active instance"):
        client.destroy("demo")
