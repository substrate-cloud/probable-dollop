"""`substrate instance ...` — lifecycle commands."""

from __future__ import annotations

from uuid import UUID

import typer
from rich.prompt import Confirm

from substrate.cli._common import console, err_console, handle_errors, make_client, table_from
from substrate.models.enums import InstanceStatus

app = typer.Typer(help="Manage GPU instances.", no_args_is_help=True)


@app.command("ls")
@handle_errors
def ls(
    tag: str | None = typer.Option(None, "--tag", help="Filter by tag substring."),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    """List active instances."""
    client = make_client(profile=profile)
    instances = client.instances.list()
    if tag:
        instances = [i for i in instances if any(tag in t for t in i.tags)]
    if not instances:
        console.print("[yellow]No instances.[/yellow]")
        return
    rows = [
        {
            "id": str(i.id),
            "name": i.name,
            "status": i.status.value,
            "gpu": f"{i.gpu_count}x{i.gpu_type}" if i.gpu_count else i.gpu_type or "",
            "ip": str(i.ip_address) if i.ip_address else "—",
            "price": f"€{i.cost_per_hour}/hr",
            "tags": ", ".join(i.tags),
        }
        for i in instances
    ]
    console.print(
        table_from(
            rows,
            columns=[
                ("ID", "id"),
                ("Name", "name"),
                ("Status", "status"),
                ("GPU", "gpu"),
                ("IP", "ip"),
                ("Price", "price"),
                ("Tags", "tags"),
            ],
        )
    )


@app.command("get")
@handle_errors
def get(
    id_or_name: str = typer.Argument(..., help="Instance UUID or name."),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    """Show details for one instance."""
    client = make_client(profile=profile)
    inst = _resolve_instance(client, id_or_name)
    console.print(f"[bold]{inst.name}[/bold] ({inst.id})")
    console.print(f"  status      = {inst.status.value}")
    console.print(f"  gpu         = {inst.gpu_count}x{inst.gpu_type}")
    console.print(f"  ip          = {inst.ip_address}")
    if inst.ip_address and inst.ssh_user:
        console.print(
            f"  connect     = ssh {inst.ssh_user}@{inst.ip_address} -p {inst.ssh_port or 22}"
        )
    console.print(f"  cost/hr     = €{inst.cost_per_hour}")
    console.print(f"  uptime      = {inst.uptime}")
    console.print(f"  est. spend  = €{inst.estimated_spend}")
    console.print(f"  tags        = {inst.tags}")


@app.command("launch")
@handle_errors
def launch(
    gpu: str | None = typer.Option(None, "--gpu", help="GPU type selector."),
    name: str = typer.Option(..., "--name", help="Instance display name."),
    region: str | None = typer.Option(None, "--region"),
    max_price: float | None = typer.Option(None, "--max-price"),
    ssh_key: str | None = typer.Option(None, "--ssh-key", help="SSH key name or UUID."),
    os_image: str | None = typer.Option(None, "--os", help="OS option exact string."),
    tag: list[str] = typer.Option([], "--tag", help="Add a tag (repeatable)."),
    workload: str | None = typer.Option(
        None, "--workload", help="Path to workload YAML/JSON (optional)."
    ),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Block until active."),
    timeout: int = typer.Option(600, "--timeout", help="Wait timeout (seconds)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip cost confirmation."),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    """Launch a new instance. Prints estimated daily spend before billing starts."""
    client = make_client(profile=profile)

    # Find capacity first so we can show price BEFORE the user confirms.
    item = client.inventory.find_cheapest(
        gpu_type=gpu, location=region, max_price=max_price
    )
    daily = item.final_price_per_hour * 24
    weekly = daily * 7
    console.print(
        f"\n[bold]Selected:[/bold] {item}\n"
        f"  est. €{daily:.2f}/day  €{weekly:.2f}/week\n"
    )

    if not yes:
        if not Confirm.ask("Proceed with launch?", default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    wl = _load_workload(workload) if workload else None
    inst = client.run(
        workload=wl,
        gpu=gpu or item.gpu_type,
        region_preference=[region] if region else None,
        max_price_per_hour=max_price,
        name=name,
        ssh_key=ssh_key,
        os=os_image or item.default_os,
        tags=tag,
        wait=wait,
        wait_timeout=timeout,
    )
    console.print(f"[green]Launched[/green] {inst.name} ({inst.id})  status={inst.status.value}")
    console.print(
        "[dim]Billing stops only on terminate/delete. "
        "Use `substrate destroy` for manifest-driven launches.[/dim]"
    )


@app.command("terminate")
@handle_errors
def terminate(
    id_or_name: str | None = typer.Argument(None, help="Instance UUID or name."),
    all_tagged: str | None = typer.Option(
        None, "--all-tagged", help="Delete every instance carrying this tag."
    ),
    yes: bool = typer.Option(False, "--yes", "-y"),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    """Terminate one or many instances. Irreversible — stops billing."""
    client = make_client(profile=profile)

    targets = []
    if all_tagged:
        targets = client.instances.find_by_tag(all_tagged)
        if not targets:
            console.print(f"[yellow]No instances with tag {all_tagged!r}.[/yellow]")
            raise typer.Exit(0)
    elif id_or_name:
        targets = [_resolve_instance(client, id_or_name)]
    else:
        err_console.print("Supply an id/name or --all-tagged.")
        raise typer.Exit(2)

    console.print(
        f"About to terminate {len(targets)} instance(s):  "
        + ", ".join(f"{t.name} ({t.id})" for t in targets)
    )
    if not yes and not Confirm.ask("Confirm DELETE?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(0)

    deleted = client.instances.delete_many([t.id for t in targets])
    console.print(f"[green]Deleted {len(deleted)} instance(s).[/green]")


def _resolve_instance(client, ident: str):
    """Resolve UUID or name. Names are not unique — disambiguate by status/active."""
    try:
        UUID(ident)
        return client.instances.get(ident)
    except (ValueError, AttributeError):
        matches = client.instances.find_by_name(ident)
        active = [m for m in matches if m.status != InstanceStatus.DELETED]
        if not active:
            from substrate._http.errors import NotFoundError
            raise NotFoundError(f"No instance named {ident!r}.")
        if len(active) > 1:
            ids = ", ".join(str(m.id) for m in active)
            err_console.print(
                f"[yellow]Multiple instances named {ident!r}. "
                f"Pass an explicit UUID: {ids}[/yellow]"
            )
            raise typer.Exit(2)
        return active[0]


def _load_workload(path: str):
    """Load a workload spec from YAML/JSON. Format documented in docs/recipes/workload-yaml.md."""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        err_console.print(f"Workload file not found: {path}")
        raise typer.Exit(2)
    text = p.read_text()
    if p.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            err_console.print("YAML workloads require PyYAML. `pip install pyyaml`.")
            raise typer.Exit(2)
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
