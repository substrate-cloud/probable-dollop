"""Shared helpers for runnable examples."""

from __future__ import annotations

import os


def is_offline_ci() -> bool:
    """When set, examples must not call the API (used by tests)."""
    return os.environ.get("SUBSTRATECLOUD_EXAMPLES_OFFLINE", "0") == "1"


def is_live_run() -> bool:
    """True when SUBSTRATECLOUD_EXAMPLES_LIVE=1 and a token is configured."""
    return os.environ.get("SUBSTRATECLOUD_EXAMPLES_LIVE") == "1" and bool(
        os.environ.get("SUBSTRATECLOUD_MCP_TOKEN")
    )


def require_live() -> None:
    if not is_live_run():
        raise SystemExit(
            "Set SUBSTRATECLOUD_MCP_TOKEN and SUBSTRATECLOUD_EXAMPLES_LIVE=1 to launch for real."
        )
