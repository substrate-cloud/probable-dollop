#!/usr/bin/env bash
# Install SubstrateCloud SDK + CLI from the public GitHub repo (dev branch by default).
set -euo pipefail

REPO="${SUBSTRATECLOUD_SDK_REPO:-https://github.com/gssondhi-substrate/SDK.git}"
BRANCH="${SUBSTRATECLOUD_SDK_BRANCH:-dev}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install "substratecloud[cli] @ git+${REPO}@${BRANCH}"

echo "Installed. Run: substratecloud --help"
echo "Configure: substratecloud config init   # or export SUBSTRATECLOUD_MCP_TOKEN=mcp_..."
