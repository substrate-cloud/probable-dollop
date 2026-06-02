"""Validate all files under examples/ — no live API required."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from substratecloud.cli.main import app
from substratecloud.declarative.manifest import Manifest

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
MANIFESTS_DIR = EXAMPLES_ROOT / "manifests"
PYTHON_DIR = EXAMPLES_ROOT / "python"

MANIFEST_FILES = sorted(MANIFESTS_DIR.glob("*.yaml"))
PYTHON_SCRIPTS = sorted(PYTHON_DIR.glob("[0-9]*.py"))

BUILD_MANIFEST_SCRIPTS = {
    "01_quickstart_launch.py": "build_manifest",
    "05_fluent_docker_builder.py": "build_manifest",
    "06_fluent_boot_script.py": "build_manifest",
    "07_secrets_and_env.py": "build_manifest",
    "11_docker_workload_direct.py": "build_workload",
    "15_deploy_git_repo.py": "build_manifest",
}


def _load_module(script: Path):
    spec = importlib.util.spec_from_file_location(script.stem, script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PYTHON_DIR))
    try:
        spec.loader.exec_module(mod)
    finally:
        if str(PYTHON_DIR) in sys.path:
            sys.path.remove(str(PYTHON_DIR))
    return mod


@pytest.mark.parametrize("manifest_path", MANIFEST_FILES, ids=lambda p: p.name)
def test_example_manifest_parses(manifest_path: Path) -> None:
    m = Manifest.from_yaml(manifest_path)
    assert m.name
    assert m.has_safety_net(), f"{manifest_path.name} must set budget_limit_usd"


@pytest.mark.parametrize("manifest_path", MANIFEST_FILES, ids=lambda p: p.name)
def test_cli_plan_example_manifest(
    manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_api,
    sample_inventory_item: dict,
) -> None:
    monkeypatch.setenv("SUBSTRATECLOUD_MCP_TOKEN", "mcp_testtoken")
    monkeypatch.setenv("SUBSTRATECLOUD_API_BASE_URL", "https://test.example.com/ondemand-mcp-manager")
    mock_api.get("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )
    mock_api.get("/inventory").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [sample_inventory_item]})
    )
    create = mock_api.post("/instances").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {}})
    )
    runner = CliRunner()
    result = runner.invoke(app, ["plan", str(manifest_path)])
    assert result.exit_code == 0, result.stdout + result.stderr
    m = Manifest.from_yaml(manifest_path)
    assert m.name in result.stdout
    assert create.call_count == 0


@pytest.mark.parametrize(
    "script_name,builder_name",
    sorted(BUILD_MANIFEST_SCRIPTS.items()),
    ids=lambda x: x if isinstance(x, str) else "",
)
def test_example_builders(script_name: str, builder_name: str) -> None:
    mod = _load_module(PYTHON_DIR / script_name)
    builder = getattr(mod, builder_name)
    result = builder()
    assert result is not None


@pytest.mark.parametrize("script", PYTHON_SCRIPTS, ids=lambda p: p.name)
def test_example_script_runs_offline(script: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each example as a subprocess without live flag — must exit 0."""
    import os

    env = {
        **os.environ,
        "SUBSTRATECLOUD_EXAMPLES_OFFLINE": "1",
        "SUBSTRATECLOUD_MCP_TOKEN": "mcp_testtoken",
        "SUBSTRATECLOUD_API_BASE_URL": "https://test.example.com/ondemand-mcp-manager",
    }
    env.pop("SUBSTRATECLOUD_EXAMPLES_LIVE", None)
    # Scripts that only print offline messages still need a token for SubstrateCloud() + plan.
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=PYTHON_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_examples_readme_exists() -> None:
    assert (EXAMPLES_ROOT / "README.md").is_file()
    assert (EXAMPLES_ROOT / "cli" / "COMMANDS.md").is_file()
