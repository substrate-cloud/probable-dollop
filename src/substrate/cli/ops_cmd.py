"""`substrate check` / `show-gpus` / `logs` / `exec` / `cost` / `autostop`.

The auth/health and operations commands. Most ops commands are best-effort
client-side implementations (logs via SSH+journalctl, autostop as a local
timer); they print a clear caveat on every invocation.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

import typer

from substrate.cli._common import console, err_console, handle_errors, make_client, table_from
from substrate.declarative.duration import parse_duration


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
        """SkyPilot-style summary: cheapest available capacity per GPU family."""
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

    @app.command("logs")
    @handle_errors
    def logs_cmd(
        name: str = typer.Argument(...),
        tail: int = typer.Option(200, "--tail"),
        follow: bool = typer.Option(False, "--follow", "-f"),
        unit: str = typer.Option("", "--unit", help="systemd unit name; default: cloud-init.log"),
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Tail logs from an instance over SSH (journalctl or cloud-init).

        Requires SSH connectivity. Best-effort until the API exposes a logs endpoint.
        """
        client = make_client(profile=profile)
        inst = _resolve_instance_for_ops(client, name)
        cmd = _journalctl_or_cloud_init(unit=unit, tail=tail, follow=follow)
        _ssh_exec(inst, cmd, capture=False)

    @app.command("exec")
    @handle_errors
    def exec_cmd(
        ctx: typer.Context,
        name: str = typer.Argument(...),
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Run a command on an instance via SSH. Usage: `substrate exec NAME -- CMD ...`."""
        # Everything after `--` lives on ctx.args.
        if not ctx.args:
            err_console.print("[red]usage:[/red] substrate exec NAME -- CMD [args...]")
            raise typer.Exit(2)
        client = make_client(profile=profile)
        inst = _resolve_instance_for_ops(client, name)
        cmd = shlex.join(ctx.args)
        _ssh_exec(inst, cmd, capture=False)

    # Allow free-form args after `--` for exec.
    exec_cmd.__wrapped__.context_settings = {  # type: ignore[attr-defined]
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }

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

    @app.command("autostop")
    @handle_errors
    def autostop_cmd(
        name: str = typer.Argument(...),
        after: str = typer.Option(..., "--after", help="Duration e.g. '1h', '30m', '4h'."),
        profile: str | None = typer.Option(None, "--profile"),
    ) -> None:
        """Schedule auto-termination of an instance after a delay.

        Caveat: runs in this CLI process. If the terminal closes, the timer
        dies. Server-side enforcement is API-OPEN-QUESTION #4.
        """
        client = make_client(profile=profile)
        inst = _resolve_instance_for_ops(client, name)
        delay = parse_duration(after)
        err_console.print(
            f"[yellow]autostop: in-process timer for {after}. "
            f"Closing this terminal kills the timer.[/yellow]"
        )
        console.print(
            f"[bold]Scheduled[/bold] termination of {inst.name} ({inst.id}) at "
            f"{(datetime.now(timezone.utc).timestamp() + delay.total_seconds()):.0f} (UTC epoch). "
            f"Press Ctrl-C to cancel."
        )
        try:
            time.sleep(delay.total_seconds())
        except KeyboardInterrupt:
            err_console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(130) from None
        client.instances.delete(inst.id)
        console.print(f"[green]Terminated[/green] {inst.name} ({inst.id})")


# ─── helpers ──────────────────────────────────────────────────────────────


def _resolve_instance_for_ops(client, name_or_id: str):
    """Look up an instance by manifest tag, then by name, then by id."""
    by_tag = client.instances.find_by_tag(f"manifest:{name_or_id}")
    active = [i for i in by_tag if not i.status.is_terminal]
    if len(active) == 1:
        return active[0]
    by_name = client.instances.find_by_name(name_or_id)
    active = [i for i in by_name if not i.status.is_terminal]
    if len(active) == 1:
        return active[0]
    if not active:
        from substrate._http.errors import SubstrateError

        raise SubstrateError(f"no active instance found for {name_or_id!r}")
    raise SubstrateError(
        f"multiple active instances match {name_or_id!r}; pass an explicit id"
    )


def _ssh_exec(instance, cmd: str, *, capture: bool) -> str:
    """Run a command on the instance over SSH. Returns stdout if capture=True."""
    if instance.ip_address is None:
        from substrate._http.errors import SubstrateError

        raise SubstrateError(
            f"instance {instance.id} has no ip_address yet (status={instance.status.value})"
        )
    target = f"{instance.ssh_user}@{instance.ip_address}"
    ssh_cmd = ["ssh", "-p", str(instance.ssh_port or 22), target, cmd]
    if capture:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=False)
        return result.stdout
    # Stream live.
    result = subprocess.run(ssh_cmd, check=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
    return ""


def _journalctl_or_cloud_init(*, unit: str, tail: int, follow: bool) -> str:
    if unit:
        flag_follow = "-f" if follow else ""
        return f"sudo journalctl -u {shlex.quote(unit)} -n {int(tail)} {flag_follow}".strip()
    flag = "tail -n" if not follow else "tail -F"
    return f"sudo {flag} {int(tail)} /var/log/cloud-init.log /var/log/cloud-init-output.log 2>/dev/null"


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
