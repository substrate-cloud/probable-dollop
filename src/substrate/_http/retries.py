"""Retry policy: exponential backoff with jitter — idempotent verbs only.

POST /instances is NEVER retried automatically. A 5xx during instance creation
may have already created a (billed) instance — silent retry would duplicate it.
The SDK surfaces the error and lets the caller decide.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx

T = TypeVar("T")

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "DELETE", "PATCH", "PUT", "OPTIONS"})


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_initial_s: float = 0.5
    backoff_factor: float = 2.0
    backoff_max_s: float = 8.0
    jitter: float = 0.2  # 20% jitter
    retryable_statuses: frozenset[int] = frozenset({429, 500, 502, 503, 504})

    def is_idempotent(self, method: str) -> bool:
        return method.upper() in IDEMPOTENT_METHODS

    def should_retry(self, attempt: int, status: int | None, method: str) -> bool:
        if attempt >= self.max_attempts:
            return False
        if not self.is_idempotent(method):
            return False
        if status is None:
            return True  # transport-level — retry within idempotent budget
        return status in self.retryable_statuses

    def delay_for(self, attempt: int) -> float:
        base = min(
            self.backoff_initial_s * (self.backoff_factor ** (attempt - 1)),
            self.backoff_max_s,
        )
        return base * (1 + random.uniform(-self.jitter, self.jitter))


def sleep_sync(seconds: float) -> None:
    time.sleep(seconds)


async def sleep_async(seconds: float) -> None:
    await asyncio.sleep(seconds)


def is_retryable_transport_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


__all__ = [
    "RetryPolicy",
    "IDEMPOTENT_METHODS",
    "sleep_sync",
    "sleep_async",
    "is_retryable_transport_error",
]
