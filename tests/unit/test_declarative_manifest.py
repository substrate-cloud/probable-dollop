"""Manifest schema: parsing, validation, YAML round-trip, env shorthand lowering."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from substratecloud.declarative import Manifest, parse_duration
from substratecloud.declarative.lower import (
    docker_workload_from_spec,
    resolve_env_value,
    workload_from_manifest,
)
from substratecloud.declarative.manifest import (
    BootScriptWorkloadSpec,
    DockerWorkloadSpec,
    _FromEnv,
    _FromVault,
    _Literal,
)
from substratecloud.workloads.secret import Secret


# ─── basic parsing ─────────────────────────────────────────────────────────


def test_minimal_manifest_parses():
    m = Manifest.model_validate({"name": "demo"})
    assert m.name == "demo"
    assert m.tags == []
    assert m.gpu is None
    assert m.workload is None
    assert m.lifecycle.wait_until_active is True


def test_manifest_name_rejects_invalid_chars():
    with pytest.raises(Exception):
        Manifest.model_validate({"name": "has spaces"})
    with pytest.raises(Exception):
        Manifest.model_validate({"name": ""})
    with pytest.raises(Exception):
        Manifest.model_validate({"name": "-leading-dash"})


def test_manifest_tag_helper():
    m = Manifest(name="vllm-mistral")
    assert m.manifest_tag() == "manifest:vllm-mistral"


# ─── Docker workload ───────────────────────────────────────────────────────


def test_docker_workload_full_parses():
    data = {
        "name": "vllm",
        "gpu": {"type": "A100", "max_price_per_hour": "3.00"},
        "workload": {
            "type": "docker",
            "image": "vllm/vllm-openai:latest",
            "args": ["--model", "mistralai/Mistral-7B-v0.1"],
            "env": {
                "HF_TOKEN": {"from_env": "HF_TOKEN"},
                "PLAIN": "value",
                "SHORT": "$ANOTHER",
            },
            "ports": {8000: 8000},
        },
    }
    m = Manifest.model_validate(data)
    assert isinstance(m.workload, DockerWorkloadSpec)
    assert m.workload.image == "vllm/vllm-openai:latest"
    assert m.workload.env["HF_TOKEN"] == _FromEnv(from_env="HF_TOKEN")
    assert m.workload.env["PLAIN"] == "value"
    assert m.workload.env["SHORT"] == "$ANOTHER"


# ─── Boot-script workload ──────────────────────────────────────────────────


def test_boot_script_requires_one_source():
    with pytest.raises(Exception):
        BootScriptWorkloadSpec(type="boot_script")  # neither
    with pytest.raises(Exception):
        BootScriptWorkloadSpec(
            type="boot_script", steps=["echo hi"], body="echo there"
        )


def test_boot_script_with_steps_parses():
    spec = BootScriptWorkloadSpec(
        type="boot_script", steps=["apt-get update", "echo ready"]
    )
    assert spec.steps == ["apt-get update", "echo ready"]


# ─── Lifecycle validation ──────────────────────────────────────────────────


def test_lifecycle_rejects_removed_timer_fields():
    with pytest.raises(Exception):
        Manifest.model_validate({"name": "x", "lifecycle": {"max_runtime": "4h"}})
    with pytest.raises(Exception):
        Manifest.model_validate({"name": "x", "lifecycle": {"idle_timeout": "30m"}})


def test_safety_net_helper():
    m = Manifest(name="x")
    assert m.has_safety_net() is False
    m2 = Manifest.model_validate({"name": "x", "lifecycle": {"budget_limit_usd": "10"}})
    assert m2.has_safety_net() is True


# ─── YAML round-trip ───────────────────────────────────────────────────────


def test_yaml_roundtrip(tmp_path: Path):
    src = tmp_path / "substratecloud.yaml"
    src.write_text(
        textwrap.dedent(
            """\
            name: demo
            tags:
              - team:platform
            gpu:
              type: A100
              count: 1
              regions:
                - us-east-1
            workload:
              type: docker
              image: nginx:latest
              ports:
                80: 80
            lifecycle:
              budget_limit_usd: '5.00'
              wait_until_active: true
              wait_timeout: 600.0
            """
        )
    )
    m = Manifest.from_yaml(src)
    out = tmp_path / "out.yaml"
    m.to_yaml(out)
    m2 = Manifest.from_yaml(out)
    assert m == m2


def test_from_yaml_rejects_non_mapping(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a list\n")
    with pytest.raises(ValueError, match="mapping"):
        Manifest.from_yaml(p)


# ─── Env-value lowering ────────────────────────────────────────────────────


def test_resolve_env_value_plain_string():
    assert resolve_env_value("hello") == "hello"


def test_resolve_env_value_dollar_shorthand():
    out = resolve_env_value("$HF_TOKEN")
    assert isinstance(out, Secret)
    assert out.origin == "env:HF_TOKEN"


def test_resolve_env_value_escaped_dollar():
    assert resolve_env_value(r"\$literal") == "$literal"


def test_resolve_env_value_from_env_typed():
    out = resolve_env_value(_FromEnv(from_env="HF_TOKEN"))
    assert isinstance(out, Secret)
    assert out.origin == "env:HF_TOKEN"


def test_resolve_env_value_literal_warned(caplog):
    out = resolve_env_value(_Literal(literal="hi"))
    assert isinstance(out, Secret)
    assert out.resolve() == "hi"


def test_resolve_env_value_vault_lazy():
    out = resolve_env_value(_FromVault(from_vault="kv/data/x#tok"))
    assert isinstance(out, Secret)
    with pytest.raises(RuntimeError, match="Vault provider not configured"):
        out.resolve()


# ─── Workload lowering ────────────────────────────────────────────────────


def test_docker_lower_keeps_env_keys(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "hf_test_test_test_test_test_test")
    spec = DockerWorkloadSpec(
        type="docker",
        image="x:latest",
        env={"HF_TOKEN": _FromEnv(from_env="HF_TOKEN"), "PLAIN": "v"},
    )
    wl = docker_workload_from_spec(spec)
    assert "HF_TOKEN" in wl.env
    assert "PLAIN" in wl.env
    assert isinstance(wl.env["HF_TOKEN"], Secret)


def test_workload_from_manifest_none():
    m = Manifest(name="x")
    assert workload_from_manifest(m) is None


# ─── Duration parsing ─────────────────────────────────────────────────────


def test_parse_duration_units():
    assert parse_duration("60s").total_seconds() == 60
    assert parse_duration("5m").total_seconds() == 300
    assert parse_duration("2h").total_seconds() == 7200
    assert parse_duration("1d").total_seconds() == 86400


def test_parse_duration_rejects_bad():
    with pytest.raises(ValueError):
        parse_duration("4 hours")
    with pytest.raises(ValueError):
        parse_duration("h4")
    with pytest.raises(ValueError):
        parse_duration("")
