"""Typed boot-script step types.

Each step renders an idempotent bash block: it checks first, does the work,
and writes a per-step log to /var/log/substratecloud-boot/<step>.log plus a status
entry to /var/log/substratecloud-boot/manifest.json.

Designed so re-running the script (after a reboot, retry, or rebuild) is safe.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from substratecloud.workloads.secret import Secret, resolve_value

_LOG_DIR = "/var/log/substratecloud-boot"

# Newlines / NULs in fields that are interpolated into a systemd unit can
# inject extra directives into a unit that runs as root at boot. Refuse them.
_SYSTEMD_CTRL_CHARS = re.compile(r"[\r\n\x00]")


def _reject_systemd_control(field_name: str, value: str) -> str:
    if _SYSTEMD_CTRL_CHARS.search(value):
        raise ValueError(
            f"RunSystemdUnit.{field_name} contains a newline or control character. "
            f"Such a value could inject directives into a unit that runs as root "
            f"at boot, so rendering is refused. Use EnvironmentFile= or .custom() "
            f"if you genuinely need multi-line content."
        )
    return value


def _systemd_env_quote(value: str) -> str:
    """Escape a value for use inside a double-quoted systemd `Environment=` entry."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _log_block(step_id: str) -> tuple[str, str]:
    """Return (open, close) bash snippets that tee step output and record status."""
    open_snip = (
        f"\n# --- {step_id} ---\n"
        f"_substrate_step_id='{step_id}'\n"
        f"_substrate_step_log='{_LOG_DIR}/{step_id}.log'\n"
        f"_substrate_step_start=$(date +%s)\n"
        f"echo \"[substratecloud-boot] {step_id} starting at $(date -u +%FT%TZ)\" "
        f"| tee -a \"$_substrate_step_log\"\n"
        f"{{ \n"
    )
    close_snip = (
        f"\n}} 2>&1 | tee -a \"$_substrate_step_log\"\n"
        f"_substrate_step_rc=${{PIPESTATUS[0]}}\n"
        f"echo \"[substratecloud-boot] {step_id} done rc=$_substrate_step_rc\" "
        f"| tee -a \"$_substrate_step_log\"\n"
        f"python3 - <<'PYEOF' \"$_substrate_step_id\" \"$_substrate_step_rc\" "
        f"\"$_substrate_step_start\" || true\n"
        f"import json, os, sys, time\n"
        f"step_id, rc, started = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])\n"
        f"path = '{_LOG_DIR}/manifest.json'\n"
        f"data = []\n"
        f"if os.path.exists(path):\n"
        f"    try:\n"
        f"        with open(path) as f: data = json.load(f)\n"
        f"    except Exception: data = []\n"
        f"data.append({{'step': step_id, 'rc': rc, 'started_at': started, "
        f"'finished_at': int(time.time())}})\n"
        f"with open(path, 'w') as f: json.dump(data, f, indent=2)\n"
        f"PYEOF\n"
        f"if [ \"$_substrate_step_rc\" -ne 0 ]; then exit \"$_substrate_step_rc\"; fi\n"
    )
    return open_snip, close_snip


@dataclass
class Step:
    """Base class for a step. Concrete steps override `_body()`."""

    step_id: str

    def render(self) -> str:
        open_snip, close_snip = _log_block(self.step_id)
        return open_snip + self._body() + close_snip

    def _body(self) -> str:  # pragma: no cover — abstract
        raise NotImplementedError

    def secrets(self) -> list[Secret]:
        return []


@dataclass
class BaseImageSetup(Step):
    step_id: str = "base_image_setup"

    def _body(self) -> str:
        return (
            "export DEBIAN_FRONTEND=noninteractive\n"
            "apt-get update -y\n"
            "apt-get install -y --no-install-recommends "
            "ca-certificates curl gnupg lsb-release jq build-essential python3 python3-pip\n"
        )


@dataclass
class InstallUv(Step):
    step_id: str = "install_uv"

    def _body(self) -> str:
        return (
            "if ! command -v uv >/dev/null 2>&1; then\n"
            "  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
            "  install -m 0755 \"$HOME/.local/bin/uv\" /usr/local/bin/uv || true\n"
            "fi\n"
            "uv --version\n"
        )


@dataclass
class InstallCudaDrivers(Step):
    step_id: str = "install_cuda_drivers"

    def _body(self) -> str:
        return (
            "if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then\n"
            "  echo 'nvidia-smi already present; skipping driver install.'\n"
            "else\n"
            "  echo 'NVIDIA drivers missing on this image; expected to be pre-baked. Aborting.'\n"
            "  exit 1\n"
            "fi\n"
        )


@dataclass
class PipInstall(Step):
    packages: list[str] = field(default_factory=list)
    use_uv: bool = True
    step_id: str = "pip_install"

    def _body(self) -> str:
        if not self.packages:
            return "echo 'no packages to install'\n"
        quoted = " ".join(shlex.quote(p) for p in self.packages)
        if self.use_uv:
            return (
                "if command -v uv >/dev/null 2>&1; then\n"
                f"  uv pip install --system {quoted}\n"
                "else\n"
                f"  pip3 install --upgrade {quoted}\n"
                "fi\n"
            )
        return f"pip3 install --upgrade {quoted}\n"


@dataclass
class PullHFModel(Step):
    model_id: str = ""
    revision: str | None = None
    hf_token: Secret | None = None
    cache_dir: str = "/opt/models"
    step_id: str = "pull_hf_model"

    def _body(self) -> str:
        token_setup = ""
        if self.hf_token is not None:
            token_setup = (
                'if [ -z "${HF_TOKEN:-}" ]; then\n'
                '  echo "HF_TOKEN not present in env at boot; using injected token (one-shot)." \n'
                "fi\n"
            )
        rev = f"--revision {shlex.quote(self.revision)}" if self.revision else ""
        return (
            "mkdir -p " + shlex.quote(self.cache_dir) + "\n"
            "if ! command -v huggingface-cli >/dev/null 2>&1; then\n"
            "  pip3 install --upgrade 'huggingface_hub[cli]'\n"
            "fi\n"
            + token_setup
            + f"HF_HUB_ENABLE_HF_TRANSFER=1 huggingface-cli download {rev} "
            f"{shlex.quote(self.model_id)} --local-dir {shlex.quote(self.cache_dir)}/"
            f"{shlex.quote(self.model_id.replace('/', '__'))}\n"
        )

    def secrets(self) -> list[Secret]:
        return [self.hf_token] if self.hf_token else []


@dataclass
class RunSystemdUnit(Step):
    name: str = ""
    exec_start: str = ""
    description: str = ""
    restart: str = "on-failure"
    environment: dict[str, str | Secret] = field(default_factory=dict)
    after: list[str] = field(default_factory=lambda: ["network-online.target"])
    user: str = "root"
    step_id: str = "run_systemd_unit"

    def _body(self) -> str:
        if "/" in self.name:
            raise ValueError("RunSystemdUnit.name must be a bare unit name (no '/').")
        _reject_systemd_control("name", self.name)
        _reject_systemd_control("exec_start", self.exec_start)
        _reject_systemd_control("description", self.description)
        _reject_systemd_control("user", self.user)
        env_lines = ""
        for k, v in self.environment.items():
            _reject_systemd_control(f"environment[{k!r}] name", k)
            resolved = _reject_systemd_control(f"environment[{k!r}]", resolve_value(v))
            env_lines += f'Environment="{_systemd_env_quote(k)}={_systemd_env_quote(resolved)}"\n'
        after = " ".join(self.after)
        unit_path = f"/etc/systemd/system/{shlex.quote(self.name)}.service"
        heredoc = (
            "[Unit]\n"
            f"Description={self.description or self.name}\n"
            f"After={after}\n\n"
            "[Service]\n"
            f"User={self.user}\n"
            f"ExecStart={self.exec_start}\n"
            f"Restart={self.restart}\n"
            "RestartSec=5\n"
            f"{env_lines}"
            "\n[Install]\nWantedBy=multi-user.target\n"
        )
        return (
            f"cat > {unit_path} <<'SUBSTRATECLOUD_UNIT_EOF'\n{heredoc}SUBSTRATECLOUD_UNIT_EOF\n"
            f"systemctl daemon-reload\n"
            f"systemctl enable --now {shlex.quote(self.name)}.service\n"
        )

    def secrets(self) -> list[Secret]:
        return [v for v in self.environment.values() if isinstance(v, Secret)]


@dataclass
class StatusBeacon(Step):
    callback_url: str = ""
    initial_stage: str = "boot_finished"
    step_id: str = "status_beacon"

    def _body(self) -> str:
        # Write a tiny shell script that POSTs to the callback. Idempotent: runs once.
        if not self.callback_url:
            # local-only beacon (writes a file readable over SSH)
            return (
                f"mkdir -p {_LOG_DIR}\n"
                f"echo '{{\"stage\": \"{self.initial_stage}\", \"ts\": '\"$(date +%s)\"'}}' "
                f"> {_LOG_DIR}/beacon.json\n"
            )
        return (
            f"curl -sS -X POST {shlex.quote(self.callback_url)} "
            f"-H 'content-type: application/json' "
            f"--data '{{\"stage\": \"{self.initial_stage}\", \"ts\": '\"$(date +%s)\"'}}' "
            f"|| echo 'beacon POST failed (non-fatal)'\n"
        )


@dataclass
class IdleShutdown(Step):
    """Install a watchdog that runs `shutdown -h` after N idle minutes.

    Note: OS shutdown does NOT stop SubstrateCloud billing — the instance must be
    DELETED via the API. See plan doc §10.5. This step pairs the OS shutdown
    with a curl to a deletion-broker URL if supplied.
    """

    minutes: int = 30
    deletion_callback: str | None = None
    step_id: str = "idle_shutdown"

    def _body(self) -> str:
        idle_min = self.minutes
        del_curl = ""
        if self.deletion_callback:
            del_curl = (
                f"curl -sS -X POST {shlex.quote(self.deletion_callback)} "
                f"-H 'content-type: application/json' "
                f"--data '{{\"reason\": \"idle\", \"ts\": '\"$(date +%s)\"'}}' || true\n"
            )
        script = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"IDLE_MIN={idle_min}\n"
            "GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null "
            "| awk '{s+=$1} END {print s+0}')\n"
            "SSH_SESSIONS=$(who | wc -l)\n"
            "if [ \"$GPU_UTIL\" -lt 5 ] && [ \"$SSH_SESSIONS\" -lt 1 ]; then\n"
            "  IDLE_FILE=/var/run/substratecloud-idle-since\n"
            "  if [ ! -f \"$IDLE_FILE\" ]; then date +%s > \"$IDLE_FILE\"; exit 0; fi\n"
            "  IDLE_SINCE=$(cat \"$IDLE_FILE\")\n"
            "  NOW=$(date +%s)\n"
            "  if [ $(( (NOW - IDLE_SINCE) / 60 )) -ge \"$IDLE_MIN\" ]; then\n"
            f"    {del_curl}"
            "    /sbin/shutdown -h now 'substratecloud idle shutdown'\n"
            "  fi\n"
            "else\n"
            "  rm -f /var/run/substratecloud-idle-since\n"
            "fi\n"
        )
        return (
            "cat > /usr/local/sbin/substratecloud-idle-check <<'SUBSTRATECLOUD_IDLE_EOF'\n"
            + script
            + "SUBSTRATECLOUD_IDLE_EOF\n"
            "chmod +x /usr/local/sbin/substratecloud-idle-check\n"
            "cat > /etc/cron.d/substratecloud-idle <<'CRON_EOF'\n"
            "*/5 * * * * root /usr/local/sbin/substratecloud-idle-check\n"
            "CRON_EOF\n"
        )


@dataclass
class CustomCommand(Step):
    command: str = ""
    step_id: str = "custom"

    def _body(self) -> str:
        return self.command + ("\n" if not self.command.endswith("\n") else "")


@dataclass
class GitClone(Step):
    repo: str = ""
    dest: str = ""
    branch: str | None = None
    depth: int | None = 1
    step_id: str = "git_clone"

    def _body(self) -> str:
        if not self.repo or not self.dest:
            raise ValueError("GitClone requires both repo and dest")
        opts: list[str] = []
        if self.branch:
            opts.extend(["--branch", shlex.quote(self.branch)])
        if self.depth is not None:
            opts.extend(["--depth", str(self.depth)])
        opt_str = " ".join(opts)
        dest = shlex.quote(self.dest)
        repo = shlex.quote(self.repo)
        return (
            "if ! command -v git >/dev/null 2>&1; then\n"
            "  apt-get install -y --no-install-recommends git\n"
            "fi\n"
            f"mkdir -p \"$(dirname {dest})\"\n"
            f"if [ -d {dest}/.git ]; then\n"
            f"  echo 'repo already present at {self.dest}; pulling latest'\n"
            f"  cd {dest} && git pull --ff-only || true\n"
            "else\n"
            f"  git clone {opt_str} {repo} {dest}\n"
            "fi\n"
        )


@dataclass
class WriteFile(Step):
    path: str = ""
    content: str = ""
    mode: str = "0644"
    step_id: str = "write_file"

    def _body(self) -> str:
        path = shlex.quote(self.path)
        return (
            f"mkdir -p \"$(dirname {path})\"\n"
            f"cat > {path} <<'SUBSTRATECLOUD_FILE_EOF'\n{self.content}\nSUBSTRATECLOUD_FILE_EOF\n"
            f"chmod {self.mode} {path}\n"
        )


_PREAMBLE = (
    "#!/usr/bin/env bash\n"
    "# Generated by substratecloud-sdk BootScript. Do not edit on-host.\n"
    "set -euo pipefail\n"
    f"mkdir -p {_LOG_DIR}\n"
    f"exec > >(tee -a {_LOG_DIR}/boot.log) 2>&1\n"
    "echo \"[substratecloud-boot] starting at $(date -u +%FT%TZ)\"\n"
)


def preamble() -> str:
    return _PREAMBLE


def epilogue() -> str:
    return "echo \"[substratecloud-boot] all steps completed at $(date -u +%FT%TZ)\"\n"


def render_steps(steps: list[Step]) -> str:
    body = "".join(s.render() for s in steps)
    return preamble() + body + epilogue()


def collect_secrets(steps: list[Step]) -> list[Secret]:
    seen: dict[Any, Secret] = {}
    for s in steps:
        for sec in s.secrets():
            seen[id(sec)] = sec
    return list(seen.values())


__all__ = [
    "Step",
    "BaseImageSetup",
    "InstallUv",
    "InstallCudaDrivers",
    "PipInstall",
    "PullHFModel",
    "RunSystemdUnit",
    "StatusBeacon",
    "IdleShutdown",
    "CustomCommand",
    "GitClone",
    "WriteFile",
    "render_steps",
    "collect_secrets",
]
