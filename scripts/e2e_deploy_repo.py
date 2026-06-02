#!/usr/bin/env python3
"""Live E2E: apply git-repo manifest, verify clone via SSH, destroy.

Requires:
  - SUBSTRATECLOUD_MCP_TOKEN (or substratecloud config)
  - sdktest_private.pem in repo root (registered as org key "sdktest")
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from substratecloud import SubstrateCloud
from substratecloud.declarative.manifest import Manifest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "manifests" / "deploy-git-repo.yaml"
PRIVATE_KEY = ROOT / "sdktest_private.pem"
REPO_DEST = "/opt/app/repo"
MARKER = "/var/log/substratecloud-boot/repo-deploy.marker"
MANIFEST_NAME = "deploy-git-repo"


def ssh(ip: str, port: int, user: str, command: str, *, timeout: int = 30) -> tuple[int, str]:
    cmd = [
        "ssh",
        "-i",
        str(PRIVATE_KEY),
        "-p",
        str(port),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=/tmp/substrate_e2e_known_hosts",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "BatchMode=yes",
        f"{user}@{ip}",
        command,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> int:
    if not PRIVATE_KEY.exists():
        print(f"missing SSH key: {PRIVATE_KEY}")
        return 2

    client = SubstrateCloud()
    manifest = Manifest.from_yaml(MANIFEST)

    print("=== plan ===")
    print(client.plan(manifest).summary())

    print("\n=== apply ===")
    inst = client.apply(manifest)
    print(f"instance {inst.name} ({inst.id}) status={inst.status.value}")

    try:
        print("\n=== wait active ===")
        active = client.instances.wait_until_active(inst.id, timeout=1500, poll_interval=10)
        ip = str(active.ip_address)
        port = active.ssh_port or 22
        user = active.ssh_user or "substratecloud"
        print(f"active ip={ip}")

        print("\n=== wait SSH ===")
        for i in range(24):
            rc, _ = ssh(ip, port, user, "echo ok", timeout=15)
            if rc == 0:
                print(f"SSH up after {i + 1} attempt(s)")
                break
            time.sleep(10)
        else:
            print("FAIL: SSH never reachable")
            return 1

        print("\n=== wait repo deploy (marker) ===")
        for i in range(40):
            rc, out = ssh(ip, port, user, f"sudo test -f {MARKER} && sudo cat {MARKER}", timeout=20)
            if rc == 0 and "REPO_DEPLOY_OK" in out:
                print(f"marker OK after {(i + 1) * 15}s")
                break
            time.sleep(15)
        else:
            print("FAIL: repo deploy marker missing")
            rc, log = ssh(ip, port, user, "sudo tail -80 /var/log/cloud-init-output.log 2>/dev/null || true")
            print(log[:2000] if log else f"cloud-init tail rc={rc}")
            return 1

        checks = [
            ("repo_readme", f"test -f {REPO_DEST}/README.md && head -2 {REPO_DEST}/README.md"),
            ("repo_git", f"test -d {REPO_DEST}/.git"),
        ]
        print("\n=== verify repo on VM ===")
        failed = 0
        for name, cmd in checks:
            rc, out = ssh(ip, port, user, cmd, timeout=30)
            ok = rc == 0
            print(f"  {'PASS' if ok else 'FAIL'} {name}: {out[:120]}")
            if not ok:
                failed += 1

        if failed:
            return 1
        print("\nE2E PASS: public repo cloned on GPU VM via SDK apply")
        return 0
    finally:
        print("\n=== destroy ===")
        deleted = client.destroy(MANIFEST_NAME)
        print(f"destroyed {len(deleted)} instance(s)")


if __name__ == "__main__":
    sys.exit(main())
