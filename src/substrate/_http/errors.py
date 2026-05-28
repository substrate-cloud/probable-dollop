"""Typed exception tree for Substrate API errors."""

from __future__ import annotations

from typing import Any


class SubstrateError(Exception):
    """Base for all Substrate SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
        route: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.route = route
        self.body = body

    def __repr__(self) -> str:
        parts = [f"message={self.message!r}"]
        if self.status_code is not None:
            parts.append(f"status_code={self.status_code}")
        if self.route:
            parts.append(f"route={self.route!r}")
        if self.request_id:
            parts.append(f"request_id={self.request_id!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class AuthError(SubstrateError):
    """HTTP 401 — missing, invalid, or revoked MCP token."""


class NotFoundError(SubstrateError):
    """HTTP 404 — resource missing or owned by a different organisation."""


class ValidationError(SubstrateError):
    """HTTP 400 — invalid request body or parameters."""


class QuotaError(SubstrateError):
    """HTTP 422 — e.g. token limit reached, capacity quota."""


class ServerError(SubstrateError):
    """HTTP 5xx — Substrate-side error. Idempotent verbs are retried; POST is not."""


class TransportError(SubstrateError):
    """Network failure, DNS, TLS, or timeout — never reached a Substrate server."""


class NoCapacityError(SubstrateError):
    """No inventory item matched the requested specification."""


class WorkloadTimeoutError(SubstrateError):
    """Workload health check did not pass within the deadline."""


_STATUS_MAP: dict[int, type[SubstrateError]] = {
    400: ValidationError,
    401: AuthError,
    404: NotFoundError,
    422: QuotaError,
}


def from_status(
    status_code: int,
    message: str,
    *,
    route: str | None = None,
    request_id: str | None = None,
    body: Any = None,
) -> SubstrateError:
    """Map an HTTP status to the right exception class."""
    if status_code in _STATUS_MAP:
        exc_cls = _STATUS_MAP[status_code]
    elif 500 <= status_code < 600:
        exc_cls = ServerError
    else:
        exc_cls = SubstrateError
    return exc_cls(
        message,
        status_code=status_code,
        route=route,
        request_id=request_id,
        body=body,
    )
