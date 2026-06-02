"""Fluent Launch builder: immutability, chain order, manifest emission."""

from __future__ import annotations

import pytest

from substratecloud.declarative.builder import Launch
from substratecloud.declarative.manifest import (
    BootScriptWorkloadSpec,
    DockerWorkloadSpec,
    Manifest,
    _FromEnv,
)
from substratecloud.workloads.secret import Secret


# ─── immutability ─────────────────────────────────────────────────────────


def test_builder_is_immutable():
    b1 = Launch()
    b2 = b1.gpu("A100")
    assert b1 is not b2
    assert b1._partial == {}  # untouched
    assert b2._partial["gpu"]["type"] == "A100"


def test_chain_does_not_mutate_branches():
    base = Launch().gpu("A100")
    a = base.tags("a")
    b = base.tags("b")
    assert a._partial["tags"] == ["a"]
    assert b._partial["tags"] == ["b"]


# ─── docker workload ──────────────────────────────────────────────────────


def test_docker_full_chain_emits_manifest():
    m = (
        Launch()
        .gpu("A100", count=1, max_price=3, regions=["us-east-1"])
        .docker("vllm/vllm-openai:latest")
        .args("--model", "mistralai/Mistral-7B-v0.1")
        .env(HF_TOKEN="$HF_TOKEN", PLAIN="value")
        .ports(8000)
        .budget(10)
        .tags("team:platform", "env:demo")
        .to_manifest(name="vllm-mistral")
    )
    assert m.name == "vllm-mistral"
    assert m.gpu.type == "A100"
    assert m.gpu.regions == ["us-east-1"]
    assert isinstance(m.workload, DockerWorkloadSpec)
    assert m.workload.image == "vllm/vllm-openai:latest"
    assert m.workload.args == ["--model", "mistralai/Mistral-7B-v0.1"]
    assert m.workload.env["HF_TOKEN"] == "$HF_TOKEN"
    assert m.workload.env["PLAIN"] == "value"
    assert m.workload.ports == {8000: 8000}
    assert str(m.lifecycle.budget_limit_usd) == "10"
    assert "team:platform" in m.tags
    assert "env:demo" in m.tags


def test_secret_from_env_lowers_to_manifest_dict():
    s = Secret.from_env("HF_TOKEN")
    m = (
        Launch()
        .docker("x:1")
        .env(HF_TOKEN=s)
        .to_manifest(name="x")
    )
    assert isinstance(m.workload, DockerWorkloadSpec)
    assert m.workload.env["HF_TOKEN"] == _FromEnv(from_env="HF_TOKEN")


def test_ports_dict_form():
    m = (
        Launch()
        .docker("x:1")
        .ports({8000: 8080}, 9000)
        .to_manifest(name="x")
    )
    assert isinstance(m.workload, DockerWorkloadSpec)
    assert m.workload.ports == {8000: 8080, 9000: 9000}


# ─── boot script ──────────────────────────────────────────────────────────


def test_boot_script_steps():
    m = (
        Launch()
        .gpu("A4000")
        .boot_script(steps=["apt-get update", "echo ready"])
        .to_manifest(name="bs")
    )
    assert isinstance(m.workload, BootScriptWorkloadSpec)
    assert m.workload.steps == ["apt-get update", "echo ready"]


def test_boot_script_body_xor_steps():
    with pytest.raises(ValueError, match="exactly one"):
        Launch().boot_script(steps=["a"], body="b")
    with pytest.raises(ValueError, match="exactly one"):
        Launch().boot_script()


# ─── manifest round-trip ──────────────────────────────────────────────────


def test_from_manifest_round_trip():
    m = Manifest.model_validate(
        {
            "name": "x",
            "gpu": {"type": "A100", "count": 2},
            "workload": {"type": "docker", "image": "nginx:latest"},
        }
    )
    b = Launch.from_manifest(m)
    m2 = b.to_manifest()
    assert m == m2


# ─── name requirement ─────────────────────────────────────────────────────


def test_to_manifest_requires_name():
    with pytest.raises(ValueError, match="requires a `name`"):
        Launch().gpu("A100").to_manifest()


def test_to_manifest_accepts_name_arg():
    m = Launch().gpu("A100").to_manifest(name="x")
    assert m.name == "x"


# ─── detached builder cannot launch ───────────────────────────────────────


def test_detached_launch_raises():
    b = Launch().gpu("A100").docker("x:1")
    with pytest.raises(RuntimeError, match="detached"):
        b.launch(name="x")
