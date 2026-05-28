"""Prototype a deploy in Python, then commit the YAML.

Pattern: experiment in a notebook using the fluent builder; once happy,
call `.to_yaml(path)` to dump it. Commit the YAML; CI deploys it with
`substrate apply`.

Run:
    python examples/prototype_to_yaml.py            # writes substrate.yaml
    substrate plan substrate.yaml                   # validate
"""

from __future__ import annotations

from substrate import Substrate


def main() -> None:
    # Build the manifest fluently. `Substrate()` here is just a builder
    # entry point — no API calls are made.
    client = Substrate()
    launch = (
        client
        .gpu("A100", count=1, max_price=3, regions=["us-east-1"])
        .docker("vllm/vllm-openai:latest")
        .args("--model", "mistralai/Mistral-7B-v0.1")
        .env(HF_TOKEN="$HF_TOKEN")          # `$VAR` is shorthand for Secret.from_env(VAR)
        .ports(8000)
        .budget(25)
        .max_runtime("8h")
        .tags("team:platform", "env:demo")
    )

    # Print the YAML (also writes to ./substrate.yaml).
    yaml = launch.to_yaml("substrate.yaml", name="vllm-mistral")
    print(yaml)
    print("Wrote substrate.yaml — review and commit, then:")
    print("  substrate plan substrate.yaml")
    print("  substrate apply substrate.yaml")


if __name__ == "__main__":
    main()
