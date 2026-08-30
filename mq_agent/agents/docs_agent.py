from openai import OpenAI

from ..core.executor import Executor
from ..core.planner import Planner
from ..core.safety import SafetyGate
from ..core.state import AgentState, SafetyMode
from ..core.verification import Verifier
from ..tools import TOOL_REGISTRY


class DocsAgent:
    """Audits and summarises repository documentation."""

    def __init__(self, client: OpenAI):
        self.client = client
        self.planner = Planner(client)
        self.verifier = Verifier(client)

    def audit(self, path: str = ".", execution_run_id: str | None = None) -> dict:
        state = AgentState(
            goal="Audit the repository documentation. "
                 "Check README.md, CHANGELOG.md, inline docstrings, and any /docs folder. "
                 "Report gaps and suggest improvements.",
            safety_mode=SafetyMode.READ_ONLY,
            working_dir=path,
        )

        tools_allowed = ["read_file", "list_files", "find_files", "repo_summary"]
        state.plan = self.planner.create_plan(state, tools_allowed)

        safety = SafetyGate(SafetyMode.READ_ONLY)
        executor = Executor(safety, TOOL_REGISTRY, dry_run=False)
        executor.run_plan(state)

        verification = self.verifier.verify_plan(state.plan)

        steps = [
            {
                "description": s.description,
                "status": s.status.value,
                "result": s.result,
            }
            for s in state.plan
        ]

        result: dict = {"steps": steps, "verification": verification}

        # One routing decision inside this execution: who reviews the evidence
        # the read-only steps just gathered. Per ADR-010 D1 the route governs
        # this decision, not the whole audit — the plan, the tool calls and the
        # verification all stay on the canonical path.
        if execution_run_id is not None:
            routed = self._routed_docs_review(steps, execution_run_id, state.safety_mode)
            if routed is not None:
                result["docs_review"] = routed
        return result

    @staticmethod
    def _routed_docs_review(
        steps: list[dict], execution_run_id: str, safety_mode: SafetyMode
    ) -> dict | None:
        """Produce the docs review through the applied route, or not at all.

        There is no cloud implementation of this review to fall back to — it did
        not exist before the route made it possible — so when the route does not
        govern, the audit returns exactly what it always returned. That is why
        `fallbacks` on the execution record stays unmeasured rather than being
        written as `0`: nothing fell back, and nothing counted.
        """
        from ..tools.applied_routing import apply_route
        from ..tools.model_routing import record_route_outcome

        evidence = "\n".join(
            str(step["result"]) for step in steps if step.get("result")
        )
        routed = apply_route(
            "Review the repository documentation for gaps",
            execution_run_id=execution_run_id,
            safety_mode=safety_mode,
            context=evidence or None,
        )
        # The observation is recorded whether or not the route governed. An
        # advisory rejection is evidence about routing behaviour too; it simply
        # is not evidence that a route was applied.
        try:
            record_route_outcome(routed["outcome"])
        except Exception:  # noqa: BLE001 — telemetry never fails a run
            pass

        candidate = routed["candidate"]
        if candidate is None:
            return None
        return {
            "summary": candidate["summary"],
            "suggestions": candidate["suggestions"],
            "route": routed["outcome"]["selected_route"],
            "model": routed["outcome"]["local_model"],
        }
