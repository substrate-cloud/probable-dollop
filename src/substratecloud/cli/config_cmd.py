"""`substratecloud config ...` — interactive token + profile setup."""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import SecretStr
from rich.prompt import Confirm, IntPrompt, Prompt

from substratecloud import config as cfg
from substratecloud.cli._common import console, err_console, handle_errors

app = typer.Typer(help="Manage credentials and profiles.", no_args_is_help=True)


_DEFAULT_BASE_URL_HINT = "https://<your-supabase-project>.functions.supabase.co/ondemand-mcp-manager"


def _select_default_ssh_key(
    token: str, base_url: str, current_default: str | None
) -> str | None:
    """List the org's registered SSH keys and let the user pick a default.

    Returns the chosen key's UUID as a string, or None to leave it unset. Falls
    back to manual ID entry if the keys can't be listed (offline, bad token, …).
    """
    from substratecloud import SubstrateCloud

    try:
        with SubstrateCloud(token=token, base_url=base_url) as client:
            keys = client.ssh_keys.list()
    except Exception as exc:  # noqa: BLE001 — setup must not hard-fail on a list error
        console.print(f"[dim]Couldn't list SSH keys ({exc}).[/dim]")
        return (
            Prompt.ask(
                "Default SSH key ID [dim](optional)[/dim]", default=current_default or ""
            ).strip()
            or None
        )

    if not keys:
        console.print(
            "[dim]No SSH keys registered for this org "
            "(add one in the SubstrateCloud console). Skipping.[/dim]"
        )
        return None

    console.print("Available SSH keys:")
    for i, key in enumerate(keys, start=1):
        marker = (
            " [cyan](current)[/cyan]"
            if current_default and str(key.id) == current_default
            else ""
        )
        console.print(f"  [bold]{i}[/bold]. {key.name} [dim]{key.id}[/dim]{marker}")
    console.print("  [bold]0[/bold]. [dim]none / skip[/dim]")

    choice = IntPrompt.ask(
        "Select default SSH key",
        choices=[str(i) for i in range(len(keys) + 1)],
        default=0,
        show_choices=False,
    )
    if choice == 0:
        return None
    return str(keys[choice - 1].id)


@app.command("init")
@handle_errors
def init(
    profile: str = typer.Option("default", "--profile", "-p", help="Profile name to write."),
    config_path: Path | None = typer.Option(
        None, "--config", help="Override config file path (defaults to ~/.config/substratecloud/config.toml)."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite if the profile already exists."),
) -> None:
    """Interactively create or replace a credential profile.

    Prompts for: MCP token, API base URL, default region, default SSH key (optional).
    """
    path = config_path or cfg.DEFAULT_CONFIG_PATH
    current = cfg.load(path)

    if profile in current.profiles and not force:
        if not Confirm.ask(
            f"Profile [bold]{profile}[/bold] already exists. Overwrite?", default=False
        ):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(0)

    console.print(f"[bold]Configuring profile [cyan]{profile}[/cyan][/bold]")
    console.print(
        "[dim]Your MCP token is created from the SubstrateCloud console: "
        "Resources → MCP Keys.[/dim]"
    )

    token = Prompt.ask("MCP token", password=True)
    if not token.strip():
        err_console.print("Token cannot be empty.")
        raise typer.Exit(2)
    if not token.startswith("mcp_"):
        if not Confirm.ask(
            "[yellow]Token doesn't start with `mcp_`. Save anyway?[/yellow]", default=False
        ):
            raise typer.Exit(2)

    base_url = Prompt.ask(
        f"API base URL [dim](e.g. {_DEFAULT_BASE_URL_HINT})[/dim]",
        default=current.profiles.get(profile, cfg.Profile()).base_url or "",
    ).strip()
    if not base_url:
        err_console.print("Base URL is required.")
        raise typer.Exit(2)

    default_region = Prompt.ask(
        "Default region [dim](optional, e.g. Europe)[/dim]",
        default=current.profiles.get(profile, cfg.Profile()).default_region or "",
    ).strip() or None

    default_ssh_key_id = _select_default_ssh_key(
        token,
        base_url,
        current.profiles.get(profile, cfg.Profile()).default_ssh_key_id,
    )

    new_profile = cfg.Profile(
        token=SecretStr(token),
        base_url=base_url,
        default_region=default_region,
        default_ssh_key_id=default_ssh_key_id,
    )
    current.profiles[profile] = new_profile
    if current.active_profile not in current.profiles:
        current.active_profile = profile

    written = cfg.save(current, path)
    console.print(f"[green]Saved profile [bold]{profile}[/bold] to {written}[/green]")
    console.print("[dim]File mode set to 0600.[/dim]")


@app.command("use")
@handle_errors
def use(
    profile: str = typer.Argument(..., help="Profile to make active."),
    config_path: Path | None = typer.Option(None, "--config", help="Override config file path."),
) -> None:
    """Switch the active profile."""
    path = config_path or cfg.DEFAULT_CONFIG_PATH
    current = cfg.load(path)
    if profile not in current.profiles:
        err_console.print(
            f"No profile named [bold]{profile}[/bold]. Available: {', '.join(current.profiles)}"
        )
        raise typer.Exit(2)
    current.active_profile = profile
    cfg.save(current, path)
    console.print(f"[green]Active profile set to [bold]{profile}[/bold][/green]")


@app.command("ls")
@handle_errors
def list_profiles(
    config_path: Path | None = typer.Option(None, "--config", help="Override config file path."),
) -> None:
    """List available profiles."""
    path = config_path or cfg.DEFAULT_CONFIG_PATH
    current = cfg.load(path)
    if not current.profiles:
        console.print("[yellow]No profiles configured. Run `substratecloud config init`.[/yellow]")
        return
    for name, prof in current.profiles.items():
        marker = " [bold cyan](active)[/bold cyan]" if name == current.active_profile else ""
        console.print(
            f"• [bold]{name}[/bold]{marker} — base_url={prof.base_url or '?'} "
            f"region={prof.default_region or '?'}"
        )


@app.command("show")
@handle_errors
def show(
    profile: str | None = typer.Argument(None, help="Profile name (defaults to active)."),
    config_path: Path | None = typer.Option(None, "--config", help="Override config file path."),
) -> None:
    """Show a profile's settings (token redacted)."""
    path = config_path or cfg.DEFAULT_CONFIG_PATH
    current = cfg.load(path)
    name = profile or current.active_profile
    prof = current.profiles.get(name)
    if prof is None:
        err_console.print(f"No profile named [bold]{name}[/bold].")
        raise typer.Exit(2)
    console.print(f"[bold]Profile [cyan]{name}[/cyan][/bold]")
    console.print(f"  token        = {'mcp_***' if prof.token else '(unset)'}")
    console.print(f"  base_url     = {prof.base_url or '(unset)'}")
    console.print(f"  region       = {prof.default_region or '(unset)'}")
    console.print(f"  ssh_key_id   = {prof.default_ssh_key_id or '(unset)'}")
    console.print(f"  default_tags = {prof.default_tags or '[]'}")
