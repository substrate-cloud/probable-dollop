"""`substrate check` / `show-gpus` / `cost` — auth, inventory summary, spend estimates."""

from __future__ import annotations

from decimal import Decimal

import typer

from substrate.cli._common import console, err_console, handle_errors, make_client, table_from


def register(app: typer.Typer) -> None:
    @app.command("check")
    @handle_errors
    def check_cmd(
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Validate that the configured token and base URL work."""
        client = make_client(profile=profile)
        console.print(f"[bold]Endpoint:[/bold] {client.base_url}")
        # Try a lightweight call.
        try:
            instances = client.instances.list()
            console.print(f"[green]Auth OK[/green]  (saw {len(instances)} instance(s))")
        except Exception as exc:  # noqa: BLE001
            err_console.print(f"[red]Auth check failed:[/red] {exc}")
            raise typer.Exit(2) from None

    @app.command("show-gpus")
    @handle_errors
    def show_gpus_cmd(
        max_price: float | None = typer.Option(None, "--max-price"),
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Summary of the cheapest available capacity per GPU family."""
        client = make_client(profile=profile)
        items = client.inventory.list(max_price=max_price)
        if not items:
            console.print("[yellow]No inventory matches.[/yellow]")
            return
        # Group by gpu_type, pick cheapest each.
        by_type: dict[str, list] = {}
        for it in items:
            by_type.setdefault(it.gpu_type, []).append(it)
        rows = []
        for gpu_type, group in sorted(by_type.items()):
            cheapest = min(group, key=lambda x: x.final_price_per_hour)
            rows.append(
                {
                    "gpu": gpu_type,
                    "count": str(cheapest.gpu_count),
                    "vram": f"{cheapest.gpu_vram_gb}GB",
                    "region": str(cheapest.region),
                    "price": f"${cheapest.final_price_per_hour}/hr",
                    "available": str(len(group)),
                }
            )
        table = table_from(
            rows,
            [
                ("GPU", "gpu"),
                ("Count", "count"),
                ("VRAM", "vram"),
                ("Cheapest in", "region"),
                ("Price", "price"),
                ("# Listings", "available"),
            ],
        )
        console.print(table)

    @app.command("cost")
    @handle_errors
    def cost_cmd(
        tag: list[str] = typer.Option([], "--tag", help="Filter by tag (repeatable)."),
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Client-side cost report. Estimates spend = uptime × cost_per_hour."""
        client = make_client(profile=profile)
        instances = client.instances.list()
        if tag:
            instances = [i for i in instances if all(t in i.tags for t in tag)]
        rows = []
        total = Decimal(0)
        for inst in instances:
            rows.append(
                {
                    "name": inst.name,
                    "id": str(inst.id)[:8],
                    "gpu": inst.gpu_type or "",
                    "status": inst.status.value,
                    "uptime": _humanize_uptime(inst.uptime.total_seconds()),
                    "rate": f"${inst.cost_per_hour}/hr",
                    "spend": f"${inst.estimated_spend}",
                }
            )
            total += inst.estimated_spend
        table = table_from(
            rows,
            [
                ("Name", "name"),
                ("ID", "id"),
                ("GPU", "gpu"),
                ("Status", "status"),
                ("Uptime", "uptime"),
                ("Rate", "rate"),
                ("Spend", "spend"),
            ],
        )
        console.print(table)
        console.print(f"[bold]Total estimated spend:[/bold] ${total}")


def _humanize_uptime(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"
