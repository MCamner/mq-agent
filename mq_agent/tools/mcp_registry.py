"""MCP tool registry — normalizes mq-mcp tools into mq-agent tool specs."""
from __future__ import annotations

from dataclasses import dataclass, field


class MCPSafetyClass:
    READ_ONLY = "read-only"
    WRITE_CAPABLE = "write-capable"
    SUBPROCESS = "subprocess"
    DANGEROUS = "dangerous"
    UNKNOWN = "unknown"


# Longest/most-specific prefixes first so "remove_" wins over a hypothetical "re_"
_PREFIX_MAP: list[tuple[str, str]] = [
    ("read_", MCPSafetyClass.READ_ONLY),
    ("list_", MCPSafetyClass.READ_ONLY),
    ("get_", MCPSafetyClass.READ_ONLY),
    ("search_", MCPSafetyClass.READ_ONLY),
    ("find_", MCPSafetyClass.READ_ONLY),
    ("scan_", MCPSafetyClass.READ_ONLY),
    ("git_", MCPSafetyClass.READ_ONLY),      # git_status, git_diff, git_log
    ("update_", MCPSafetyClass.WRITE_CAPABLE),
    ("write_", MCPSafetyClass.WRITE_CAPABLE),
    ("set_", MCPSafetyClass.WRITE_CAPABLE),
    ("create_", MCPSafetyClass.WRITE_CAPABLE),
    ("edit_", MCPSafetyClass.WRITE_CAPABLE),
    ("new_", MCPSafetyClass.WRITE_CAPABLE),
    ("delete_", MCPSafetyClass.DANGEROUS),
    ("remove_", MCPSafetyClass.DANGEROUS),
    ("run_", MCPSafetyClass.SUBPROCESS),
    ("validate_", MCPSafetyClass.SUBPROCESS),
    ("execute_", MCPSafetyClass.SUBPROCESS),
    ("invoke_", MCPSafetyClass.SUBPROCESS),
    ("open_", MCPSafetyClass.SUBPROCESS),
    ("launch_", MCPSafetyClass.SUBPROCESS),
]


def normalize_safety_class(value: object) -> str:
    """Normalize mq-mcp safety metadata into mq-agent's safety labels."""
    normalized = str(value or "").strip().lower()
    return {
        "a": MCPSafetyClass.READ_ONLY,
        "b": MCPSafetyClass.READ_ONLY,
        "c": MCPSafetyClass.WRITE_CAPABLE,
        "d": MCPSafetyClass.SUBPROCESS,
        MCPSafetyClass.READ_ONLY: MCPSafetyClass.READ_ONLY,
        MCPSafetyClass.WRITE_CAPABLE: MCPSafetyClass.WRITE_CAPABLE,
        MCPSafetyClass.SUBPROCESS: MCPSafetyClass.SUBPROCESS,
        MCPSafetyClass.DANGEROUS: MCPSafetyClass.DANGEROUS,
        MCPSafetyClass.UNKNOWN: MCPSafetyClass.UNKNOWN,
    }.get(normalized, "")


def classify_tool_name(name: str) -> str:
    """Return safety class inferred from tool name prefix."""
    lower = name.lower()
    for prefix, cls in _PREFIX_MAP:
        if lower.startswith(prefix):
            return cls
    return MCPSafetyClass.UNKNOWN


@dataclass
class MCPToolSpec:
    name: str
    description: str = ""
    safety_class: str = MCPSafetyClass.UNKNOWN
    read_only: bool = False
    write_capable: bool = False
    subprocess: bool = False
    dangerous: bool = False
    input_schema: dict = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    source: str = "mq-mcp"

    @classmethod
    def from_name(cls, name: str, description: str = "") -> MCPToolSpec:
        safety = classify_tool_name(name)
        return cls(
            name=name,
            description=description,
            safety_class=safety,
            read_only=(safety == MCPSafetyClass.READ_ONLY),
            write_capable=(safety == MCPSafetyClass.WRITE_CAPABLE),
            subprocess=(safety == MCPSafetyClass.SUBPROCESS),
            dangerous=(safety == MCPSafetyClass.DANGEROUS),
        )

    @classmethod
    def from_dict(cls, data: dict) -> MCPToolSpec:
        name = data.get("name", "")
        safety = (
            normalize_safety_class(data.get("safety_class"))
            or normalize_safety_class(data.get("class"))
            or classify_tool_name(name)
        )
        return cls(
            name=name,
            description=data.get("description", ""),
            safety_class=safety,
            read_only=(safety == MCPSafetyClass.READ_ONLY),
            write_capable=(safety == MCPSafetyClass.WRITE_CAPABLE),
            subprocess=(safety == MCPSafetyClass.SUBPROCESS),
            dangerous=(safety == MCPSafetyClass.DANGEROUS),
            input_schema=data.get("input_schema", {}),
            examples=data.get("examples", []),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "safety_class": self.safety_class,
            "read_only": self.read_only,
            "write_capable": self.write_capable,
            "subprocess": self.subprocess,
            "dangerous": self.dangerous,
            "input_schema": self.input_schema,
            "examples": self.examples,
            "source": self.source,
        }
