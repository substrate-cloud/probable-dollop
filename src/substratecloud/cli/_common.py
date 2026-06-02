"""Shared CLI helpers — client factory, output, error handling."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
except ImportError as exc:  # pragma: no cover — friendly error for missing extras
    raise SystemExit(
        "The substratecloud CLI requires the [cli] extras. Install with:\n"
        '    pip install "substratecloud[cli]"'
    ) from exc

from substratecloud import SubstrateCloud
from substratecloud._http.errors import SubstrateCloudError

console = Console()
err_console = Console(stderr=True, style="red")


def make_client(token: str | None = None, base_url: str | None = None, profile: str | None = None) -> SubstrateCloud:
    """Construct a SubstrateCloud client with friendly error reporting."""
    try:
        return SubstrateCloud(token=token, base_url=base_url, profile=profile)
    except SubstrateCloudError as exc:
        err_console.print(f"[bold red]Configuration error:[/bold red] {exc.message}")
        err_console.print(
            "[dim]Run [bold]substratecloud config init[/bold] to set up your credentials.[/dim]"
        )
        raise SystemExit(2) from None


def handle_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: convert SubstrateCloudError into a clean CLI error + exit code."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except SubstrateCloudError as exc:
            err_console.print(f"[bold red]{type(exc).__name__}:[/bold red] {exc.message}")
            if exc.status_code:
                err_console.print(f"[dim]HTTP {exc.status_code}  route={exc.route}[/dim]")
            sys.exit(_exit_code_for(exc))
        except KeyboardInterrupt:
            err_console.print("[yellow]Interrupted.[/yellow]")
            sys.exit(130)

    return wrapper


def _exit_code_for(exc: SubstrateCloudError) -> int:
    from substratecloud._http.errors import (
        AuthError,
        NotFoundError,
        QuotaError,
        ServerError,
        ValidationError,
    )

    if isinstance(exc, AuthError):
        return 2
    if isinstance(exc, ValidationError):
        return 3
    if isinstance(exc, NotFoundError):
        return 4
    if isinstance(exc, QuotaError):
        return 5
    if isinstance(exc, ServerError):
        return 6
    return 1


def table_from(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> Table:
    """Build a rich Table. `columns` is a list of (header, key)."""
    table = Table(show_header=True, header_style="bold cyan")
    for header, _ in columns:
        table.add_column(header)
    for row in rows:
        table.add_row(*[str(row.get(key, "") or "") for _, key in columns])
    return table
