"""Compose a boot script that pulls a model and runs a custom systemd service.

# API-OPEN-QUESTION: this example depends on the script-based launch_configuration
# shape, which is not yet documented by the Substrate API (see plan doc §11.1).
# When the API confirms its shape, only `substrate.models.launch_config` needs
# to change — this script keeps working as written.
"""

from __future__ import annotations

import sys

from substrate import BootScript, BootScriptWorkload, Secret, Substrate


def main() -> int:
    client = Substrate()

    script = (
        BootScript()
        .with_base_image_setup()
        .install_uv()
        .install_cuda_drivers()
        .pip_install(["torch", "transformers", "accelerate"])
        .pull_hf_model(
            "meta-llama/Llama-3-8B",
            hf_token=Secret.from_env("HF_TOKEN"),
        )
        .write_file(
            path="/opt/app/run.sh",
            content="#!/usr/bin/env bash\nexec python -m my_app.serve --port 8000\n",
            mode="0755",
        )
        .run_systemd_unit(
            name="my-app",
            exec_start="/opt/app/run.sh",
            description="Llama-3 serving app",
            restart="on-failure",
        )
        .with_status_beacon("https://my-platform.example/hooks/boot")
        .with_idle_shutdown(minutes=30)
    )

    print("Rendered bash (first 600 chars):\n")
    print(script.render()[:600])
    print("\n…")

    workload = BootScriptWorkload(script, ports=[8000], estimated_boot_s=600)

    inst = client.run(
        workload=workload,
        gpu="H100",
        name="llama-boot-script-demo",
        tags=["team:platform"],
        wait=True,
        wait_timeout=900,
    )
    print(f"\nActive: {inst.name} ({inst.id})  ip={inst.ip_address}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
