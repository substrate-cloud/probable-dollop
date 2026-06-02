"""Config TOML round-trip + profile resolution."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from substratecloud.config import Config, Profile, load, save


def test_save_and_load_roundtrip(tmp_path: Path):
    cfg = Config(
        active_profile="default",
        profiles={
            "default": Profile(
                token=SecretStr("mcp_aaa"),
                base_url="https://example.com/x",
                default_region="Europe",
            ),
            "prod": Profile(token=SecretStr("mcp_bbb"), base_url="https://example.com/y"),
        },
    )
    path = tmp_path / "config.toml"
    save(cfg, path)
    assert path.exists()
    loaded = load(path)
    assert loaded.active_profile == "default"
    assert loaded.profiles["default"].base_url == "https://example.com/x"
    # token round-trips through SecretStr
    assert loaded.profiles["default"].token.get_secret_value() == "mcp_aaa"


def test_legacy_flat_config_lifts_to_default_profile(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('token = "mcp_legacy"\nbase_url = "https://x"\n')
    loaded = load(path)
    assert "default" in loaded.profiles
    assert loaded.profiles["default"].token.get_secret_value() == "mcp_legacy"


def test_get_profile_respects_env(tmp_path: Path, monkeypatch):
    cfg = Config(
        profiles={
            "default": Profile(token=SecretStr("mcp_a"), base_url="x"),
            "staging": Profile(token=SecretStr("mcp_b"), base_url="y"),
        }
    )
    monkeypatch.setenv("SUBSTRATECLOUD_PROFILE", "staging")
    prof = cfg.get_profile()
    assert prof is cfg.profiles["staging"]


def test_save_chmod_0600(tmp_path: Path):
    cfg = Config(profiles={"default": Profile(token=SecretStr("mcp_x"), base_url="x")})
    path = tmp_path / "config.toml"
    save(cfg, path)
    mode = path.stat().st_mode & 0o777
    # Windows skips chmod; on POSIX we expect 0600.
    if mode != 0:  # pragma: no branch
        assert mode == 0o600
