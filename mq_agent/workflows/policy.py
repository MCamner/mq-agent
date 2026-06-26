"""Tool-policy provider for the workflow runner (Phase 6).

Fetches machine-readable tool policy from mq-mcp (`GET /tool-policies`, the
Phase 5 endpoint) so the runner no longer relies on a hardcoded allowlist to
decide what may run. Key properties:

  * **Fetched, not hardcoded** — the primary source is mq-mcp's live policy.
  * **Safe fallback** — if the policy fetch fails or returns garbage, the
    provider falls back to the static read-only allowlist (templates.ALLOWED_TOOLS)
    so execution is never bricked, only constrained.
  * **Observable** — every decision carries a reason and a source
    (``policy`` vs ``fallback``) so it is obvious why a tool was allowed/denied.

The fetcher is injectable so the runner is testable without a live mq-mcp.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import FORBIDDEN_TOOLS, WorkflowStep
from .templates import ALLOWED_TOOLS

SOURCE_POLICY = "policy"
SOURCE_FALLBACK = "fallback"

APPROVAL_NONE = "none"
APPROVAL_PLAN = "plan"
APPROVAL_STEP = "step"
APPROVAL_FORBIDDEN = "forbidden"

#: Policy fetcher: returns a list of policy dicts (one per tool) or raises.
Fetcher = Callable[[], list[dict[str, Any]]]


@dataclass(frozen=True)
class PolicyDecision:
    """Outcome of evaluating one step against tool policy."""

    tool: str
    allowed: bool
    approval: str
    reason: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "allowed": self.allowed,
            "approval": self.approval,
            "reason": self.reason,
            "source": self.source,
        }


def _default_fetcher() -> list[dict[str, Any]]:
    """Fetch tool policies from the local mq-mcp `/tool-policies` route."""
    import httpx

    from ..tools.mcp_bridge import MCPBridge

    endpoint = MCPBridge().endpoint
    response = httpx.get(f"{endpoint}/tool-policies", timeout=5)
    response.raise_for_status()
    data = response.json()
    tools = data["tools"]  # KeyError on a malformed response -> triggers fallback
    if not isinstance(tools, list):
        raise ValueError("malformed /tool-policies response: 'tools' is not a list")
    return tools


class PolicyProvider:
    """Loads tool policy with a safe static fallback."""

    def __init__(
        self,
        fetcher: Fetcher | None = None,
        *,
        fallback_tools: frozenset[str] | None = None,
    ) -> None:
        self._fetcher = fetcher or _default_fetcher
        self._fallback_tools = fallback_tools or ALLOWED_TOOLS
        self._policies: dict[str, dict[str, Any]] | None = None
        self.source: str = SOURCE_POLICY
        self.error: str | None = None

    def load(self) -> dict[str, dict[str, Any]]:
        """Fetch and cache policies; fall back to the static allowlist on error."""
        try:
            raw = self._fetcher()
            policies = {p["name"]: p for p in raw}
            if not policies:
                raise ValueError("empty policy set")
            self._policies = policies
            self.source = SOURCE_POLICY
            self.error = None
        except Exception as exc:  # noqa: BLE001 - any failure → safe fallback
            self._policies = None
            self.source = SOURCE_FALLBACK
            self.error = str(exc)
        return self._policies or {}

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return the loaded policy map (empty when running on fallback)."""
        return dict(self._policies) if self._policies else {}

    def decide(self, step: WorkflowStep, *, read_only: bool = True) -> PolicyDecision:
        """Decide whether ``step`` may run, and at what approval level."""
        tool = step.tool

        if self._policies is None:
            return self._decide_fallback(tool)

        policy = self._policies.get(tool)
        if policy is None:
            return PolicyDecision(
                tool, False, APPROVAL_FORBIDDEN,
                "no policy for tool (unknown tool or contract drift)", SOURCE_POLICY,
            )
        if not policy.get("workflow_allowed", False):
            return PolicyDecision(
                tool, False, policy.get("approval", APPROVAL_FORBIDDEN),
                "tool is not workflow_allowed", SOURCE_POLICY,
            )
        approval = policy.get("approval", APPROVAL_FORBIDDEN)
        if approval == APPROVAL_FORBIDDEN:
            return PolicyDecision(
                tool, False, approval, "approval is forbidden", SOURCE_POLICY
            )
        if read_only and (policy.get("write") or approval == APPROVAL_STEP):
            return PolicyDecision(
                tool, False, approval,
                "mutation not allowed in read-only runner", SOURCE_POLICY,
            )
        return PolicyDecision(tool, True, approval, "allowed by policy", SOURCE_POLICY)

    def retry_safe(self, tool: str) -> bool:
        """Whether a tool is safe to re-run. Conservative when unknown."""
        if self._policies is None:
            return tool in self._fallback_tools  # static allowlist is read-only
        policy = self._policies.get(tool)
        return bool(policy and policy.get("retry_safe", False))

    def _decide_fallback(self, tool: str) -> PolicyDecision:
        if tool in FORBIDDEN_TOOLS:
            return PolicyDecision(
                tool, False, APPROVAL_FORBIDDEN, "tool is forbidden", SOURCE_FALLBACK
            )
        if tool in self._fallback_tools:
            # The static allowlist is read-only; require plan approval to be safe.
            return PolicyDecision(
                tool, True, APPROVAL_PLAN,
                "allowed by static fallback allowlist (policy unavailable)",
                SOURCE_FALLBACK,
            )
        return PolicyDecision(
            tool, False, APPROVAL_FORBIDDEN,
            "policy unavailable and tool not in fallback allowlist", SOURCE_FALLBACK,
        )


def diff_policies(
    snapshot: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    tools: set[str],
) -> list[str]:
    """Return tools whose policy materially changed between snapshot and current.

    Only flags tools present (with a policy) in both maps — a tool that merely
    became unavailable (fallback) is handled by the runner, not treated as drift.
    """
    changed: list[str] = []
    for tool in sorted(tools):
        snap = snapshot.get(tool)
        cur = current.get(tool)
        if snap and cur and snap != cur:
            changed.append(tool)
    return changed
