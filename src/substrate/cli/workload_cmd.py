"""`substrate workload ...` — validate / render workload specs without launching."""

from __future__ import annotations

from pathlib import Path

import typer

from substrate.cli._common import console, err_console, handle_errors

app = typer.Typer(help="Inspect workload specs without launching.", no_args_is_help=True)


@app.command("validate")
@handle_errors
def validate(
    path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Parse and validate a workload YAML/JSON. Does not contact the API."""
    spec = _load(path)
    kind = spec.get("kind", "docker")
    if kind == "docker":
        from substrate.workloads.docker import from_dict
        wl = from_dict(spec)
        console.print(f"[green]OK[/green] DockerWorkload(image={wl.image!r}, ports={wl.ports})")
    else:
        err_console.print(f"Unsupported workload kind: {kind!r}")
        raise typer.Exit(2)


@app.command("render")
@handle_errors
def render(
    path: Path | None = typer.Option(None, "--from", "-f", help="Boot-script YAML."),
    output: Path | None = typer.Option(None, "-o", help="Write rendered bash to this file."),
) -> None:
    """Render a BootScript spec to bash without submitting.

    Useful for code review and for dropping a static script into version control.
    """
    if path is None:
        err_console.print("Pass --from <boot-script.yaml>.")
        raise typer.Exit(2)
    err_console.print(
        "[yellow]Boot-script YAML format is under active design. "
        "For now, render via Python (see docs/recipes/boot-script.md).[/yellow]"
    )
    raise typer.Exit(1)


def _load(path: Path) -> dict:
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            err_console.print("YAML workloads require PyYAML. `pip install pyyaml`.")
            raise typer.Exit(2)
        return yaml.safe_load(text)
    import json
    return json.loads(text)
