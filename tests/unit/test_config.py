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


def test_save_creates_config_dir_0700(tmp_path: Path):
    # The directory holding the token must not be world-traversable.
    cfg = Config(profiles={"default": Profile(token=SecretStr("mcp_x"), base_url="x")})
    path = tmp_path / "nested" / "config.toml"
    save(cfg, path)
    mode = path.parent.stat().st_mode & 0o777
    if mode != 0:  # POSIX only; Windows reports 0 here
        assert mode == 0o700, f"config dir created with {oct(mode)}, expected 0o700"


def test_save_file_is_0600_without_relying_on_post_write_chmod(tmp_path: Path, monkeypatch):
    # The token must never be world-readable, not even for the instant between
    # creating the file and tightening its mode. So the file must be created
    # 0600 from the start, not chmod'd afterwards. Neutralise chmod to prove
    # the secure mode does not depend on a post-write fixup.
    monkeypatch.setattr(Path, "chmod", lambda self, mode: None)
    cfg = Config(profiles={"default": Profile(token=SecretStr("mcp_secret"), base_url="x")})
    path = tmp_path / "nested" / "config.toml"
    save(cfg, path)
    mode = path.stat().st_mode & 0o777
    if mode != 0:
        assert mode == 0o600, f"file created with {oct(mode)}, expected 0o600"
