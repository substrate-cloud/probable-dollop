"""Deploy a git repository onto a GPU VM via BootScript.git_clone.

Patterns for "put my code on the box":
  1. YAML boot_script `steps:` with `git clone` (see manifests/deploy-git-repo.yaml)
  2. Fluent BootScript().git_clone(...) → apply (this file)
  3. Docker workload: clone in container `args` before your entrypoint

Private repos: pass a deploy key or HTTPS token in env at boot; never bake
secrets into committed YAML — use `{from_env: GIT_TOKEN}` in Docker env or
fetch from your secret store in a boot_script step.

Run (offline):  SUBSTRATECLOUD_EXAMPLES_OFFLINE=1 python 15_deploy_git_repo.py
Run (live):     SUBSTRATECLOUD_EXAMPLES_LIVE=1 SUBSTRATECLOUD_MCP_TOKEN=mcp_... python 15_deploy_git_repo.py
"""

from __future__ import annotations

import os

from _common import is_live_run, is_offline_ci, require_live
from substratecloud import BootScript, SubstrateCloud
from substratecloud.declarative.manifest import Manifest
from substratecloud.workloads.boot_script.workload import BootScriptWorkload

# Point at your repository (HTTPS public clone).
REPO_URL = os.environ.get("SUBSTRATECLOUD_DEPLOY_REPO", "https://github.com/pytorch/examples")
REPO_DEST = os.environ.get("SUBSTRATECLOUD_DEPLOY_DEST", "/opt/app/repo")
MANIFEST_NAME = "deploy-git-repo-sdk"


def build_workload() -> BootScriptWorkload:
    script = (
        BootScript()
        .with_base_image_setup()
        .git_clone(REPO_URL, REPO_DEST, depth=1)
        .write_file(
            "/var/log/substratecloud-boot/repo-deploy.marker",
            "REPO_DEPLOY_OK",
            mode="0644",
        )
    )
    return BootScriptWorkload(script, estimated_boot_s=600)


def build_manifest() -> Manifest:
    # Declarative path uses boot_script body rendered from BootScript steps.
    wl = build_workload()
    body = wl.script.render()
    from substratecloud.declarative.builder import Launch

    return (
        Launch()
        .boot_script(body=body)
        .gpu("A4000", max_price=1.5)
        .tags("example:git-deploy")
        .budget(3)
        .wait(until_active=True, timeout=1500)
        .to_manifest(name=MANIFEST_NAME)
    )


def main() -> None:
    manifest = build_manifest()
    if is_offline_ci():
        print(manifest.to_yaml())
        return
    client = SubstrateCloud()
    print(client.plan(manifest).summary())
    if not is_live_run():
        print("\nLive deploy:")
        print("  export SUBSTRATECLOUD_EXAMPLES_LIVE=1")
        print(f"  export SUBSTRATECLOUD_DEPLOY_REPO={REPO_URL!r}")
        print("  python 15_deploy_git_repo.py")
        print(f"  substratecloud destroy {MANIFEST_NAME}")
        return
    require_live()
    inst = client.apply(manifest)
    print(f"deployed {inst.name} ({inst.id}) ip={inst.ip_address}")
    print(f"when done: substratecloud destroy {MANIFEST_NAME}")


if __name__ == "__main__":
    main()
