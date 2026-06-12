"""Typed exception tree for SubstrateCloud API errors."""

from __future__ import annotations

from typing import Any


class SubstrateCloudError(Exception):
    """Base for all SubstrateCloud SDK errors."""

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


class AuthError(SubstrateCloudError):
    """HTTP 401 — missing, invalid, or revoked MCP token."""


class NotFoundError(SubstrateCloudError):
    """HTTP 404 — resource missing or owned by a different organisation."""


class ValidationError(SubstrateCloudError):
    """HTTP 400 — invalid request body or parameters."""


class QuotaError(SubstrateCloudError):
    """HTTP 422 — e.g. token limit reached, capacity quota."""


class ServerError(SubstrateCloudError):
    """HTTP 5xx — SubstrateCloud-side error. Idempotent verbs are retried; POST is not."""


class TransportError(SubstrateCloudError):
    """Network failure, DNS, TLS, or timeout — never reached a SubstrateCloud server."""


class NoCapacityError(SubstrateCloudError):
    """No inventory item matched the requested specification."""


class WorkloadTimeoutError(SubstrateCloudError):
    """Workload health check did not pass within the deadline."""


class WaitTimeoutError(SubstrateCloudError, TimeoutError):
    """A poll/wait deadline was exceeded (e.g. `instances.wait_until_active`).

    Subclasses both `SubstrateCloudError` — so the CLI's `handle_errors`
    reports it as a clean message rather than dumping a traceback — and the
    builtin `TimeoutError`, so existing `except TimeoutError` callers keep
    working unchanged.
    """


_STATUS_MAP: dict[int, type[SubstrateCloudError]] = {
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
) -> SubstrateCloudError:
    """Map an HTTP status to the right exception class."""
    if status_code in _STATUS_MAP:
        exc_cls = _STATUS_MAP[status_code]
    elif 500 <= status_code < 600:
        exc_cls = ServerError
    else:
        exc_cls = SubstrateCloudError
    return exc_cls(
        message,
        status_code=status_code,
        route=route,
        request_id=request_id,
        body=body,
    )
