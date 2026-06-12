"""Fluent builder: docker image, args, env, ports → Manifest."""

from __future__ import annotations

from substratecloud import Secret
from substratecloud.declarative.builder import Launch
from substratecloud.declarative.manifest import DockerWorkloadSpec, Manifest


def build_manifest() -> Manifest:
    return (
        Launch()
        .gpu("A100", count=1, max_price=3, regions=["north america"])
        .docker("vllm/vllm-openai:latest")
        .args("--model", "mistralai/Mistral-7B-v0.1")
        .env(HF_TOKEN=Secret.from_env("HF_TOKEN"), PLAIN="demo")
        .ports(8000)
        .budget(20)
        .tags("example:fluent-docker")
        .to_manifest(name="fluent-vllm")
    )


def main() -> None:
    m = build_manifest()
    assert isinstance(m.workload, DockerWorkloadSpec)
    print(m.to_yaml())


if __name__ == "__main__":
    main()
