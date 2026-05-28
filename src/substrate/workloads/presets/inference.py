"""InferenceServer preset — runs vLLM/TGI/SGLang behind an OpenAI-compatible endpoint.

Built on DockerWorkload (the documented API path). For the script-config variant
(downloads model on the host, runs as systemd unit) use BootScript directly.
"""

from __future__ import annotations

from typing import Literal

from substrate.workloads.docker import DockerWorkload
from substrate.workloads.secret import Secret

Engine = Literal["vllm", "tgi", "sglang"]

_ENGINE_IMAGES: dict[Engine, str] = {
    "vllm": "vllm/vllm-openai:latest",
    "tgi": "ghcr.io/huggingface/text-generation-inference:latest",
    "sglang": "lmsysorg/sglang:latest",
}


def InferenceServer(
    *,
    engine: Engine = "vllm",
    model: str,
    port: int = 8000,
    hf_token: Secret | None = None,
    extra_args: list[str] | None = None,
) -> DockerWorkload:
    """Construct a DockerWorkload running the chosen inference engine.

    Example:
        wl = InferenceServer(
            engine="vllm",
            model="mistralai/Mistral-7B-v0.1",
            hf_token=Secret.from_env("HF_TOKEN"),
        )
        instance = client.run(workload=wl, gpu="A100", name="vllm-mistral")
    """
    if engine not in _ENGINE_IMAGES:
        raise ValueError(f"Unknown engine {engine!r}; choose from {list(_ENGINE_IMAGES)}")

    args: list[str]
    if engine == "vllm":
        args = ["--model", model, "--port", str(port)]
    elif engine == "tgi":
        args = ["--model-id", model, "--port", str(port)]
    else:  # sglang
        args = ["--model-path", model, "--port", str(port)]

    if extra_args:
        args.extend(extra_args)

    env: dict[str, str | Secret] = {}
    if hf_token is not None:
        env["HF_TOKEN"] = hf_token
        env["HUGGING_FACE_HUB_TOKEN"] = hf_token

    return DockerWorkload(
        image=_ENGINE_IMAGES[engine],
        args=args,
        env=env,
        ports={port: port},
        health_path="/health",
        estimated_boot_s=180,
    )
