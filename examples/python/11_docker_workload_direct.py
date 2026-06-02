"""Imperative DockerWorkload + client.run (escape hatch)."""

from __future__ import annotations

from _common import is_live_run, require_live
from substrate import DockerWorkload, Secret, Substrate


def build_workload() -> DockerWorkload:
    return DockerWorkload(
        image="nginx:latest",
        ports={80: 80},
        env={"DEMO": Secret.from_env("DEMO_VAR")},
    )


def main() -> None:
    wl = build_workload()
    print(f"workload image={wl.image} ports={wl.ports}")
    if not is_live_run():
        return
    require_live()
    client = Substrate()
    inst = client.run(workload=wl, gpu="A4000", name="docker-workload-direct", tags=["example:docker"])
    print(f"launched {inst.id}; destroy via instance terminate or destroy if manifest-tagged")


if __name__ == "__main__":
    main()
