#!/usr/bin/env bash
# Install Substrate SDK + CLI from the public GitHub repo (dev branch by default).
set -euo pipefail

REPO="${SUBSTRATE_SDK_REPO:-https://github.com/gssondhi-substrate/SDK.git}"
BRANCH="${SUBSTRATE_SDK_BRANCH:-dev}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install "substrate[cli] @ git+${REPO}@${BRANCH}"

echo "Installed. Run: substrate --help"
echo "Configure: substrate config init   # or export SUBSTRATE_MCP_TOKEN=mcp_..."
