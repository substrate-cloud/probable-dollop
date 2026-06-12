"""Layer 1 HTTP behaviour: auth header, error mapping, retry policy."""

from __future__ import annotations

import httpx
import pytest

from substratecloud._http.errors import (
    AuthError,
    NotFoundError,
    QuotaError,
    ServerError,
    ValidationError,
)


def test_get_inventory_sends_bearer_token(http, mock_api):
    route = mock_api.get("/inventory").mock(return_value=httpx.Response(200, json={"data": []}))
    http.request("GET", "/inventory")
    assert route.called
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer mcp_testtoken"


def test_repr_redacts_token(http):
    assert "mcp_testtoken" not in repr(http)
    assert "***" in repr(http)


@pytest.mark.parametrize(
    "status,exc_cls",
    [
        (400, ValidationError),
        (401, AuthError),
        (404, NotFoundError),
        (422, QuotaError),
        (500, ServerError),
    ],
)
def test_error_status_mapping(http, mock_api, status, exc_cls):
    mock_api.get("/instances").mock(
        return_value=httpx.Response(status, json={"error": "nope"})
    )
    with pytest.raises(exc_cls) as exc:
        http.request("GET", "/instances")
    assert exc.value.status_code == status


def test_post_instances_does_not_auto_retry(http, mock_api):
    """The single most important cost-safety guarantee."""
    route = mock_api.post("/instances").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    with pytest.raises(ServerError):
        http.request("POST", "/instances", json={"inventory_gpu_id": "x", "name": "y"})
    assert route.call_count == 1, "POST /instances must not retry on 5xx"


def test_idempotent_get_retries_on_5xx(http, mock_api):
    """GET should retry; default budget is 3 attempts."""
    responses = [
        httpx.Response(500, json={"error": "transient"}),
        httpx.Response(500, json={"error": "transient"}),
        httpx.Response(200, json={"data": []}),
    ]
    mock_api.get("/inventory").mock(side_effect=responses)
    out = http.request("GET", "/inventory")
    assert out == {"data": []}


def test_resolve_base_url_warns_on_plain_http():
    # A non-https base URL means the bearer token goes out in cleartext.
    from substratecloud._http.auth import resolve_base_url

    with pytest.warns(UserWarning, match="(?i)cleartext|https"):
        resolve_base_url("http://gpu.example.com")


def test_resolve_base_url_silent_on_https():
    import warnings as _warnings

    from substratecloud._http.auth import resolve_base_url

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")  # any warning would fail the test
        assert resolve_base_url("https://gpu.example.com") == "https://gpu.example.com"


def test_resolve_base_url_silent_on_localhost_http():
    # Plain http to localhost is a normal dev pattern; no warning.
    import warnings as _warnings

    from substratecloud._http.auth import resolve_base_url

    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        resolve_base_url("http://localhost:8080")
