"""Shared helpers for resource managers.

The Substrate MCP API wraps successful responses in `{"success": true, "data": ...}`.
This module unwraps that envelope once so individual managers stay terse.
"""

from __future__ import annotations

from typing import Any

from substrate._http.errors import SubstrateError


def unwrap(response: Any, *, route: str) -> Any:
    """Extract the `data` field from a Substrate envelope.

    Raises SubstrateError if the envelope is malformed — should never happen
    on a successful 2xx but defensive in case the API changes shape.
    """
    if response is None:
        return None
    if not isinstance(response, dict):
        raise SubstrateError(
            f"Unexpected non-object response from {route}", route=route, body=response
        )
    if "data" in response:
        return response["data"]
    # Some endpoints (DELETE) return {"success": True, "message": "...", "data": {...}}
    # but others may omit data. Tolerate both.
    return response
