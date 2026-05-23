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

    def audit(self, path: str = ".") -> dict:
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

        return {
            "steps": [
                {
                    "description": s.description,
                    "status": s.status.value,
                    "result": s.result,
                }
                for s in state.plan
            ],
            "verification": verification,
        }
