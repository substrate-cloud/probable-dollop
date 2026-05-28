"""CLI: substrate plan / apply / destroy / check / show-gpus."""

from __future__ import annotations

import textwrap
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from substrate.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def manifest_file(tmp_path: Path) -> Path:
    p = tmp_path / "substrate.yaml"
    p.write_text(
        textwrap.dedent(
            """\
            name: demo-cli
            gpu:
              type: A4000
            workload:
              type: docker
              image: nginx:latest
              ports:
                80: 80
            lifecycle:
              budget_limit_usd: '5'
            """
        )
    )
    return p


def _stub_env(monkeypatch, base_url):
    monkeypatch.setenv("SUBSTRATE_MCP_TOKEN", "mcp_testtoken")
    monkeypatch.setenv("SUBSTRATE_API_BASE_URL", base_url)


def test_cli_plan_outputs_summary(
    runner, manifest_file, monkeypatch, mock_api, sample_inventory_item
):
    _stub_env(monkeypatch, "https://test.example.com/ondemand-mcp-manager")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    create_route = mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {}})
    )
    result = runner.invoke(app, ["plan", str(manifest_file)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Plan for demo-cli" in result.stdout
    assert "Action       : create" in result.stdout
    assert create_route.call_count == 0


def test_cli_apply_idempotent_reuse(
    runner, manifest_file, monkeypatch, mock_api
):
    _stub_env(monkeypatch, "https://test.example.com/ondemand-mcp-manager")
    inst = {
        "id": "9745a7b7-a2e9-40c3-ad88-e8fc0f5ccbad",
        "name": "demo-cli",
        "gpu_type": "A4000",
        "gpu_count": 1,
        "status": "active",
        "ip_address": "94.101.98.107",
        "ssh_user": "substrate",
        "ssh_port": 22,
        "cost_per_hour": 0.14,
        "tags": ["manifest:demo-cli"],
        "created_at": "2026-03-23T12:56:38.605254+00:00",
        "updated_at": "2026-03-23T13:05:46.626072+00:00",
        "launch_configuration": {
            "type": "docker",
            "docker_configuration": {
                "image": "nginx:latest",
                "args": None,
                "envs": [],
                "port_mappings": [{"container_port": 80, "host_port": 80}],
            },
        },
    }
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    create_route = mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {}})
    )
    result = runner.invoke(app, ["apply", str(manifest_file)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Applied" in result.stdout
    assert create_route.call_count == 0  # idempotent reuse


def test_cli_destroy_single_match(runner, monkeypatch, mock_api):
    _stub_env(monkeypatch, "https://test.example.com/ondemand-mcp-manager")
    inst = {
        "id": "9745a7b7-a2e9-40c3-ad88-e8fc0f5ccbad",
        "name": "demo-cli",
        "gpu_type": "A4000",
        "gpu_count": 1,
        "status": "active",
        "ip_address": "94.101.98.107",
        "ssh_user": "substrate",
        "ssh_port": 22,
        "cost_per_hour": 0.14,
        "tags": ["manifest:demo-cli"],
        "created_at": "2026-03-23T12:56:38.605254+00:00",
        "updated_at": "2026-03-23T13:05:46.626072+00:00",
    }
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [inst]})
    )
    mock_api.delete(f"/instance/{inst['id']}").mock(
        return_value=httpx.Response(200, json={"success": True, "data": inst})
    )
    result = runner.invoke(app, ["destroy", "demo-cli"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Destroyed" in result.stdout


def test_cli_check_outputs_endpoint(runner, monkeypatch, mock_api):
    _stub_env(monkeypatch, "https://test.example.com/ondemand-mcp-manager")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "Endpoint" in result.stdout
    assert "Auth OK" in result.stdout


def test_cli_show_gpus(runner, monkeypatch, mock_api, sample_inventory_item):
    _stub_env(monkeypatch, "https://test.example.com/ondemand-mcp-manager")
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    result = runner.invoke(app, ["show-gpus"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "A4000" in result.stdout
