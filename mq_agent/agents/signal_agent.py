"""
repo-signal integration agent.

Combines repo-signal's static analysis (scan, readme score, publish checklist)
with the AI planner+verifier loop to produce a scored, actionable repo assessment.
"""
from __future__ import annotations

from openai import OpenAI

from ..core.executor import Executor
from ..core.planner import Planner
from ..core.safety import SafetyGate
from ..core.state import AgentState, SafetyMode
from ..core.verification import Verifier
from ..tools import TOOL_REGISTRY
from ..tools.signal_tools import repo_signal_json


class SignalAgent:
    """
    Runs a full repo-signal assessment: static scan + README score +
    publish checklist + AI-generated improvement plan.
    """

    def __init__(self, client: OpenAI):
        self.client = client
        self.planner = Planner(client)
        self.verifier = Verifier(client)

    def run(self, path: str = ".", dry_run: bool = False) -> dict:
        # Always run the static signal pass first — no AI needed
        signal = repo_signal_json(path)

        if not signal["available"]:
            return {
                "available": False,
                "error": signal["error"],
                "path": path,
            }

        readme = signal["readme_score"]
        checklist = signal["publish_checklist"]

        # Score: combine readme (0-100) and publish checklist (0-total)
        readme_pct = readme["score"]
        checklist_pct = round(checklist["score"] / checklist["total"] * 100) if checklist["total"] else 0
        overall = round((readme_pct + checklist_pct) / 2)

        # AI planning pass: use signal data as context to generate improvement steps
        state = AgentState(
            goal=(
                f"Analyse the repository '{signal['name']}' using repo-signal data. "
                f"README score is {readme['score']}/100 (missing: {readme['missing']}). "
                f"Publish checklist is {checklist['score']}/{checklist['total']} ({checklist['status']}). "
                f"Focus areas: {signal['focus_areas']}. "
                "Generate specific, actionable improvement steps using the available tools."
            ),
            safety_mode=SafetyMode.READ_ONLY,
            dry_run=dry_run,
            working_dir=path,
            context={
                "signal": signal,
                "readme_score": readme["score"],
                "readme_missing": readme["missing"],
                "publish_score": f"{checklist['score']}/{checklist['total']}",
                "focus_areas": signal["focus_areas"],
            },
        )

        signal_tools = [
            "repo_scan", "repo_readme_score", "repo_publish_checklist",
            "repo_analyze", "git_status", "git_log", "read_file",
        ]

        state.plan = self.planner.create_plan(state, signal_tools)

        safety = SafetyGate(SafetyMode.READ_ONLY)
        executor = Executor(safety, TOOL_REGISTRY, dry_run=dry_run)
        executor.run_plan(state)

        verification = self.verifier.verify_plan(state.plan)

        return {
            "available": True,
            "path": path,
            "repo": signal["name"],
            "project_type": signal["project_type"],
            "scores": {
                "readme": readme["score"],
                "readme_max": readme["max_score"],
                "publish": checklist["score"],
                "publish_total": checklist["total"],
                "overall": overall,
            },
            "readme": {
                "present": readme["present"],
                "missing": readme["missing"],
            },
            "publish": {
                "status": checklist["status"],
                "next_action": checklist.get("next_action", ""),
            },
            "signal": signal,
            "focus_areas": signal["focus_areas"],
            "steps": [
                {
                    "description": s.description,
                    "tool": s.tool,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                }
                for s in state.plan
            ],
            "verification": verification,
        }
