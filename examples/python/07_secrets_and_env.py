"""Secret types and env resolution for manifests."""

from __future__ import annotations

from substratecloud import Secret
from substratecloud.declarative.lower import resolve_env_value
from substratecloud.declarative.manifest import Manifest, _FromEnv


def build_manifest() -> Manifest:
    return Manifest.model_validate(
        {
            "name": "secrets-demo",
            "gpu": {"type": "A4000"},
            "workload": {
                "type": "docker",
                "image": "alpine:latest",
                "env": {
                    "FROM_ENV": {"from_env": "HF_TOKEN"},
                    "DOLLAR": "$HF_TOKEN",
                    "PLAIN": "hello",
                },
            },
            "lifecycle": {"budget_limit_usd": "3"},
        }
    )


def main() -> None:
    m = build_manifest()
    wl = m.workload
    assert wl is not None
    assert isinstance(wl.env["FROM_ENV"], _FromEnv)
    resolved = resolve_env_value(wl.env["FROM_ENV"])
    assert isinstance(resolved, Secret)
    print("manifest env keys:", list(wl.env.keys()))
    print("Secret.from_env origin:", Secret.from_env("HF_TOKEN").origin)


if __name__ == "__main__":
    main()
