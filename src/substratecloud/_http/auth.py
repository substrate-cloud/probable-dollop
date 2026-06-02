"""Auth resolution: explicit kwarg → env → config file. Token is held in SecretStr."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import SecretStr

from substratecloud._http.errors import AuthError

if TYPE_CHECKING:
    from substratecloud.config import Profile

ENV_TOKEN = "SUBSTRATECLOUD_MCP_TOKEN"
ENV_BASE_URL = "SUBSTRATECLOUD_API_BASE_URL"
ENV_PROFILE = "SUBSTRATECLOUD_PROFILE"


def resolve_token(
    explicit: str | SecretStr | None = None,
    profile: Profile | None = None,
) -> SecretStr:
    """Resolve an MCP token from the configured sources.

    Priority: explicit > SUBSTRATECLOUD_MCP_TOKEN env var > profile.token.
    Raises AuthError with a clear message pointing at `substratecloud config init`.
    """
    if explicit is not None:
        return explicit if isinstance(explicit, SecretStr) else SecretStr(explicit)

    env_val = os.environ.get(ENV_TOKEN)
    if env_val:
        return SecretStr(env_val)

    if profile is not None and profile.token is not None:
        return profile.token

    raise AuthError(
        "No MCP token configured. Set SUBSTRATECLOUD_MCP_TOKEN or run "
        "`substratecloud config init` to write a profile."
    )


def resolve_base_url(
    explicit: str | None = None,
    profile: Profile | None = None,
) -> str:
    """Resolve API base URL. Same priority order as token."""
    if explicit:
        return explicit.rstrip("/")

    env_val = os.environ.get(ENV_BASE_URL)
    if env_val:
        return env_val.rstrip("/")

    if profile is not None and profile.base_url:
        return profile.base_url.rstrip("/")

    raise AuthError(
        "No SubstrateCloud API base URL configured. Set SUBSTRATECLOUD_API_BASE_URL or run "
        "`substratecloud config init`."
    )


def bearer_header(token: SecretStr) -> dict[str, str]:
    """Construct the Authorization header. Token is unwrapped only here."""
    return {"Authorization": f"Bearer {token.get_secret_value()}"}
