"""Prototype in Python, export YAML for git + CI."""

from __future__ import annotations

from pathlib import Path

from substrate import Substrate


def build_and_write(path: Path) -> str:
    yaml_text = (
        Substrate()
        .gpu("A4000", max_price=1)
        .docker("nginx:latest", ports={80: 80})
        .budget(5)
        .tags("example:prototype")
        .to_yaml(path, name="prototype-nginx")
    )
    return yaml_text


def main() -> None:
    out = Path("substrate.generated.yaml")
    print(build_and_write(out))
    print(f"wrote {out.resolve()}")


if __name__ == "__main__":
    main()
