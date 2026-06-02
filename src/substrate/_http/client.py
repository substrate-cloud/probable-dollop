"""HTTP transport — sync + async — built on httpx.

Responsibilities:
- Inject the MCP token Authorization header (token held as SecretStr).
- Retry idempotent verbs only; POST /instances is never auto-retried.
- Map HTTP status codes to typed SubstrateError subclasses.
- Emit structured request/response logs (no bodies, secrets redacted).
- Surface the request_id from response headers if present.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from typing import Any, cast

import httpx
from pydantic import SecretStr

from substrate._http.auth import bearer_header
from substrate._http.errors import (
    SubstrateError,
    TransportError,
    from_status,
)
from substrate._http.logging import get_logger
from substrate._http.retries import (
    RetryPolicy,
    is_retryable_transport_error,
    sleep_async,
    sleep_sync,
)
from substrate._version import __version__

_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
_USER_AGENT = f"substrate-python/{__version__}"

_log = get_logger("substrate.http")


class HttpClient:
    """Shared sync+async transport for the Substrate MCP API.

    Both `request` and `arequest` use the same retry policy and error mapping.
    """

    def __init__(
        self,
        *,
        base_url: str,
        token: SecretStr,
        timeout: httpx.Timeout | float | None = None,
        retry_policy: RetryPolicy | None = None,
        user_agent: str | None = None,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT
        self._retry_policy = retry_policy or RetryPolicy()
        self._user_agent = user_agent or _USER_AGENT
        self._transport = transport
        self._async_transport = async_transport
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    # -- lifecycle ------------------------------------------------------------

    def _ensure_sync(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=self._default_headers(),
                transport=self._transport,
            )
        return self._sync_client

    def _ensure_async(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=self._default_headers(),
                transport=self._async_transport,
            )
        return self._async_client

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            **bearer_header(self._token),
        }

    def close(self) -> None:
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def __enter__(self) -> HttpClient:
        self._ensure_sync()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    async def __aenter__(self) -> HttpClient:
        self._ensure_async()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    # -- sync request ---------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        client = self._ensure_sync()
        method = method.upper()
        attempt = 0
        last_exc: BaseException | None = None

        while True:
            attempt += 1
            request_id = uuid.uuid4().hex[:12]
            t0 = time.monotonic()
            try:
                response = client.request(
                    method,
                    path,
                    params=_drop_none(params),
                    json=json,
                    headers={"X-Request-Id": request_id},
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                latency_ms = int((time.monotonic() - t0) * 1000)
                _log.warning(
                    "substrate.http.transport_error",
                    method=method,
                    route=path,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    error=str(exc),
                )
                if is_retryable_transport_error(exc) and self._retry_policy.should_retry(
                    attempt, None, method
                ):
                    sleep_sync(self._retry_policy.delay_for(attempt))
                    continue
                raise TransportError(
                    f"Transport error contacting Substrate: {exc}",
                    route=path,
                    request_id=request_id,
                ) from exc

            srv_request_id = response.headers.get("x-request-id") or request_id

            if 200 <= response.status_code < 300:
                return _decode(response, path, srv_request_id)

            if self._retry_policy.should_retry(attempt, response.status_code, method):
                sleep_sync(self._retry_policy.delay_for(attempt))
                continue

            raise _http_error(response, path, srv_request_id)

        # unreachable; keeps mypy happy if loop logic changes
        raise TransportError(f"Exhausted retries: {last_exc}")  # pragma: no cover

    # -- async request --------------------------------------------------------

    async def arequest(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        client = self._ensure_async()
        method = method.upper()
        attempt = 0
        last_exc: BaseException | None = None

        while True:
            attempt += 1
            request_id = uuid.uuid4().hex[:12]
            t0 = time.monotonic()
            try:
                response = await client.request(
                    method,
                    path,
                    params=_drop_none(params),
                    json=json,
                    headers={"X-Request-Id": request_id},
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                latency_ms = int((time.monotonic() - t0) * 1000)
                _log.warning(
                    "substrate.http.transport_error",
                    method=method,
                    route=path,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    error=str(exc),
                )
                if is_retryable_transport_error(exc) and self._retry_policy.should_retry(
                    attempt, None, method
                ):
                    await sleep_async(self._retry_policy.delay_for(attempt))
                    continue
                raise TransportError(
                    f"Transport error contacting Substrate: {exc}",
                    route=path,
                    request_id=request_id,
                ) from exc

            srv_request_id = response.headers.get("x-request-id") or request_id

            if 200 <= response.status_code < 300:
                return _decode(response, path, srv_request_id)

            if self._retry_policy.should_retry(attempt, response.status_code, method):
                await sleep_async(self._retry_policy.delay_for(attempt))
                continue

            raise _http_error(response, path, srv_request_id)

        raise TransportError(f"Exhausted retries: {last_exc}")  # pragma: no cover

    # -- repr scrubs token ----------------------------------------------------

    def __repr__(self) -> str:
        return f"HttpClient(base_url={self._base_url!r}, token=***)"


def _drop_none(params: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if params is None:
        return None
    return {k: v for k, v in params.items() if v is not None}


def _decode(response: httpx.Response, route: str, request_id: str) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise SubstrateError(
            f"Substrate returned non-JSON body (status {response.status_code})",
            status_code=response.status_code,
            route=route,
            request_id=request_id,
            body=response.text[:500],
        ) from exc


def _http_error(response: httpx.Response, route: str, request_id: str) -> SubstrateError:
    body: Any
    try:
        body = response.json()
    except ValueError:
        body = response.text[:500]

    message: str
    if isinstance(body, dict) and "error" in body:
        message = cast(str, body["error"])
    else:
        message = f"HTTP {response.status_code}"

    return from_status(
        response.status_code,
        message,
        route=route,
        request_id=request_id,
        body=body,
    )
