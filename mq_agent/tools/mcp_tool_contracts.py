"""MCP tool contract checking: what mq-agent calls against what producers publish.

The consumer side is `schemas/mcp_tool_requirements.json`, packaged with
mq-agent and held to the code by tests/test_mcp_tool_requirements.py. The
producer side is each producer's committed `contracts/tool_surface.v1.json`
(`mq-mcp.tool-surface.v1`). Both are files: a running server can lag `main`,
so it is never the source of truth here.

Severity follows the rest of the compatibility gate. A producer with no
published surface is SKIPPED: nothing to assess, and it must not lift a clean
stack to a non-zero exit. A surface that exists but is invalid is the
producer's defect and FAILs. Unknown is never incompatible.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

CONSUMER = "mq-agent"
SURFACE_CONTRACT = "mq-mcp.tool-surface.v1"
SURFACE_FILE = Path("contracts") / "tool_surface.v1.json"
SURFACE_SCHEMA_FILE = Path("contracts") / "tool_surface.v1.schema.json"
REQUIREMENTS_FILE = "mcp_tool_requirements.json"

_CLASS_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}


def _packaged(name: str) -> Path:
    packaged = Path(__file__).resolve().parents[1] / "schemas" / name
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[2] / "schemas" / name


def load_requirements() -> dict[str, Any]:
    """The tools mq-agent calls, as declared in the packaged manifest."""
    return json.loads(_packaged(REQUIREMENTS_FILE).read_text(encoding="utf-8"))


def _finding(
    code: str, severity: str, producer: str, message: str, evidence: str | None = None
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "repo": CONSUMER,
        "repos": sorted({CONSUMER, producer}),
        "message": message,
        "blocks_release": severity == "FAIL",
    }
    if evidence is not None:
        finding["evidence"] = [
            {"repo": producer, "file": SURFACE_FILE.as_posix(), "field": "tools", "observed": evidence}
        ]
    return finding


def _load_surface(root: Path) -> tuple[dict[str, Any] | None, str]:
    """(surface, "") when valid; (None, reason) when absent or invalid.

    An absent file returns reason "" too, which the caller reads as SKIPPED.
    """
    path = root / SURFACE_FILE
    if not path.is_file():
        return None, ""
    try:
        surface = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads((root / SURFACE_SCHEMA_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable: {exc.__class__.__name__}"
    errors = sorted(Draft202012Validator(schema).iter_errors(surface), key=lambda e: list(e.path))
    if errors:
        return None, f"invalid against its schema: {errors[0].message}"
    return surface, ""


def _check_tool(producer: str, need: dict[str, Any], tool: dict[str, Any] | None) -> list[dict[str, Any]]:
    name = need["name"]
    if tool is None:
        severity = "WARN" if need.get("optional_tool") else "FAIL"
        return [
            _finding(
                "MQC019_TOOL_NOT_PRODUCED",
                severity,
                producer,
                f"mq-agent calls {name!r} but {producer} does not register it",
                evidence=name,
            )
        ]

    findings: list[dict[str, Any]] = []
    declared_class, ceiling = tool["safety_class"], need["max_safety_class"]
    if _CLASS_RANK[declared_class] > _CLASS_RANK[ceiling]:
        findings.append(
            _finding(
                "MQC020_TOOL_SAFETY_ESCALATED",
                "FAIL",
                producer,
                f"{producer} declares {name!r} class {declared_class}; mq-agent calls it "
                f"expecting at most class {ceiling}",
                evidence=f"{name}.safety_class={declared_class}",
            )
        )

    params = {p["name"]: p for p in tool["parameters"]}
    for arg, severity in [(a, "FAIL") for a in need.get("arguments", [])] + [
        (a, "WARN") for a in need.get("optional_arguments", [])
    ]:
        if arg not in params:
            findings.append(
                _finding(
                    "MQC021_TOOL_ARGUMENT_UNDECLARED",
                    severity,
                    producer,
                    f"mq-agent sends {arg!r} to {name!r}, which {producer} does not accept",
                    evidence=f"{name}.parameters",
                )
            )

    sent = set(need.get("arguments", [])) | set(need.get("optional_arguments", [])) | set(
        need.get("context_arguments", [])
    )
    for param in sorted(p for p, spec in params.items() if spec["required"] and p not in sent):
        findings.append(
            _finding(
                "MQC022_TOOL_REQUIRED_ARGUMENT_UNSENT",
                "FAIL",
                producer,
                f"{producer} requires {param!r} for {name!r}, which mq-agent never sends",
                evidence=f"{name}.parameters.{param}",
            )
        )
    return findings


def tool_contract_findings(
    producer_roots: dict[str, Path], requirements: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Relationships and findings for every inventoried producer mq-agent calls.

    `producer_roots` maps a repository name to its checkout. A producer that is
    not in it was not inventoried, and nothing is said about it.
    """
    requirements = requirements if requirements is not None else load_requirements()
    by_producer: dict[str, list[dict[str, Any]]] = {}
    for need in requirements.get("tools", []):
        by_producer.setdefault(need["producer"], []).append(need)

    relationships: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for producer in sorted(by_producer):
        root = producer_roots.get(producer)
        if root is None:
            continue
        needs = by_producer[producer]
        surface, problem = _load_surface(root)
        if surface is None:
            severity = "FAIL" if problem else "SKIPPED"
            message = (
                f"{producer} publishes {SURFACE_FILE.as_posix()} but it is {problem}"
                if problem
                else f"{producer} publishes no {SURFACE_CONTRACT}; the {len(needs)} tools "
                "mq-agent calls there cannot be checked"
            )
            findings.append(_finding("MQC023_TOOL_SURFACE_UNAVAILABLE", severity, producer, message))
            relationships.append(
                {
                    "producer": producer,
                    "consumer": CONSUMER,
                    "subject": SURFACE_CONTRACT,
                    "status": severity,
                    "overlap": None,
                    "detail": message,
                }
            )
            continue

        tools = {t["name"]: t for t in surface["tools"]}
        pair: list[dict[str, Any]] = []
        for need in needs:
            pair.extend(_check_tool(producer, need, tools.get(need["name"])))
        findings.extend(pair)
        relationships.append(
            {
                "producer": producer,
                "consumer": CONSUMER,
                "subject": SURFACE_CONTRACT,
                "status": max(
                    [f["severity"] for f in pair] or ["PASS"],
                    key=lambda s: {"PASS": 0, "WARN": 1, "FAIL": 2}[s],
                ),
                "overlap": None,
                "detail": f"{len(needs)} tools mq-agent calls checked against "
                f"{producer}'s published surface",
            }
        )
    return relationships, findings


# --- optional live comparison (--live) ----------------------------------------

LIVE_DRIFT = "MQC024_TOOL_SURFACE_LIVE_DRIFT"
_LIVE_LABEL = {"A": "read-only", "B": "read-only", "C": "write-capable", "D": "subprocess"}
_LIVE_EXAMPLES = 5


def fetch_json(url: str) -> Any:
    """GET a JSON document, or None when the server does not answer with one."""
    try:
        import httpx

        response = httpx.get(url, timeout=5)
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None


def _checkout_commit(root: Path) -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _shape_committed(tool: dict[str, Any]) -> tuple[str, dict[str, bool]]:
    return tool["safety_class"], {p["name"]: p["required"] for p in tool["parameters"]}


def _shape_live(tool: dict[str, Any]) -> tuple[str, dict[str, bool]]:
    """The class as the server states it, and its parameters.

    mq-image-analyze sends the ADR-003 letter as `class`; mq-mcp sends a
    `safety_class` label. A letter is kept as a letter, because A and B share
    the label read-only and an A -> B change would vanish in the label.
    """
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required") or [])
    letter = str(tool.get("class") or "")
    stated = letter if letter in _LIVE_LABEL else str(tool.get("safety_class") or "")
    return stated, {name: name in required for name in schema.get("properties") or {}}


def _class_differs(stated: str, committed_letter: str) -> bool:
    if not stated:
        return False
    if stated in _LIVE_LABEL:
        return stated != committed_letter
    return stated != _LIVE_LABEL[committed_letter]


def _sample(names: list[str]) -> str:
    shown = ", ".join(names[:_LIVE_EXAMPLES])
    return shown + (f" (+{len(names) - _LIVE_EXAMPLES} more)" if len(names) > _LIVE_EXAMPLES else "")


def live_surface_findings(
    producer_roots: dict[str, Path],
    endpoints: dict[str, str],
    fetch: Any = fetch_json,
) -> list[dict[str, Any]]:
    """MQC024 for each producer whose running server differs from its committed surface.

    Optional evidence, never a gate: drift is WARN, a server that does not
    answer is UNAVAILABLE, and neither blocks a release. Only producers with a
    valid committed surface and a known endpoint are compared.
    """
    findings: list[dict[str, Any]] = []
    for producer in sorted(producer_roots):
        url = endpoints.get(producer)
        surface, _problem = _load_surface(producer_roots[producer])
        if not url or surface is None:
            continue
        listing = fetch(f"{url.rstrip('/')}/tools")
        if not isinstance(listing, dict) or not isinstance(listing.get("tools"), list):
            findings.append(
                _finding(
                    LIVE_DRIFT, "UNAVAILABLE", producer,
                    f"{producer} is not answering at {url}; its running tool surface was not compared",
                )
            )
            continue
        identity = fetch(f"{url.rstrip('/')}/runtime-identity")
        live_commit = str((identity or {}).get("commit") or "unknown") if isinstance(identity, dict) else "unknown"

        committed = {t["name"]: _shape_committed(t) for t in surface["tools"]}
        live = {str(t.get("name")): _shape_live(t) for t in listing["tools"] if isinstance(t, dict)}
        not_running = sorted(set(committed) - set(live))
        not_committed = sorted(set(live) - set(committed))
        shared = sorted(set(committed) & set(live))
        class_drift = [n for n in shared if _class_differs(live[n][0], committed[n][0])]
        param_drift = [n for n in shared if live[n][1] != committed[n][1]]
        if not (not_running or not_committed or class_drift or param_drift):
            continue

        parts = [
            f"{label}: {_sample(names)}"
            for label, names in (
                ("not running", not_running),
                ("running but not committed", not_committed),
                ("class differs", class_drift),
                ("parameters differ", param_drift),
            )
            if names
        ]
        committed_commit = _checkout_commit(producer_roots[producer]) or "unknown"
        findings.append(
            _finding(
                LIVE_DRIFT, "WARN", producer,
                f"{producer} running at {live_commit[:12]} differs from its committed surface "
                f"at {committed_commit[:12]}: " + "; ".join(parts) + ". Restart it from the checkout.",
                evidence=f"live commit {live_commit}, committed checkout {committed_commit}",
            )
        )
    return findings
