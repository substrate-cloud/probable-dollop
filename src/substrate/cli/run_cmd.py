"""`substrate run` — full lifecycle: launch → wait → optionally terminate."""

from __future__ import annotations

from pathlib import Path

import typer

from substrate.cli._common import console, err_console, handle_errors, make_client


def register(app: typer.Typer) -> None:
    """Register the top-level `run` command on the root app."""

    @app.command("run")
    @handle_errors
    def run(
        workload_path: Path = typer.Argument(..., exists=True, readable=True),
        gpu: str | None = typer.Option(None, "--gpu"),
        name: str = typer.Option(..., "--name"),
        region: str | None = typer.Option(None, "--region"),
        max_price: float | None = typer.Option(None, "--max-price"),
        ssh_key: str | None = typer.Option(None, "--ssh-key"),
        os_image: str | None = typer.Option(None, "--os"),
        tag: list[str] = typer.Option([], "--tag"),
        until_done: bool = typer.Option(
            False,
            "--until-done",
            help="Block until the workload reports completion, then terminate.",
        ),
        timeout: int = typer.Option(900, "--timeout"),
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Launch a workload, wait, then (with --until-done) terminate.

        Without --until-done this is equivalent to `instance launch --workload`.
        With --until-done, the SDK polls for a completion marker and DELETEs
        the instance when done.
        """
        client = make_client(profile=profile)

        wl = _load_workload(workload_path)
        console.print(f"[bold]Launching[/bold] {name}…")
        inst = client.run(
            workload=wl,
            gpu=gpu,
            region_preference=[region] if region else None,
            max_price_per_hour=max_price,
            name=name,
            ssh_key=ssh_key,
            os=os_image,
            tags=tag,
            wait=True,
            wait_timeout=timeout,
        )
        console.print(f"[green]Active:[/green] {inst.name} @ {inst.ip_address}")

        if not until_done:
            return

        err_console.print(
            "[yellow]--until-done requires the workload to expose a completion signal "
            "(planned for v0.3; see plan doc §11.2). For now: SSH in and inspect, or "
            "use the JobRunner API.[/yellow]"
        )

    def _load_workload(path: Path):
        text = path.read_text()
        if path.suffix in (".yaml", ".yml"):
            import yaml  # type: ignore[import-untyped]
            spec = yaml.safe_load(text)
        else:
            import json
            spec = json.loads(text)
        kind = spec.get("kind", "docker")
        if kind == "docker":
            from substrate.workloads.docker import from_dict
            return from_dict(spec)
        err_console.print(f"Unsupported workload kind: {kind!r}")
        raise typer.Exit(2)
