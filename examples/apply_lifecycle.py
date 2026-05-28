"""End-to-end manifest lifecycle: plan → apply → reuse → destroy.

Demonstrates idempotency: the second `apply` does NOT call `POST /instances`.
That's the central cost-safety property of the declarative layer.

Run:
    export SUBSTRATE_MCP_TOKEN=mcp_...
    python examples/apply_lifecycle.py
"""

from __future__ import annotations

from pathlib import Path

from substrate import Substrate

MANIFEST = Path(__file__).parent / "manifests" / "minimal.yaml"


def main() -> None:
    client = Substrate()

    # 1. Plan — never calls POST /instances. Prints what apply would do
    #    and an estimated cost.
    print("─── plan ──────────────────────────────────────")
    plan = client.plan(MANIFEST)
    print(plan.summary())
    print()

    # 2. Apply — launches if nothing's there, or reuses if a matching instance
    #    already carries the `manifest:<name>` tag.
    print("─── apply (first run: should create) ──────────")
    inst = client.apply(MANIFEST)
    print(f"  {inst.name} ({inst.id}) status={inst.status.value}")
    print()

    # 3. Apply again — idempotent. No new instance.
    print("─── apply (second run: should reuse) ──────────")
    inst2 = client.apply(MANIFEST)
    assert inst2.id == inst.id, "apply should have reused the existing instance"
    print(f"  Reused: {inst2.name} ({inst2.id})")
    print()

    # 4. Tear down. Resolves by `manifest:minimal` tag.
    print("─── destroy ───────────────────────────────────")
    deleted = client.destroy("minimal")
    for d in deleted:
        print(f"  Deleted: {d.name} ({d.id})")


if __name__ == "__main__":
    main()
