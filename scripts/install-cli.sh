#!/usr/bin/env bash
# Install SubstrateCloud SDK + CLI — no system pip, no git, no pipx required.
# Needs: python3 (+ python3-venv on Debian/Ubuntu). Everything else is self-contained.
set -euo pipefail

REPO="${SUBSTRATECLOUD_SDK_REPO:-substrate-cloud/probable-dollop}"
BRANCH="${SUBSTRATECLOUD_SDK_BRANCH:-main}"
INSTALL_ROOT="${SUBSTRATECLOUD_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/substratecloud}"
VENV="${INSTALL_ROOT}/venv"
BIN_DIR="${HOME}/.local/bin"
WRAPPER="${BIN_DIR}/substratecloud"

# Zipball avoids a git dependency; pip resolves the package from the repo root.
PIP_SPEC="substratecloud[cli] @ https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"

pick_python() {
  if [[ -n "${VIRTUAL_ENV:-}" ]] && [[ -x /usr/bin/python3 ]]; then
    echo /usr/bin/python3
    return
  fi
  command -v python3
}

die() {
  echo "substratecloud install: $*" >&2
  exit 1
}

PYTHON="$(pick_python)" || die "python3 not found. Install Python 3.10+ and retry."

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  die "Python 3.10+ required ($( "$PYTHON" --version 2>/dev/null || echo unknown ))."
fi

if ! "$PYTHON" -m venv --help >/dev/null 2>&1; then
  die "python3-venv is missing. On Debian/Ubuntu run: sudo apt install -y python3-venv"
fi

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "Creating isolated environment at ${VENV} ..."
  "$PYTHON" -m venv "$VENV"
fi

VPY="${VENV}/bin/python"
if ! "$VPY" -m pip --version >/dev/null 2>&1; then
  echo "Bootstrapping pip in venv ..."
  "$VPY" -m ensurepip --upgrade 2>/dev/null || true
fi
"$VPY" -m pip --version >/dev/null 2>&1 || die "pip unavailable in venv. Try: sudo apt install -y python3-venv python3-pip"

echo "Installing substratecloud[cli] from ${REPO}@${BRANCH} ..."
"$VPY" -m pip install --upgrade pip wheel
"$VPY" -m pip install --upgrade "${PIP_SPEC}"

if [[ ! -x "${VENV}/bin/substratecloud" ]]; then
  die "install finished but substratecloud CLI not found in ${VENV}/bin"
fi

cat >"$WRAPPER" <<EOF
#!/usr/bin/env bash
exec "${VENV}/bin/substratecloud" "\$@"
EOF
chmod +x "$WRAPPER"

echo ""
echo "Installed substratecloud → ${WRAPPER}"
echo "  Version: $("$WRAPPER" --version 2>/dev/null || "$WRAPPER" --help 2>&1 | head -1)"
echo ""
if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
  echo "Add to your shell profile (~/.bashrc or ~/.zshrc):"
  echo "  export PATH=\"${BIN_DIR}:\$PATH\""
  echo ""
  echo "Then run: substratecloud config init"
  echo "Or use now: ${WRAPPER} config init"
else
  echo "Run: substratecloud config init"
  echo "     (or export SUBSTRATECLOUD_MCP_TOKEN=mcp_...)"
fi
