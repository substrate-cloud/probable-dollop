"""`substrate plan` / `apply` / `destroy` — manifest-driven workflow."""

from __future__ import annotations

from pathlib import Path

import typer

from substrate.cli._common import console, err_console, handle_errors, make_client


def register(app: typer.Typer) -> None:
    @app.command("plan")
    @handle_errors
    def plan_cmd(
        manifest_path: Path = typer.Argument(..., exists=True, readable=True),
        profile: str | None = typer.Option(None, "--profile"),
        no_safety_net: bool = typer.Option(
            False, "--no-safety-net", help="Allow manifests with no budget/runtime/idle."
        ),
    ) -> None:
        """Dry-run an apply. Never calls POST /instances."""
        client = make_client(profile=profile)
        plan = client.plan(manifest_path, require_safety_net=not no_safety_net)
        console.print(plan.summary())

    @app.command("apply")
    @handle_errors
    def apply_cmd(
        manifest_path: Path = typer.Argument(..., exists=True, readable=True),
        profile: str | None = typer.Option(None, "--profile"),
        force: bool = typer.Option(False, "--force", help="Destroy and relaunch on drift."),
        no_safety_net: bool = typer.Option(
            False, "--no-safety-net", help="Allow manifests with no budget/runtime/idle."
        ),
    ) -> None:
        """Idempotent launch. Reuses an existing matching instance if found."""
        client = make_client(profile=profile)
        inst = client.apply(
            manifest_path,
            force=force,
            require_safety_net=not no_safety_net,
        )
        console.print(
            f"[green]Applied:[/green] {inst.name} ({inst.id}) status={inst.status.value}"
        )
        if inst.ip_address:
            console.print(f"  ssh: ssh {inst.ssh_user}@{inst.ip_address} -p {inst.ssh_port}")

    @app.command("destroy")
    @handle_errors
    def destroy_cmd(
        target: str = typer.Argument(..., help="Manifest name, or path to a manifest YAML."),
        profile: str | None = typer.Option(None, "--profile"),
        all_matches: bool = typer.Option(
            False, "--all", help="Delete every active instance matching the manifest tag."
        ),
    ) -> None:
        """Tear down instances launched by `apply`."""
        client = make_client(profile=profile)
        deleted = client.destroy(target, all_matches=all_matches)
        for inst in deleted:
            console.print(f"[yellow]Destroyed:[/yellow] {inst.name} ({inst.id})")
        if not deleted:
            err_console.print("[red]No matching instances destroyed.[/red]")
            raise typer.Exit(4)
