"""Shared helpers for runnable examples."""

from __future__ import annotations

import os


def is_offline_ci() -> bool:
    """When set, examples must not call the API (used by tests)."""
    return os.environ.get("SUBSTRATE_EXAMPLES_OFFLINE", "0") == "1"


def is_live_run() -> bool:
    """True when SUBSTRATE_EXAMPLES_LIVE=1 and a token is configured."""
    return os.environ.get("SUBSTRATE_EXAMPLES_LIVE") == "1" and bool(
        os.environ.get("SUBSTRATE_MCP_TOKEN")
    )


def require_live() -> None:
    if not is_live_run():
        raise SystemExit(
            "Set SUBSTRATE_MCP_TOKEN and SUBSTRATE_EXAMPLES_LIVE=1 to launch for real."
        )
