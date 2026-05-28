"""End-to-end live smoke: launch cheapest A4000 with nginx, wait, DELETE.

Cost: one partial billing hour on the chosen inventory. The DELETE call lives
in a `finally` block so the instance is always cleaned up — even on Ctrl-C or
unexpected errors.

Run with:
    set -a && source .env && set +a && .venv/bin/python scripts/live_test_cycle.py
"""

from __future__ import annotations

import sys
import time

from substrate import DockerWorkload, Substrate


def main() -> int:
    c = Substrate()

    print(">>> 1. Find cheapest A4000…")
    item = c.inventory.find_cheapest(gpu_type="A4000")
    print(f"    {item}   id={item.id}")
    print(f"    default_os={item.default_os}")

    print(">>> 2. Pick an SSH key (gpu-test-key)…")
    try:
        key = c.ssh_keys.find_by_name("gpu-test-key")
    except Exception:
        keys = c.ssh_keys.list()
        if not keys:
            print("    no SSH keys registered — aborting (no auditable SSH access)")
            return 2
        key = keys[0]
    print(f"    {key.name}  id={key.id}")

    print(">>> 3. Compose DockerWorkload (nginx:alpine on port 80)…")
    wl = DockerWorkload(
        image="nginx:alpine",
        ports={80: 80},
        estimated_boot_s=60,
        health_path=None,
    )
    launch_cfg = wl.to_launch_configuration()
    print(f"    launch_configuration.type={launch_cfg.type}  "
          f"image={launch_cfg.docker_configuration.image}")

    print(">>> 4. POST /instances (BILLING STARTS HERE)…")
    instance = c.instances.create(
        inventory_gpu_id=item.id,
        name="sdk-live-test",
        ssh_key_id=key.id,
        os=item.default_os,
        tags=["sdk-smoke-test", "delete-immediately", f"trace:{int(time.time())}"],
        launch_configuration=launch_cfg,
    )
    instance_id = instance.id
    print(f"    created id={instance_id}  status={instance.status.value}  "
          f"cost={instance.cost_per_hour}/hr")

    try:
        print(">>> 5. Wait up to 10 min for status=active…")
        t0 = time.monotonic()
        active = c.instances.wait_until_active(instance_id, timeout=600, poll_interval=5)
        elapsed = int(time.monotonic() - t0)
        print(f"    ACTIVE in {elapsed}s  ip={active.ip_address}  "
              f"ssh={active.ssh_user}@{active.ip_address}:{active.ssh_port}")

        print(">>> 6. GET /instance/:id sanity check…")
        fetched = c.instances.get(instance_id)
        print(f"    name={fetched.name}  tags={fetched.tags}")
        print(f"    uptime={fetched.uptime}  est_spend={fetched.estimated_spend}")

        print(">>> 7. PATCH /instance/:id (add tag)…")
        patched = c.instances.update(instance_id, tags=[*fetched.tags, "patched:true"])
        print(f"    new tags={patched.tags}")

    finally:
        print(">>> 8. DELETE /instance/:id (stops billing)…")
        try:
            deleted = c.instances.delete(instance_id)
            print(f"    deleted  status={deleted.status.value}")
        except Exception as e:
            print(f"    DELETE FAILED — investigate manually: {e}")
            print(f"    MANUAL CLEANUP NEEDED for instance {instance_id}")
            return 1

    print()
    print(">>> Done. Estimated total spend: ~€" + str(item.final_price_per_hour) +
          " (Substrate bills a final partial hour on delete).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
