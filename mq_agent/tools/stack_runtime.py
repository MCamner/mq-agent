"""Stack runtime orchestration checks for v1.16.0."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from typing import Any


def _step(name: str, ok: bool, detail: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "status": "PASS" if ok else "FAIL",
        "detail": detail,
    }
    entry.update(extra)
    return entry


def _repo_signal_step() -> dict[str, Any]:
    from mq_agent.tools.signal_tools import _not_available_msg, signal_available

    if signal_available():
        return _step("repo-signal", True, "available")
    return _step("repo-signal", False, _not_available_msg(), hint="uv pip install repo-signal")


def _mcp_step(bridge: Any) -> dict[str, Any]:
    if not bridge.is_available():
        return _step("mq-mcp", False, "not reachable", hint="mq-agent mcp start")
    specs = bridge.list_tool_specs()
    names = {spec.name for spec in specs}
    missing = [name for name in ("review_repo", "brain_record_review") if name not in names]
    if missing:
        return _step(
            "mq-mcp",
            False,
            f"reachable, missing tools: {', '.join(missing)}",
            tool_count=len(specs),
            hint="upgrade mq-mcp, then run mq-agent mcp tools",
        )
    return _step("mq-mcp", True, "reachable", tool_count=len(specs))


def _ollama_step(bridge: Any) -> dict[str, Any]:
    status = bridge.ollama_learn_status()
    if isinstance(status, dict):
        ok = bool(status.get("ok", True)) and not status.get("error")
        detail = status.get("detail") or status.get("model") or status.get("status") or "available"
        return _step("ollama", ok, str(detail), payload=status)
    if status is not None:
        return _step("ollama", True, str(status))

    if not shutil.which("ollama"):
        return _step("ollama", False, "ollama CLI not found", hint="install or start Ollama")

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return _step("ollama", False, f"ollama check failed: {exc}")

    if result.returncode == 0:
        return _step("ollama", True, "ollama CLI reachable")
    detail = (result.stderr or result.stdout or "ollama list failed").strip()
    return _step("ollama", False, detail)


def _brain_export_step(write: bool) -> dict[str, Any]:
    from mq_agent.tools.stack_truth import stack_truth_export

    result = stack_truth_export(write=write)
    ok = bool(result.get("markdown")) and bool(result.get("path"))
    written = bool(result.get("written"))
    if written:
        detail = f"written {result.get('path')}"
    elif ok:
        detail = f"dry-run ok — would write {result.get('path')}"
    else:
        detail = "truth note did not render"
    return _step("brain export", ok, detail, written=written, path=result.get("path"))


def _release_step(ci: bool) -> dict[str, Any]:
    from mq_agent.tools.stack_tools import stack_release_check

    data = json.loads(stack_release_check(ci=ci))
    overall = data.get("overall", "UNKNOWN")
    blockers = [
        f"{repo.get('name')}: {blocker}"
        for repo in data.get("repos", [])
        for blocker in repo.get("blockers", [])
    ]
    detail = overall if not blockers else f"{overall} — {blockers[0]}"
    return _step("release", overall == "GO", detail, mode=data.get("mode", "ci" if ci else "local"))


def stack_run(
    *,
    dry_run: bool = False,
    brain: bool = False,
    ci: bool = False,
    approve: bool = False,
) -> str:
    """Run the stack runtime gate and optionally write the brain truth export."""
    from mq_agent.tools.mcp_bridge import MultiMCPBridge

    bridge = MultiMCPBridge()
    write_brain = brain and approve and not dry_run
    steps = [
        _repo_signal_step(),
        _mcp_step(bridge),
        _ollama_step(bridge),
        _brain_export_step(write=write_brain),
        _release_step(ci=ci),
    ]
    failed = [step for step in steps if step["status"] == "FAIL"]
    return json.dumps({
        "overall": "PASS" if not failed else "FAIL",
        "mode": "ci" if ci else "local",
        "dry_run": dry_run,
        "brain": brain,
        "approved": approve,
        "writes_enabled": write_brain,
        "steps": steps,
        "next_action": failed[0].get("hint", failed[0]["detail"]) if failed else "all green",
        "checked_at": datetime.now(UTC).isoformat(),
    }, indent=2, default=str)
