"""Workload layer: Docker submission shape, Secret redaction, BootScript rendering."""

from __future__ import annotations

import pytest

from substratecloud import BootScript, DockerWorkload, Secret


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


def test_systemd_unit_rejects_newline_in_env_value():
    # A newline in an env value could append extra directives to a unit that
    # runs as root at boot. Refuse to render rather than inject.
    from substratecloud.workloads.boot_script.steps import RunSystemdUnit

    unit = RunSystemdUnit(
        name="job",
        exec_start="/usr/bin/true",
        environment={"X": 'ok"\nExecStartPre=/bin/rm -rf /'},
    )
    with pytest.raises(ValueError):
        unit._body()


def test_systemd_unit_escapes_double_quote_in_env_value():
    # A bare " would close the Environment="..." quoting and let the rest of
    # the value be parsed as directives; it must be escaped.
    from substratecloud.workloads.boot_script.steps import RunSystemdUnit

    unit = RunSystemdUnit(name="job", exec_start="/usr/bin/true", environment={"X": 'a"b'})
    body = unit._body()
    assert 'Environment="X=a\\"b"' in body


def test_systemd_unit_rejects_newline_in_exec_start():
    # exec_start is interpolated raw; a newline would inject a new directive.
    from substratecloud.workloads.boot_script.steps import RunSystemdUnit

    unit = RunSystemdUnit(name="job", exec_start="/usr/bin/true\nUser=root")
    with pytest.raises(ValueError):
        unit._body()


def test_looks_high_entropy_detects_random_tokens():
    from substratecloud.workloads.secret import looks_high_entropy

    assert looks_high_entropy("k3J8xQ2pL9mNvB7wZ1cF5tR0yH4dG6sA8eW2uI3") is True
    assert looks_high_entropy("production") is False  # too short
    assert looks_high_entropy("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is False  # no entropy
    assert looks_high_entropy("a long passphrase with spaces in it") is False  # has spaces


def test_docker_warns_on_high_entropy_literal_env():
    # A generic secret (not one of the four hard-fail token shapes) would
    # otherwise persist silently server-side. Warn that it looks like a secret.
    wl = DockerWorkload(image="x", env={"DB_PASSWORD": "k3J8xQ2pL9mNvB7wZ1cF5tR0yH4dG6sA8eW2uI3"})
    with pytest.warns(UserWarning, match="(?i)secret"):
        wl.to_launch_configuration()


def test_docker_still_hard_fails_known_token_shape():
    # Existing behaviour preserved: the four known token shapes still hard-fail.
    wl = DockerWorkload(image="x", env={"HF_TOKEN": "hf_" + "a" * 30})
    with pytest.raises(ValueError):
        wl.to_launch_configuration()
