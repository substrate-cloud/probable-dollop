"""End-to-end boot-script live test.

1. Find cheapest GPU (excluding CPU nodes)
2. Compose BootScript: install uv, pip-install packages, git clone, write marker
3. Launch via launch_configuration.type="script"  (# API-OPEN-QUESTION speculative)
4. Wait for ACTIVE (long timeout — boot scripts add minutes on top of provision)
5. SSH in with sdktest key, run a battery of assertions
6. DELETE in finally
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from substratecloud import BootScript, BootScriptWorkload, SubstrateCloud
from substratecloud._http.errors import SubstrateCloudError

REPO = "https://github.com/pytorch/examples"
REPO_DEST = "/opt/repos/examples"
MARKER_FILE = "/var/log/substratecloud-boot/HELLO_FROM_SDK_TEST"
MARKER_TEXT = "boot-script-marker-ok"

PRIVATE_KEY = Path(__file__).resolve().parent.parent / "sdktest_private.pem"


def ssh(ip: str, port: int, user: str, command: str, *, timeout: int = 30) -> tuple[int, str]:
    """Run a single command on the remote host via SSH. Returns (rc, output)."""
    cmd = [
        "ssh",
        "-i", str(PRIVATE_KEY),
        "-p", str(port),
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=/tmp/substrate_sdktest_known_hosts",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        f"{user}@{ip}",
        command,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return 124, "SSH command timed out"
    return result.returncode, (result.stdout + result.stderr).strip()


def ssh_with_retries(ip: str, port: int, user: str, *, attempts: int = 12, delay: int = 10) -> bool:
    """Wait until SSH becomes reachable. Returns True if successful."""
    print(f"    waiting for SSH to come up at {user}@{ip}:{port}…")
    for i in range(1, attempts + 1):
        rc, _out = ssh(ip, port, user, "echo ready", timeout=15)
        if rc == 0:
            print(f"    SSH reachable after {i} attempt(s)")
            return True
        time.sleep(delay)
    return False


def main() -> int:
    if not PRIVATE_KEY.exists():
        print(f"!! private key not found at {PRIVATE_KEY}")
        return 2
    if oct(PRIVATE_KEY.stat().st_mode & 0o777) != "0o600":
        print(f"!! private key perms must be 0600: {PRIVATE_KEY}")
        return 2

    c = SubstrateCloud()

    print(">>> 1. Find a cheap GPU (skip A6000/A4000 — user constraint)…")
    item = c.inventory.find_with_fallback([
        {"gpu_type": "A16"},
        {"gpu_type": "RTX4090"},
        {"gpu_type": "L4"},
        {"gpu_type": "L40"},
        {"gpu_type": "L40S"},
    ])
    print(f"    {item}   id={item.id}")
    print(f"    default_os={item.default_os}")

    print(">>> 2. Resolve sdktest SSH key…")
    key = c.ssh_keys.find_by_name("sdktest")
    print(f"    {key.name}  id={key.id}")

    print(">>> 3. Compose BootScript…")
    script = (
        BootScript()
        .with_base_image_setup()
        .install_uv()
        .pip_install(["numpy", "requests"])
        .git_clone(REPO, REPO_DEST, depth=1)
        .write_file(MARKER_FILE, MARKER_TEXT, mode="0644")
        .with_status_beacon("")  # local-only beacon file
    )
    rendered = script.render()
    print(f"    rendered {len(rendered)} bytes  steps={[s.step_id for s in script.steps]}")

    workload = BootScriptWorkload(script, estimated_boot_s=900)
    launch_cfg = workload.to_launch_configuration()
    print(f"    launch_configuration.type={launch_cfg.type}")

    print(">>> 4. POST /instances (BILLING STARTS)…")
    try:
        instance = c.instances.create(
            inventory_gpu_id=item.id,
            name="sdk-bootscript-test",
            ssh_key_id=key.id,
            os=item.default_os,
            tags=["sdk-smoke", "boot-script", f"trace:{int(time.time())}"],
            launch_configuration=launch_cfg,
        )
    except SubstrateCloudError as exc:
        print(f"!! POST failed (HTTP {exc.status_code}): {exc.message}")
        print("   (no billing started — if 400/422, the API likely doesn't accept "
              "type='script' or the field shape is different)")
        return 1

    instance_id = instance.id
    print(f"    id={instance_id}  status={instance.status.value}  cost=€{instance.cost_per_hour}/hr")

    results: dict[str, tuple[bool, str]] = {}
    try:
        print(">>> 5. Wait up to 25 min for ACTIVE…")
        t0 = time.monotonic()
        active = c.instances.wait_until_active(instance_id, timeout=1500, poll_interval=10)
        elapsed = int(time.monotonic() - t0)
        print(f"    ACTIVE in {elapsed}s  ip={active.ip_address}")

        ip = str(active.ip_address)
        port = active.ssh_port or 22
        user = active.ssh_user or "substratecloud"

        print(">>> 6. Wait for SSH to come up…")
        if not ssh_with_retries(ip, port, user, attempts=24, delay=10):
            results["ssh_reachable"] = (False, "SSH never came up")
            return 1
        results["ssh_reachable"] = (True, "OK")

        print(">>> 7. Wait for boot script completion (manifest.json)…")
        # The boot script runs after the OS is up; the marker file appears
        # only after all steps finish. Give it generous time.
        for attempt in range(30):
            rc, _ = ssh(ip, port, user, f"sudo test -f {MARKER_FILE}", timeout=15)
            if rc == 0:
                print(f"    marker present after {attempt + 1} polls "
                      f"({(attempt + 1) * 15}s)")
                break
            time.sleep(15)
        else:
            results["boot_marker"] = (False, f"{MARKER_FILE} never appeared")
            # carry on with other checks — they'll mostly fail but give us info

        print(">>> 8. Verification battery…")
        checks: list[tuple[str, str, str | None]] = [
            ("os_release", "cat /etc/os-release | head -2", "Ubuntu"),
            ("uname", "uname -a", "Linux"),
            ("nvidia_smi", "nvidia-smi --query-gpu=name --format=csv,noheader", None),
            ("uv_installed", "command -v uv && uv --version", "uv"),
            ("python_present", "python3 --version", "Python"),
            ("numpy_installed", "python3 -c 'import numpy; print(numpy.__version__)'", "."),
            ("requests_installed", "python3 -c 'import requests; print(requests.__version__)'", "."),
            ("repo_cloned", f"ls {REPO_DEST}/README.md && cat {REPO_DEST}/README.md | head -3", "examples"),
            ("marker_file", f"sudo cat {MARKER_FILE}", MARKER_TEXT),
            ("boot_log", "sudo tail -5 /var/log/substratecloud-boot/boot.log", "completed"),
            ("manifest_json", "sudo cat /var/log/substratecloud-boot/manifest.json | head -50", '"step"'),
            ("beacon_local", "sudo cat /var/log/substratecloud-boot/beacon.json", '"stage"'),
            ("per_step_logs", "sudo ls /var/log/substratecloud-boot/", "boot.log"),
        ]
        for name, cmd, must_contain in checks:
            rc, out = ssh(ip, port, user, cmd, timeout=30)
            ok = (rc == 0) and (must_contain is None or must_contain in out)
            results[name] = (ok, out[:200])
            mark = "✓" if ok else "✗"
            preview = out.splitlines()[0][:80] if out else "(empty)"
            print(f"    {mark} {name:20s}  {preview}")

    finally:
        print(">>> 9. DELETE /instance/:id (stops billing)…")
        try:
            deleted = c.instances.delete(instance_id)
            print(f"    deleted  status={deleted.status.value}")
        except SubstrateCloudError as e:
            print(f"!! DELETE FAILED — clean up manually: {e}")
            return 1

    print()
    print("=== SUMMARY ===")
    passed = sum(1 for v, _ in results.values() if v)
    total = len(results)
    for name, (ok, out) in results.items():
        mark = "PASS" if ok else "FAIL"
        first = (out.splitlines() or [""])[0][:90]
        print(f"  [{mark}] {name:25s} | {first}")
    print(f"  ---")
    print(f"  {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
