"""structlog setup with secret redaction at the formatter level."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from structlog.types import EventDict

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(mcp_[A-Za-z0-9_-]{8,})"), "mcp_***"),
    (re.compile(r"(hf_[A-Za-z0-9]{20,})"), "hf_***"),
    (re.compile(r"(AKIA[0-9A-Z]{16})"), "AKIA***"),
    (re.compile(r"(ghp_[A-Za-z0-9]{30,})"), "ghp_***"),
    (re.compile(r"(sk-[A-Za-z0-9]{20,})"), "sk-***"),
]

_REDACT_KEYS = {
    "token",
    "mcp_token",
    "authorization",
    "auth",
    "password",
    "secret",
    "api_key",
    "hf_token",
}


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern, replacement in _REDACT_PATTERNS:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in _REDACT_KEYS else _redact_value(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v) for v in value)
    return value


def _redact_processor(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    return _redact_value(event_dict)  # type: ignore[return-value]


_configured = False


def configure(level: int | str = logging.INFO, json_output: bool | None = None) -> None:
    """Configure structlog. Idempotent.

    json_output=None auto-detects: JSON when not a TTY (suitable for log aggregators),
    pretty otherwise.
    """
    global _configured
    if _configured:
        return

    if json_output is None:
        json_output = not sys.stderr.isatty()

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact_processor,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            level if isinstance(level, int) else logging.getLevelName(level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "substratecloud") -> Any:
    configure()
    return structlog.get_logger(name)
