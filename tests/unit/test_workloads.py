"""Workload layer: Docker submission shape, Secret redaction, BootScript rendering."""

from __future__ import annotations

import pytest

from substrate import BootScript, DockerWorkload, Secret


def test_docker_workload_renders_documented_shape():
    wl = DockerWorkload(
        image="vllm/vllm-openai:latest",
        args=["--model", "mistralai/Mistral-7B-v0.1"],
        env={"HF_TOKEN": Secret.from_env("HF_TOKEN")},
        ports={8000: 8000},
    )
    import os
    os.environ["HF_TOKEN"] = "hf_dummy_for_test_only_dummy_for_test_only"
    try:
        cfg = wl.to_launch_configuration()
    finally:
        os.environ.pop("HF_TOKEN", None)
    assert cfg.type == "docker"
    assert cfg.docker_configuration.image == "vllm/vllm-openai:latest"
    assert cfg.docker_configuration.envs[0].name == "HF_TOKEN"


def test_secret_repr_never_leaks_value(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_aabbccddeeff00112233aabb")
    s = Secret.from_env("HF_TOKEN")
    assert "hf_aabbccdd" not in repr(s)
    assert "***" in repr(s)


def test_docker_workload_refuses_literal_secret():
    """Defence in depth: don't let a hf_... literal slip into launch_configuration."""
    wl = DockerWorkload(
        image="x",
        env={"HF_TOKEN": "hf_aabbccddeeff00112233aabbccddeeff"},  # literal string
    )
    with pytest.raises(ValueError, match="literal secret"):
        wl.to_launch_configuration()


def test_boot_script_renders_set_euo_pipefail():
    s = BootScript().with_base_image_setup().install_uv()
    out = s.render()
    assert "#!/usr/bin/env bash" in out
    assert "set -euo pipefail" in out
    assert "uv" in out


def test_boot_script_idempotent_install_uv():
    """Re-running the script must not break."""
    s = BootScript().install_uv()
    rendered = s.render()
    assert "command -v uv" in rendered  # checks first
