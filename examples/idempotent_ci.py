"""Safe CI redeploy. Run from a pipeline; never duplicate-launches.

The pattern: every CI job calls `apply` on the manifest. On the first run
it launches. On every subsequent run it finds the existing instance by
`manifest:<name>` tag and reuses it — no extra API write, no extra spend.

If the manifest's image/args/env-keys/ports change, `apply` refuses with
a drift error (CI should fail loudly rather than silently relaunch). Pass
`force=True` from the deploy job that owns version bumps.

Run:
    python examples/idempotent_ci.py             # production-style flow
    python examples/idempotent_ci.py --force     # force version-bump replace
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from substrate import Substrate
from substrate._http.errors import SubstrateError

MANIFEST = Path(__file__).parent / "manifests" / "vllm-inference.yaml"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Destroy+relaunch on drift.")
    args = parser.parse_args()

    client = Substrate()

    try:
        inst = client.apply(MANIFEST, force=args.force)
    except SubstrateError as exc:
        if "apply.drift" in str(exc):
            print(
                "DRIFT DETECTED. The manifest's image/args/env-keys/ports "
                "differ from the running instance. Either:\n"
                "  • bump versions explicitly with --force, or\n"
                "  • `substrate destroy` first if you want a clean relaunch.",
                file=sys.stderr,
            )
            print(f"\n  details: {exc}", file=sys.stderr)
            return 2
        raise

    print(f"Active: {inst.name} ({inst.id})  endpoint=http://{inst.ip_address}:8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
