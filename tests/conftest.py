"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
import respx
from pydantic import SecretStr

from substratecloud._http.client import HttpClient
from substratecloud.client import SubstrateCloud


@pytest.fixture
def base_url() -> str:
    return "https://test.example.com/ondemand-mcp-manager"


@pytest.fixture
def token() -> SecretStr:
    return SecretStr("mcp_testtoken")


@pytest.fixture
def http(base_url: str, token: SecretStr) -> HttpClient:
    return HttpClient(base_url=base_url, token=token)


@pytest.fixture
def mock_api(base_url: str):
    """A respx mock router pre-bound to the test base URL."""
    with respx.mock(base_url=base_url, assert_all_called=False) as router:
        yield router


@pytest.fixture
def client(base_url: str, token: SecretStr, monkeypatch) -> SubstrateCloud:
    monkeypatch.setenv("SUBSTRATECLOUD_MCP_TOKEN", token.get_secret_value())
    monkeypatch.setenv("SUBSTRATECLOUD_API_BASE_URL", base_url)
    return SubstrateCloud()


@pytest.fixture
def sample_inventory_item() -> dict:
    return {
        "id": "5ec7b784-fa6c-448c-a842-957d6d27b898",
        "gpu_type": "A4000",
        "gpu_count": 1,
        "gpu_vram_gb": 16,
        "final_price_per_hour": 0.14,
        "region": "Europe",
        "os_options": ["ubuntu22.04_cuda12.8", "ubuntu22.04"],
    }


@pytest.fixture
def sample_instance() -> dict:
    return {
        "id": "9745a7b7-a2e9-40c3-ad88-e8fc0f5ccbad",
        "name": "training-run-1",
        "gpu_type": "A4000",
        "gpu_count": 1,
        "status": "active",
        "ip_address": "94.101.98.107",
        "ssh_user": "substratecloud",
        "ssh_port": 22,
        "cost_per_hour": 0.14,
        "tags": ["experiment-42"],
        "created_at": "2026-03-23T12:56:38.605254+00:00",
        "updated_at": "2026-03-23T13:05:46.626072+00:00",
    }
