"""`substrate inventory ...` — browse GPU capacity."""

from __future__ import annotations

import typer

from substrate.cli._common import console, handle_errors, make_client, table_from

app = typer.Typer(help="Browse available GPUs.", no_args_is_help=True)


@app.command("ls")
@handle_errors
def ls(
    gpu: str | None = typer.Option(None, "--gpu", help="GPU type (e.g. H100, A100)."),
    location: str | None = typer.Option(None, "--location", help="Region substring."),
    gpu_count: int | None = typer.Option(None, "--gpu-count", help="Exact GPU count."),
    max_price: float | None = typer.Option(None, "--max-price", help="Max €/hr."),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    """List available GPU configurations, sorted cheapest first."""
    client = make_client(profile=profile)
    items = client.inventory.list(
        gpu_type=gpu,
        location=location,
        gpu_count=gpu_count,
        max_price=max_price,
    )
    if not items:
        console.print("[yellow]No inventory matched.[/yellow]")
        raise typer.Exit(0)

    rows = [
        {
            "id": str(i.id),
            "gpu": i.gpu_type,
            "count": i.gpu_count,
            "vram": f"{i.gpu_vram_gb}GB",
            "price": f"€{i.final_price_per_hour}/hr",
            "region": i.region,
            "os": ", ".join(i.os_options[:2]) + ("…" if len(i.os_options) > 2 else ""),
        }
        for i in items
    ]
    console.print(
        table_from(
            rows,
            columns=[
                ("ID", "id"),
                ("GPU", "gpu"),
                ("#", "count"),
                ("VRAM", "vram"),
                ("Price", "price"),
                ("Region", "region"),
                ("OS", "os"),
            ],
        )
    )


@app.command("cheapest")
@handle_errors
def cheapest(
    gpu: str | None = typer.Option(None, "--gpu"),
    location: str | None = typer.Option(None, "--location", "--region"),
    min_count: int = typer.Option(1, "--min-count"),
    max_price: float | None = typer.Option(None, "--max-price"),
    profile: str | None = typer.Option(None, "--profile"),
) -> None:
    """Print the cheapest matching inventory item."""
    client = make_client(profile=profile)
    item = client.inventory.find_cheapest(
        gpu_type=gpu, location=location, min_count=min_count, max_price=max_price
    )
    console.print(
        f"[bold]{item}[/bold]\n  id={item.id}\n  default_os={item.default_os}"
    )
