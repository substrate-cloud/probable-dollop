"""SubstrateCloud CLI root Typer app."""

from __future__ import annotations

import typer

from substratecloud import __version__
from substratecloud.cli import (
    config_cmd,
    instance_cmd,
    inventory_cmd,
    manifest_cmd,
    ops_cmd,
    run_cmd,
    workload_cmd,
)
from substratecloud.cli._common import console

app = typer.Typer(
    help="SubstrateCloud — typed CLI for the SubstrateCloud On-Demand GPU platform.",
    no_args_is_help=True,
    add_completion=False,
    invoke_without_command=True,
)

app.add_typer(config_cmd.app, name="config", help="Manage credentials and profiles.")
app.add_typer(inventory_cmd.app, name="inventory", help="Browse available GPUs.")
app.add_typer(instance_cmd.app, name="instance", help="Manage GPU instances.")
app.add_typer(workload_cmd.app, name="workload", help="Inspect workload specs.")
run_cmd.register(app)
manifest_cmd.register(app)
ops_cmd.register(app)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"substratecloud {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Print version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    if ctx.invoked_subcommand is None and not version:
        console.print(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
