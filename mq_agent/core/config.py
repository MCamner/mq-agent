"""Configuration management for mq-agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".mq-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict[str, Any]:
    """Load configuration from ~/.mq-agent/config.json."""
    if not CONFIG_FILE.exists():
        return {"mcp_servers": {}}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {"mcp_servers": {}}


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to ~/.mq-agent/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def add_mcp_server(name: str, url: str) -> None:
    """Register an MCP server endpoint."""
    config = load_config()
    if "mcp_servers" not in config:
        config["mcp_servers"] = {}
    config["mcp_servers"][name] = url.rstrip("/")
    save_config(config)


def remove_mcp_server(name: str) -> bool:
    """Remove a registered MCP server. Returns True if removed."""
    config = load_config()
    if "mcp_servers" in config and name in config["mcp_servers"]:
        del config["mcp_servers"][name]
        save_config(config)
        return True
    return False


def get_mcp_servers() -> dict[str, str]:
    """Get all registered MCP server endpoints with MQ ecosystem defaults."""
    config = load_config()
    servers = config.get("mcp_servers", {})
    if "mq-mcp" not in servers:
        # Ensure default is always there unless explicitly overridden
        servers["mq-mcp"] = "http://localhost:8765"
    if "mq-image-analyze" not in servers:
        # Visual perception tools. mq-agent delegates; it does not analyze images locally.
        servers["mq-image-analyze"] = "http://localhost:8766"
    return servers
