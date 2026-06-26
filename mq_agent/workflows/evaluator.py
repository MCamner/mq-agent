"""Tool-result normalization (Phase 4).

Raw tool output must not become workflow truth. ``normalize_result`` maps an
arbitrary tool result (or a timeout/exception) onto the bounded, sanitized
shape the workflow state records::

    {"ok": bool, "summary": str, "code": str, "data": dict}

``code`` is one of: PASS, FAIL, TIMEOUT, ERROR, DONE.
Only a bounded, secret-sanitized subset of the raw output is kept under ``data``.
"""
from __future__ import annotations

import re
from typing import Any

from .state import sanitize_result

_PASS_WORDS = {"pass", "passed", "ok", "success", "succeeded", "green"}
_FAIL_WORDS = {"fail", "failed", "error", "errored", "red"}
_MAX_SUMMARY_LEN = 280
_MAX_TEXT_LEN = 2000
#: mq-mcp tools embed their exit status as a leading "[exit N ...]" marker.
_EXIT_RE = re.compile(r"\[exit\s+(\d+)")


def _extract_mcp_text(raw: list) -> str:
    """Concatenate text from (possibly nested) MCP content blocks."""
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str):
                texts.append(text)

    walk(raw)
    return "\n".join(texts).strip()


def _normalize_text(text: str) -> dict[str, Any]:
    """Derive ok/summary/code from free-text tool output."""
    if not text:
        return {"ok": True, "summary": "(no output)", "code": "DONE", "data": {}}
    match = _EXIT_RE.search(text)
    if match is not None:
        ok = match.group(1) == "0"
    else:
        low = text.lower()
        ok = not any(w in low for w in _FAIL_WORDS)
    summary = text.splitlines()[0][:_MAX_SUMMARY_LEN]
    return {
        "ok": ok,
        "summary": summary,
        "code": "PASS" if ok else "FAIL",
        "data": {"text": text[:_MAX_TEXT_LEN]},
    }


def _coerce_summary(raw: dict[str, Any], fallback: str) -> str:
    for key in ("summary", "message", "detail", "title"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:_MAX_SUMMARY_LEN]
    return fallback


def normalize_result(
    raw: Any,
    *,
    timed_out: bool = False,
    error: BaseException | None = None,
) -> dict[str, Any]:
    """Normalize a raw tool result (or failure) into the workflow result shape."""
    if timed_out:
        return {"ok": False, "summary": "step timed out", "code": "TIMEOUT", "data": {}}
    if error is not None:
        return {
            "ok": False,
            "summary": f"tool raised: {error}"[:_MAX_SUMMARY_LEN],
            "code": "ERROR",
            "data": {},
        }

    # mq-mcp's bridge returns a plain string on transport/HTTP errors.
    if isinstance(raw, str):
        return {
            "ok": False,
            "summary": raw[:_MAX_SUMMARY_LEN],
            "code": "ERROR",
            "data": {},
        }

    # mq-mcp tool results arrive as MCP content blocks (possibly nested lists).
    if isinstance(raw, list):
        return _normalize_text(_extract_mcp_text(raw))

    if not isinstance(raw, dict):
        return {
            "ok": True,
            "summary": str(raw)[:_MAX_SUMMARY_LEN],
            "code": "DONE",
            "data": {},
        }

    data = sanitize_result(raw)

    ok: bool
    if isinstance(raw.get("ok"), bool):
        ok = raw["ok"]
    elif "error" in raw and raw["error"]:
        ok = False
    elif raw.get("returncode") == 0 or raw.get("exit_code") == 0:
        ok = True
    elif raw.get("returncode") not in (None, 0) or raw.get("exit_code") not in (None, 0):
        ok = False
    else:
        status_word = str(raw.get("status") or raw.get("code") or "").lower()
        if status_word in _PASS_WORDS:
            ok = True
        elif status_word in _FAIL_WORDS:
            ok = False
        else:
            ok = True  # best-effort: a structured result without a failure signal

    code = "PASS" if ok else "FAIL"
    summary = _coerce_summary(raw, "passed" if ok else "failed")
    return {"ok": ok, "summary": summary, "code": code, "data": data}
