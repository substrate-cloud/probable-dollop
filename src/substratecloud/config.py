"""TOML config at ~/.config/substratecloud/config.toml with profile support.

Resolution order (CLI flag → env → config file → default):
  --token / --base-url       (per-command)
  SUBSTRATECLOUD_MCP_TOKEN env    (always)
  SUBSTRATECLOUD_API_BASE_URL env (always)
  SUBSTRATECLOUD_PROFILE env      (selects which profile in the file)
  [default] profile          (named "default" unless SUBSTRATECLOUD_PROFILE set)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

import tomli_w

DEFAULT_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "substratecloud"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"


class Profile(BaseModel):
    """A named credential profile."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    token: SecretStr | None = None
    base_url: str | None = None
    default_region: str | None = None
    default_ssh_key_id: str | None = None
    default_tags: list[str] = Field(default_factory=list)


class Config(BaseModel):
    """Top-level config file model."""

    model_config = ConfigDict(extra="ignore")

    active_profile: str = "default"
    profiles: dict[str, Profile] = Field(default_factory=dict)

    def get_profile(self, name: str | None = None) -> Profile | None:
        key = name or os.environ.get("SUBSTRATECLOUD_PROFILE") or self.active_profile
        return self.profiles.get(key)


def load(path: Path | None = None) -> Config:
    """Read config from disk. Returns an empty Config if the file is absent."""
    p = path or DEFAULT_CONFIG_PATH
    if not p.exists():
        return Config()
    raw = tomllib.loads(p.read_text())
    return Config.model_validate(_lift_legacy(raw))


def save(config: Config, path: Path | None = None) -> Path:
    """Write config to disk so the token is never world-readable.

    The file is created 0600 from the start — written to a temp file in the
    same directory and atomically renamed into place — rather than written
    with the process umask and tightened with a later chmod. That interim
    window (file present, perms not yet narrowed) could expose the token on a
    shared machine. The containing directory is forced to 0700.
    """
    p = path or DEFAULT_CONFIG_PATH
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        p.parent.chmod(0o700)  # enforce 0700 even if the directory already existed
    except OSError:  # pragma: no cover — windows
        pass
    serialised = _dump_for_toml(config)
    data = tomli_w.dumps(serialised)
    # mkstemp creates the file readable/writable by the owner only (0600).
    fd, tmp_name = tempfile.mkstemp(dir=str(p.parent), prefix=".config-", suffix=".toml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp_name, p)  # atomic; the 0600 temp inode becomes config.toml
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:  # pragma: no cover
            pass
        raise
    return p


def _dump_for_toml(config: Config) -> dict[str, Any]:
    """Serialise Config to plain dict for tomli_w. Unwraps SecretStr → str."""
    out: dict[str, Any] = {"active_profile": config.active_profile, "profiles": {}}
    for name, prof in config.profiles.items():
        p: dict[str, Any] = {}
        if prof.token is not None:
            p["token"] = prof.token.get_secret_value()
        if prof.base_url:
            p["base_url"] = prof.base_url
        if prof.default_region:
            p["default_region"] = prof.default_region
        if prof.default_ssh_key_id:
            p["default_ssh_key_id"] = prof.default_ssh_key_id
        if prof.default_tags:
            p["default_tags"] = prof.default_tags
        out["profiles"][name] = p
    return out


def _lift_legacy(raw: dict[str, Any]) -> dict[str, Any]:
    """Tolerate single-profile (flat) configs: lift top-level token/base_url into a 'default' profile."""
    if "profiles" in raw:
        return raw
    legacy_keys = {"token", "base_url", "default_region", "default_ssh_key_id", "default_tags"}
    if not any(k in raw for k in legacy_keys):
        return raw
    profile_data = {k: v for k, v in raw.items() if k in legacy_keys}
    return {"active_profile": "default", "profiles": {"default": profile_data}}
