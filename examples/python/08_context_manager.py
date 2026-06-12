"""Use SubstrateCloud as a context manager to close HTTP connections."""

from __future__ import annotations

from substratecloud import SubstrateCloud


def main() -> None:
    import os

    # Avoid config load failures in CI — explicit env only.
    token = os.environ.get("SUBSTRATECLOUD_MCP_TOKEN", "mcp_offline_example")
    base = os.environ.get(
        "SUBSTRATECLOUD_API_BASE_URL", "https://test.example.com/ondemand-mcp-manager"
    )
    with SubstrateCloud(token=token, base_url=base) as client:
        print(f"endpoint: {client.base_url}")
        print("client closed on exit from `with` block")


if __name__ == "__main__":
    main()
