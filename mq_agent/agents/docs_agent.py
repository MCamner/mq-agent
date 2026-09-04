from pathlib import Path

from openai import OpenAI

from ..core.executor import Executor
from ..core.planner import Planner
from ..core.safety import SafetyGate
from ..core.state import AgentState, SafetyMode, StepStatus
from ..core.verification import Verifier
from ..tools import TOOL_REGISTRY
from ..tools.applied_routing import DEFAULT_ROUTE
from ..tools.material_selection import select_material
from ..tools.repo_tools import find_files


#: The files a documentation audit is always about.
#:
#: Handing these to the planner is the point: a model asked to *find* README.md
#: lists the repository root, and a later step then reads the whole listing
#: while describing itself as reading README. Naming the target removes the
#: ambiguity instead of asking a model to resist it — guidance was tried and
#: measured failing three runs out of three.
KNOWN_DOCS = ("README.md", "CHANGELOG.md")


class DocsAgent:
    """Audits and summarises repository documentation."""

    @staticmethod
    def audit_targets(path: str = ".") -> dict:
        """What this audit is about, resolved before any planning happens.

        `present` are files to read by name. `missing` are gaps to report and
        nothing to read — an audit that quietly omits an absent README hides
        the most basic finding it exists to make. `collections` are the sets
        whose members genuinely are not known in advance, and those are what
        discovery and `for_each` are for.

        Paths are given in the caller's frame, so a plan can use them directly.
        """
        root = Path(path)
        present = [str(root / name) for name in KNOWN_DOCS if (root / name).is_file()]
        missing = [name for name in KNOWN_DOCS if not (root / name).is_file()]
        collections = []
        if (root / "docs").is_dir():
            collections.append(
                {
                    "what": "the documentation folder",
                    "discovery": {
                        "tool": "find_files",
                        "args": {"path": str(root / "docs"), "pattern": "*"},
                    },
                    "min_items": 1,
                }
            )
        # Offered only when the tool that will discover it finds something. A
        # declared target class with no members sends the plan looking for files
        # that are not there, and the audit then reports on a set it never had.
        # `docs/` was already conditional; this was not.
        if find_files(str(root), "*.py"):
            collections.append(
                {
                    "what": "source files, for inline docstrings",
                    "discovery": {
                        "tool": "find_files",
                        "args": {"path": str(root), "pattern": "*.py"},
                    },
                    "min_items": 1,
                }
            )
        return {"present": present, "missing": missing, "collections": collections}

    def __init__(self, client: OpenAI):
        self.client = client
        self.planner = Planner(client)
        self.verifier = Verifier(client)

    def _audit_state(self, path: str) -> AgentState:
        """The task the planner is given, with the targets already resolved."""
        return AgentState(
            goal=(
                "Audit the repository documentation and report gaps and "
                "improvements. context.audit_targets says what to audit: read "
                "each path in `present` directly by name, with no discovery "
                "step; each name in `missing` is a documentation gap to report "
                "and there is nothing to read; each entry in `collections` is a "
                "set whose members are not known in advance — use its declared "
                "discovery.tool and discovery.args exactly, then read the members "
                "with for_each."
            ),
            safety_mode=SafetyMode.READ_ONLY,
            working_dir=path,
            context={"audit_targets": self.audit_targets(path)},
        )

    def audit(
        self,
        path: str = ".",
        execution_run_id: str | None = None,
        route: str = DEFAULT_ROUTE,
    ) -> dict:
        state = self._audit_state(path)

        tools_allowed = ["read_file", "list_files", "find_files", "repo_summary"]
        state.plan = self.planner.create_plan(state, tools_allowed)

        safety = SafetyGate(SafetyMode.READ_ONLY)
        executor = Executor(safety, TOOL_REGISTRY, dry_run=False)
        executor.run_plan(state)

        verification = self.verifier.verify_plan(state.plan)

        steps = [
            {
                "description": s.description,
                "tool": s.tool,
                "args": s.args,
                "for_each": s.for_each,
                "source_item_count": s.source_item_count,
                "executed_call_count": s.executed_call_count,
                "fan_out_complete": s.fan_out_complete,
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
            routed = self._routed_docs_review(
                steps, execution_run_id, state.safety_mode, route
            )
            if routed is not None:
                result["docs_review"] = routed
        return result

    @staticmethod
    def _evidence_material(steps: list[dict]) -> str:
        """The material both routes quote from.

        Successful steps only. A failed step's `result` is an error string, not
        something the audit observed, and quoting it would let a route cite the
        tooling's own failure as a documentation finding. Both routes read this
        same string — comparing two strategies on different material would not
        be comparing them at all.

        Selected down to a budget the route can finish inside. The string this
        returns is both what the model is given and what its citations are
        checked against, so selecting here keeps those two the same document.
        """
        return select_material([
            str(step["result"])
            for step in steps
            if step.get("result") and step.get("status") == StepStatus.SUCCESS.value
        ])

    @staticmethod
    def _routed_docs_review(
        steps: list[dict], execution_run_id: str, safety_mode: SafetyMode, route: str
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

        evidence = DocsAgent._evidence_material(steps)
        routed = apply_route(
            "Review the repository documentation for gaps",
            execution_run_id=execution_run_id,
            safety_mode=safety_mode,
            route=route,
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
