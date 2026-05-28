"""Launch a vLLM inference server on the cheapest A100, wait for active, print SSH."""

from __future__ import annotations

import sys

from substrate import InferenceServer, Secret, Substrate


def main() -> int:
    client = Substrate()  # token + base_url from env or `substrate config init`

    workload = InferenceServer(
        engine="vllm",
        model="mistralai/Mistral-7B-v0.1",
        hf_token=Secret.from_env("HF_TOKEN"),
    )

    print("Launching…")
    inst = client.run(
        workload=workload,
        gpu="A100",
        name="vllm-mistral",
        tags=["team:platform", "env:demo"],
        wait=True,
        wait_timeout=600,
    )

    print(f"\nActive: {inst.name} ({inst.id})")
    print(f"  ssh: ssh {inst.ssh_user}@{inst.ip_address} -p {inst.ssh_port}")
    print(f"  endpoint (once ready): http://{inst.ip_address}:8000/v1")
    print("\nRemember to terminate when done:")
    print(f"  substrate instance terminate {inst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
