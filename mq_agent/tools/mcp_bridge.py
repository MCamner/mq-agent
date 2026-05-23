"""Bridge to mq-mcp for tool routing via MCP protocol."""
from __future__ import annotations

import json
from typing import Any

try:
    import httpx  # noqa: F401
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

MCP_START_HINT = (
    "Start mq-mcp with:\n"
    "  uv --directory ~/mq-mcp/mq-mcp run python server.py"
)


class MCPBridge:
    """Routes tool calls to a running mq-mcp server over HTTP."""

    def __init__(self, endpoint: str = "http://localhost:8765"):
        self.endpoint = endpoint.rstrip("/")
        self._available: list[str] | None = None

    # ── connectivity ───────────────────────────────────────────────────────

    def is_available(self) -> bool:
        if not _HAS_HTTPX:
            return False
        import httpx
        try:
            httpx.get(f"{self.endpoint}/health", timeout=2)
            return True
        except Exception:
            return False

    def not_reachable_message(self) -> str:
        return (
            f"mq-mcp is not reachable at {self.endpoint}\n\n"
            f"{MCP_START_HINT}"
        )

    # ── tool listing ───────────────────────────────────────────────────────

    def _fetch_tools_raw(self) -> list:
        """Returns the raw tools list from the server (strings or dicts)."""
        if not _HAS_HTTPX:
            return []
        import httpx
        try:
            response = httpx.get(f"{self.endpoint}/tools", timeout=5)
            data = response.json()
            raw = data.get("tools", [])
            self._available = [
                item["name"] if isinstance(item, dict) else str(item)
                for item in raw
            ]
            return raw
        except Exception:
            return []

    def list_tools(self) -> list[str]:
        """Return tool names. Backward-compatible."""
        raw = self._fetch_tools_raw()
        return [
            item["name"] if isinstance(item, dict) else str(item)
            for item in raw
        ]

    def list_tool_specs(self) -> list:
        """Return MCPToolSpec objects for all discovered tools."""
        from .mcp_registry import MCPToolSpec
        raw = self._fetch_tools_raw()
        specs = []
        for item in raw:
            if isinstance(item, dict):
                specs.append(MCPToolSpec.from_dict(item))
            else:
                specs.append(MCPToolSpec.from_name(str(item)))
        return specs

    # ── tool description ───────────────────────────────────────────────────

    def describe_tool(self, name: str) -> Any:
        """Return an MCPToolSpec for a tool. Falls back to name-classification if server is down."""
        from .mcp_registry import MCPToolSpec
        if not _HAS_HTTPX:
            return MCPToolSpec.from_name(name)
        import httpx
        try:
            response = httpx.get(f"{self.endpoint}/tools/{name}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and "name" in data:
                    return MCPToolSpec.from_dict(data)
            # 404 or unexpected shape — fall through to name classification
        except Exception:
            pass
        # Confirm the tool exists in the listing before classifying by name
        tools = self._available or self.list_tools()
        if name in tools:
            return MCPToolSpec.from_name(name)
        # Server is down or tool unknown — still return a classification
        return MCPToolSpec.from_name(name)

    # ── tool execution ─────────────────────────────────────────────────────

    def call_tool(self, tool_name: str, args: dict) -> Any:
        if not _HAS_HTTPX:
            return "httpx not installed; cannot reach mq-mcp"
        import httpx
        try:
            response = httpx.post(
                f"{self.endpoint}/tools/{tool_name}",
                json=args,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            return self.not_reachable_message()
        except httpx.HTTPStatusError as exc:
            return f"mq-mcp error {exc.response.status_code}: {exc.response.text}"
        except Exception as exc:
            return f"MCP bridge error: {exc}"


_default_bridge = MCPBridge()


def mcp_call(tool_name: str, args_json: str = "{}") -> str:
    """Tool-registry-compatible wrapper for MCP bridge calls."""
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return "Invalid JSON args"
    result = _default_bridge.call_tool(tool_name, args)
    return json.dumps(result) if not isinstance(result, str) else result
