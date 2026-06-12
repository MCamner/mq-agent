"""Bridge to mq-mcp for tool routing via MCP protocol."""
from __future__ import annotations

import json
from typing import Any

try:
    import httpx  # noqa: F401
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

MCP_START_HINT = "Start mq-mcp with:\n  mq-agent mcp start"


def _infer_default_tool_source(tool_name: str, fallback: str) -> str:
    """Return the default MCP server for known MQ ecosystem tool families."""
    lower = tool_name.lower()
    if lower == "image_ocr" or lower.startswith(("observe_", "analyze_", "extract_", "reverse_", "compare_")):
        return "mq-image-analyze"
    return fallback


class MCPBridge:
    """Routes tool calls to a running mq-mcp server over HTTP."""

    def __init__(self, endpoint: str = "http://localhost:8765"):
        self.endpoint = endpoint.rstrip("/")
        self._available: list[str] | None = None
        self._contract_specs: dict[str, dict] | None = None

    # ── connectivity ───────────────────────────────────────────────────────

    def is_available(self) -> bool:
        if not _HAS_HTTPX:
            return False
        import httpx
        try:
            response = httpx.get(f"{self.endpoint}/health", timeout=2)
            return response.status_code == 200
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

    def list_tool_specs(self, source: str = "mq-mcp") -> list:
        """Return MCPToolSpec objects for all discovered tools."""
        from .mcp_registry import MCPToolSpec
        raw = self._fetch_tools_raw()
        contracts = self._fetch_contract_specs()
        specs = []
        for item in raw:
            if isinstance(item, dict):
                contract = contracts.get(str(item.get("name", "")), {})
                item = {**contract, **item}
                spec = MCPToolSpec.from_dict(item)
            else:
                name = str(item)
                spec = MCPToolSpec.from_dict({"name": name, **contracts.get(name, {})})
            spec.source = source
            specs.append(spec)
        return specs

    # ── tool description ───────────────────────────────────────────────────

    def _fetch_contract_specs(self) -> dict[str, dict]:
        """Return tool contract entries keyed by name, if the server exposes them."""
        if self._contract_specs is not None:
            return self._contract_specs
        self._contract_specs = {}
        if not _HAS_HTTPX:
            return self._contract_specs
        import httpx
        try:
            response = httpx.get(f"{self.endpoint}/tool-contracts", timeout=5)
            if response.status_code != 200:
                return self._contract_specs
            data = response.json()
            for item in data.get("tools", []):
                if isinstance(item, dict) and item.get("name"):
                    self._contract_specs[str(item["name"])] = item
        except Exception:
            pass
        return self._contract_specs

    def describe_tool(self, name: str) -> Any:
        """Return an MCPToolSpec for a tool using server metadata before name heuristics."""
        from .mcp_registry import MCPToolSpec
        if not _HAS_HTTPX:
            return MCPToolSpec.from_name(name)
        import httpx
        try:
            response = httpx.get(f"{self.endpoint}/tools/{name}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and "name" in data:
                    contract_data = self._fetch_contract_specs().get(name, {})
                    data = {**contract_data, **data}
                    return MCPToolSpec.from_dict(data)
            # 404 or unexpected shape — fall through to name classification
        except Exception:
            pass
        maybe_contract_data = self._fetch_contract_specs().get(name)
        if maybe_contract_data:
            return MCPToolSpec.from_dict(maybe_contract_data)
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
                timeout=120,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            return self.not_reachable_message()
        except httpx.HTTPStatusError as exc:
            return f"mq-mcp error {exc.response.status_code}: {exc.response.text}"
        except Exception as exc:
            return f"MCP bridge error: {exc}"

    # ── review orchestration helpers ───────────────────────────────────────

    def review_file(self, path: str, flags: dict[str, Any]) -> Any:
        return self.call_tool("review_file", {"relative_path": path, **flags})

    def review_diff(self, flags: dict[str, Any]) -> Any:
        return self.call_tool("review_diff", flags)

    def review_repo(self, path: str, flags: dict[str, Any]) -> Any:
        return self.call_tool("review_repo", flags)


class MultiMCPBridge:
    """Aggregates multiple MCP server bridges."""

    def __init__(self):
        from ..core.config import get_mcp_servers
        self.servers = get_mcp_servers()
        self.bridges = {name: MCPBridge(url) for name, url in self.servers.items()}

    def is_available(self) -> bool:
        """Returns True if ANY registered server is reachable."""
        return any(b.is_available() for b in self.bridges.values())

    def list_tool_specs(self) -> list:
        """Aggregate tool specs from all bridges."""
        all_specs = []
        for name, bridge in self.bridges.items():
            all_specs.extend(bridge.list_tool_specs(source=name))
        return all_specs

    def describe_tool(self, name: str) -> Any:
        """Find and describe a tool from any bridge."""
        from .mcp_registry import MCPSafetyClass

        for server_name, bridge in self.bridges.items():
            tools = bridge.list_tools()
            if name in tools:
                spec = bridge.describe_tool(name)
                spec.source = server_name
                return spec

        for server_name, bridge in self.bridges.items():
            spec = bridge.describe_tool(name)
            if spec.safety_class != MCPSafetyClass.UNKNOWN:
                spec.source = _infer_default_tool_source(name, server_name)
                return spec
        # Fallback to default classification
        from .mcp_registry import MCPToolSpec
        spec = MCPToolSpec.from_name(name)
        spec.source = _infer_default_tool_source(name, spec.source)
        return spec

    def call_tool(self, tool_name: str, args: dict) -> Any:
        """Route tool call to the first bridge that has the tool."""
        for name, bridge in self.bridges.items():
            if tool_name in bridge.list_tools():
                return bridge.call_tool(tool_name, args)
        return f"Tool '{tool_name}' not found on any connected MCP server."

    def _call_required_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Call a named MCP tool, returning a clear error when it is missing."""
        for name, bridge in self.bridges.items():
            tools = bridge.list_tools()
            if tool_name in tools:
                return bridge.call_tool(tool_name, args)
        return {
            "ok": False,
            "error": f"mq-mcp tool '{tool_name}' is not available.",
            "tool": tool_name,
            "hint": "Start or upgrade mq-mcp, then run mq-agent mcp tools.",
        }

    def _select_review_tool(self, base_tool: str, risk_tool: str, risk: bool) -> str | dict[str, Any]:
        if not risk:
            return base_tool
        for bridge in self.bridges.values():
            if risk_tool in bridge.list_tools():
                return risk_tool
        return {
            "ok": False,
            "error": f"--risk requires mq-mcp tool '{risk_tool}', but it is not available.",
            "tool": risk_tool,
            "hint": "Upgrade mq-mcp to a version that exposes risk review tools.",
        }

    def review_file(self, path: str, flags: dict[str, Any]) -> Any:
        selected = self._select_review_tool("review_file", "risk_review_file", bool(flags.get("risk")))
        if isinstance(selected, dict):
            return selected
        return self._call_required_tool(selected, {"relative_path": path, **flags})

    def review_diff(self, flags: dict[str, Any]) -> Any:
        selected = self._select_review_tool("review_diff", "risk_review_diff", bool(flags.get("risk")))
        if isinstance(selected, dict):
            return selected
        return self._call_required_tool(selected, flags)

    def review_repo(self, path: str, flags: dict[str, Any]) -> Any:
        selected = self._select_review_tool("review_repo", "risk_review_repo", bool(flags.get("risk")))
        if isinstance(selected, dict):
            return selected
        return self._call_required_tool(selected, flags)

    def search_semantic_memory(self, query: str) -> Any:
        """Search mq-mcp semantic memory (requires mq-mcp v1.4.0+)."""
        return self._call_required_tool("search_semantic_memory", {"query": query})

    def store_semantic_memory(self, key: str, value: str) -> Any:
        """Store an item in mq-mcp semantic memory. Class C write tool — requires approval."""
        return self._call_required_tool("store_semantic_memory", {"key": key, "value": value})

    def list_architecture_decisions(self) -> Any:
        """List architecture decisions from mq-mcp. Returns None when tool not available."""
        return self._call_optional_tool("list_architecture_decisions", {})

    def get_architecture_decision(self, decision_id: str) -> Any:
        """Fetch a single architecture decision by ID."""
        return self._call_required_tool("get_architecture_decision", {"id": decision_id})

    def learn_status(self) -> Any:
        """Check availability of the mq-mcp learn system."""
        return self._call_required_tool("learn_status", {})

    def search_learned_patterns(self, query: str) -> Any:
        """Search learned review patterns stored in mq-mcp."""
        return self._call_required_tool("search_learned_patterns", {"query": query})

    def explain_learned_pattern(self, pattern_id: str) -> Any:
        """Fetch a detailed explanation of a learned pattern by ID."""
        return self._call_required_tool("explain_learned_pattern", {"id": pattern_id})

    def learn_extract_from_last_review(self, relative_path: str) -> Any:
        """Dry-run extraction of a learn candidate from the last review for a file."""
        return self._call_required_tool(
            "learn_extract_from_last_review",
            {"relative_path": relative_path},
        )

    def learn_record(self, relative_path: str) -> Any:
        """Store the extracted learn candidate for a file as a learned pattern (Class C write)."""
        return self._call_required_tool("record_learning", {"relative_path": relative_path})

    def learn_from_review(self, relative_path: str, task: str = "", risk: str = "low") -> Any:
        """Create a learning record from the last review findings for a file (Class C write)."""
        return self._call_required_tool(
            "learn_from_review",
            {"relative_path": relative_path, "task": task, "risk": risk},
        )

    def learn_from_diff(self, task: str, lesson: str, risk: str = "low", validation: str = "") -> Any:
        """Create a learning record with the current git diff as context (Class C write)."""
        return self._call_required_tool(
            "learn_from_diff",
            {"task": task, "lesson": lesson, "risk": risk, "validation": validation},
        )

    def learn_hygiene(self) -> Any:
        """Return a hygiene report for stored learning records."""
        return self._call_optional_tool("learn_hygiene", {})

    def learn_summarize(self, limit: int = 20) -> Any:
        """Return a plain-text summary of stored learning records."""
        return self._call_optional_tool("summarize_learnings", {"limit": limit})

    def ollama_learn_status(self) -> Any:
        """Check whether the local Ollama mq-learn model is available."""
        return self._call_optional_tool("ollama_learn_status", {})

    def _call_optional_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Call a named MCP tool, returning None (not an error) when not available."""
        for bridge in self.bridges.values():
            if tool_name in bridge.list_tools():
                return bridge.call_tool(tool_name, args)
        return None

    def get_server_statuses(self) -> dict[str, dict[str, Any]]:
        """Get reachability, tool counts, and optional enrichment for all servers."""
        status = {}
        for name, bridge in self.bridges.items():
            available = bridge.is_available()
            specs = bridge.list_tool_specs(source=name) if available else []
            entry: dict[str, Any] = {
                "available": available,
                "endpoint": bridge.endpoint,
                "tools": len(specs),
                "specs": specs,
            }
            if available:
                tools = bridge.list_tools()
                if "validate_orchestration_contract" in tools:
                    entry["contract"] = bridge.call_tool("validate_orchestration_contract", {})
                if "list_semantic_memory" in tools:
                    mem = bridge.call_tool("list_semantic_memory", {})
                    if isinstance(mem, list):
                        entry["semantic_memory_count"] = len(mem)
                    elif isinstance(mem, dict) and "items" in mem:
                        entry["semantic_memory_count"] = len(mem["items"])
            status[name] = entry
        return status


_default_bridge = MultiMCPBridge()


def mcp_call(tool_name: str, args_json: str = "{}") -> str:
    """Tool-registry-compatible wrapper for MCP bridge calls."""
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return "Invalid JSON args"
    result = _default_bridge.call_tool(tool_name, args)
    return json.dumps(result) if not isinstance(result, str) else result
