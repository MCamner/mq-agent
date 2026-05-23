"""Bridge to mq-mcp for tool routing via MCP protocol."""
import json
from typing import Any

try:
    import httpx  # noqa: F401
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


class MCPBridge:
    """Routes tool calls to a running mq-mcp server over HTTP."""

    def __init__(self, endpoint: str = "http://localhost:8765"):
        self.endpoint = endpoint.rstrip("/")
        self._available: list[str] | None = None

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
            return f"mq-mcp not reachable at {self.endpoint}"
        except httpx.HTTPStatusError as exc:
            return f"mq-mcp error {exc.response.status_code}: {exc.response.text}"
        except Exception as exc:
            return f"MCP bridge error: {exc}"

    def list_tools(self) -> list[str]:
        if not _HAS_HTTPX:
            return []

        import httpx

        try:
            response = httpx.get(f"{self.endpoint}/tools", timeout=5)
            data = response.json()
            self._available = data.get("tools", [])
            return self._available or []
        except Exception:
            return []

    def is_available(self) -> bool:
        if not _HAS_HTTPX:
            return False

        import httpx

        try:
            httpx.get(f"{self.endpoint}/health", timeout=2)
            return True
        except Exception:
            return False


_default_bridge = MCPBridge()


def mcp_call(tool_name: str, args_json: str = "{}") -> str:
    """Tool-registry-compatible wrapper for MCP bridge calls."""
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return "Invalid JSON args"
    result = _default_bridge.call_tool(tool_name, args)
    return json.dumps(result) if not isinstance(result, str) else result
