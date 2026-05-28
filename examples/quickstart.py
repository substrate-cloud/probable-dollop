"""The shortest possible Substrate program.

One line of business logic. The fluent `Substrate().launch(...)` form picks
the cheapest matching GPU, launches it with the given container, attaches
a budget cap, and waits for `active`.

Run:
    pip install "substrate[cli]"
    export SUBSTRATE_MCP_TOKEN=mcp_...
    python examples/quickstart.py
"""

from __future__ import annotations

from substrate import Substrate


def main() -> None:
    inst = Substrate().launch(
        name="quickstart-demo",
        gpu="A4000",
        image="nginx:latest",
        ports={80: 80},
        budget=2,            # required: at least one safety net (budget/max_runtime/idle_timeout)
        tags=["env:demo"],
    )

    print(f"Active: {inst.name} ({inst.id})")
    print(f"  IP:  {inst.ip_address}")
    print(f"  SSH: ssh {inst.ssh_user}@{inst.ip_address} -p {inst.ssh_port}")
    print(f"  $/h: {inst.cost_per_hour}")
    print()
    print("When done, tear down with:")
    print("  substrate destroy quickstart-demo")


if __name__ == "__main__":
    main()
