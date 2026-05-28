"""End-to-end Docker live test with SSH verification.

Mirrors what a boot script would do, but inside a Docker container (since the
live API rejects launch_configuration.type='script' with HTTP 409/400 — see
plan doc §11.1).

Workflow:
1. Find cheapest GPU
2. Launch python:3.11-slim with bash args that:
     - apt-get install git
     - git clone the user-supplied repo
     - pip install numpy + requests
     - serve /opt/repo over HTTP on :8080
3. Wait for ACTIVE
4. SSH into the host, then `docker exec` into the container to verify:
     - repo cloned
     - numpy/requests importable
     - HTTP server responding
5. DELETE in finally
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from substrate import DockerWorkload, Substrate
from substrate._http.errors import SubstrateError

REPO = "https://github.com/pytorch/examples"
PRIVATE_KEY = Path(__file__).resolve().parent.parent / "sdktest_private.pem"

# Bash command run inside python:3.11-slim. Mirrors the boot-script intent.
WORKLOAD_BASH = (
    "set -e; "
    "apt-get update -qq && apt-get install -y --no-install-recommends git curl ca-certificates >/dev/null; "
    f"git clone --depth 1 {REPO} /opt/repo; "
    "pip install --quiet --no-cache-dir numpy requests; "
    "python3 -c 'import numpy, requests; print(\"sdktest-ready\", numpy.__version__, requests.__version__)' > /tmp/READY; "
    "cd /opt/repo && python3 -m http.server 8080"
)


def ssh(ip: str, port: int, user: str, command: str, *, timeout: int = 60) -> tuple[int, str]:
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


def ssh_with_retries(ip: str, port: int, user: str, *, attempts: int = 30, delay: int = 10) -> bool:
    print(f"    waiting for SSH at {user}@{ip}:{port}…")
    for i in range(1, attempts + 1):
        rc, _ = ssh(ip, port, user, "echo ready", timeout=15)
        if rc == 0:
            print(f"    SSH reachable after {i} attempt(s) ({i * delay}s)")
            return True
        time.sleep(delay)
    return False


def main() -> int:
    if not PRIVATE_KEY.exists():
        print(f"!! private key missing: {PRIVATE_KEY}")
        return 2

    c = Substrate()

    print(">>> 1. Find cheapest GPU (skip A6000/A4000 — fall back through types)…")
    # A6000 just failed provisioning; A4000 was excluded by the user.
    # Try a fallback chain of GPU families in price order.
    item = c.inventory.find_with_fallback([
        {"gpu_type": "A16"},
        {"gpu_type": "RTX4090"},
        {"gpu_type": "L4"},
        {"gpu_type": "L40S"},
        {"gpu_type": "L40"},
        {"gpu_type": "RTX6000Ada"},
    ])
    print(f"    {item}   id={item.id}")
    print(f"    default_os={item.default_os}")

    print(">>> 2. Resolve sdktest SSH key…")
    key = c.ssh_keys.find_by_name("sdktest")
    print(f"    {key.name}  id={key.id}")

    print(">>> 3. DockerWorkload (python:3.11-slim with install+clone+serve)…")
    wl = DockerWorkload(
        image="python:3.11-slim",
        args=["bash", "-c", WORKLOAD_BASH],
        ports={8080: 8080},
        estimated_boot_s=300,
        health_path=None,
    )
    launch_cfg = wl.to_launch_configuration()
    print(f"    launch_configuration.type={launch_cfg.type}  image={launch_cfg.docker_configuration.image}")

    print(">>> 4. POST /instances (BILLING STARTS)…")
    try:
        instance = c.instances.create(
            inventory_gpu_id=item.id,
            name="sdk-docker-test",
            ssh_key_id=key.id,
            os=item.default_os,
            tags=["sdk-smoke", "docker", "deploy-repo", f"trace:{int(time.time())}"],
            launch_configuration=launch_cfg,
        )
    except SubstrateError as exc:
        print(f"!! POST failed: HTTP {exc.status_code}: {exc.message}")
        return 1

    instance_id = instance.id
    print(f"    id={instance_id}  cost=€{instance.cost_per_hour}/hr")

    results: dict[str, tuple[bool, str]] = {}
    try:
        print(">>> 5. Wait up to 20 min for ACTIVE…")
        t0 = time.monotonic()
        active = c.instances.wait_until_active(instance_id, timeout=1200, poll_interval=10)
        elapsed = int(time.monotonic() - t0)
        print(f"    ACTIVE in {elapsed}s  ip={active.ip_address}")

        ip = str(active.ip_address)
        port = active.ssh_port or 22
        user = active.ssh_user or "substrate"

        print(">>> 6. Wait for SSH…")
        if not ssh_with_retries(ip, port, user, attempts=30, delay=10):
            results["ssh_reachable"] = (False, "SSH never reachable")
            return 1
        results["ssh_reachable"] = (True, "OK")

        print(">>> 7. Wait for docker container to be up…")
        for attempt in range(30):
            rc, _ = ssh(
                ip, port, user,
                "sudo docker ps --format '{{.Image}}' | grep -q python",
                timeout=15,
            )
            if rc == 0:
                print(f"    python container present after {(attempt + 1) * 10}s")
                break
            time.sleep(10)
        else:
            print("    container never appeared in 300s")

        print(">>> 8. Wait for /tmp/READY inside container…")
        for attempt in range(30):
            rc, _ = ssh(
                ip, port, user,
                "sudo docker exec $(sudo docker ps -q | head -1) test -f /tmp/READY",
                timeout=15,
            )
            if rc == 0:
                print(f"    workload finished setup after {(attempt + 1) * 10}s")
                break
            time.sleep(10)
        else:
            print("    /tmp/READY never appeared inside container")

        print(">>> 9. Verification battery…")
        checks: list[tuple[str, str, str | None]] = [
            ("os_release",
             "cat /etc/os-release | head -2", "Ubuntu"),
            ("nvidia_smi",
             "nvidia-smi --query-gpu=name --format=csv,noheader || echo no_gpu", None),
            ("docker_present",
             "command -v docker && docker --version", "Docker"),
            ("docker_ps",
             "sudo docker ps --format '{{.Image}} {{.Status}}'", "python"),
            ("docker_inspect_running",
             "sudo docker inspect --format='{{.State.Status}}' $(sudo docker ps -q | head -1)", "running"),
            ("docker_image_correct",
             "sudo docker inspect --format='{{.Config.Image}}' $(sudo docker ps -q | head -1)", "python:3.11-slim"),
            ("port_8080_listening",
             "sudo ss -ltnp 2>/dev/null | grep :8080 || sudo netstat -ltnp 2>/dev/null | grep :8080", "LISTEN"),
            ("curl_repo_index",
             "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/", "200"),
            ("curl_repo_listing",
             "curl -s http://127.0.0.1:8080/ | head -20", "README"),
            ("ready_marker",
             "sudo docker exec $(sudo docker ps -q | head -1) cat /tmp/READY", "sdktest-ready"),
            ("repo_cloned",
             "sudo docker exec $(sudo docker ps -q | head -1) ls /opt/repo | head -5", "README"),
            ("numpy_importable",
             "sudo docker exec $(sudo docker ps -q | head -1) python3 -c 'import numpy; print(numpy.__version__)'", "."),
            ("requests_importable",
             "sudo docker exec $(sudo docker ps -q | head -1) python3 -c 'import requests; print(requests.__version__)'", "."),
            ("repo_has_git",
             "sudo docker exec $(sudo docker ps -q | head -1) ls /opt/repo/.git/HEAD", "HEAD"),
        ]
        for name, cmd, must_contain in checks:
            rc, out = ssh(ip, port, user, cmd, timeout=30)
            ok = (rc == 0) and (must_contain is None or must_contain in out)
            results[name] = (ok, out[:200])
            mark = "✓" if ok else "✗"
            first = (out.splitlines() or [""])[0][:80]
            print(f"    {mark} {name:25s}  {first}")

    finally:
        print(">>> 10. DELETE…")
        try:
            deleted = c.instances.delete(instance_id)
            print(f"    deleted  status={deleted.status.value}")
        except SubstrateError as e:
            print(f"!! DELETE FAILED: {e}")
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
