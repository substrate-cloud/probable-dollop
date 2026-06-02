"""client.run() composite: pick inventory + launch + wait."""

from __future__ import annotations

from _common import is_live_run, require_live
from substrate import Substrate


def main() -> None:
    if not is_live_run():
        print("offline: client.run(gpu=..., name=..., wait=True)")
        return
    require_live()
    inst = Substrate().run(
        gpu="A4000",
        name="run-composite-demo",
        image="nginx:latest",
        ports={80: 80},
        tags=["example:run"],
        wait=True,
        wait_timeout=600,
    )
    print(f"{inst.name} active at {inst.ip_address}")


if __name__ == "__main__":
    main()
