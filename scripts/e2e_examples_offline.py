#!/usr/bin/env python3
"""Offline E2E: validate every example manifest + run all Python examples."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = {**os.environ, "SUBSTRATECLOUD_EXAMPLES_OFFLINE": "1", "SUBSTRATECLOUD_MCP_TOKEN": "mcp_test"}
    env["SUBSTRATECLOUD_API_BASE_URL"] = "https://test.example.com/ondemand-mcp-manager"

    print(">>> pytest (unit + examples)")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        return proc.returncode

    print(">>> substratecloud plan on each manifest")
    manifests = sorted((ROOT / "examples" / "manifests").glob("*.yaml"))
    for m in manifests:
        proc = subprocess.run(
            ["substratecloud", "plan", str(m)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"FAIL plan {m.name}: {proc.stderr}")
            return 1
        print(f"  OK plan {m.name}")

    print("\nOFFLINE E2E PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
