from openai import OpenAI

from ..core.executor import Executor
from ..core.planner import Planner
from ..core.safety import SafetyGate
from ..core.state import AgentState, SafetyMode
from ..core.verification import Verifier
from ..tools import TOOL_REGISTRY

DEFAULT_RELEASE_STEPS = [
    "Run test suite",
    "Validate pyproject.toml / packaging configuration",
    "Verify CHANGELOG.md exists and is updated",
    "Check README.md badges and links",
    "Confirm git working tree is clean",
    "Run publish checklist",
    "Generate release notes summary",
]


class ReleaseAgent:
    """Plans and validates a release. Safe by default — requires --approve for writes."""

    def __init__(self, client: OpenAI):
        self.client = client
        self.planner = Planner(client)
        self.verifier = Verifier(client)

    def create_plan(self, path: str = ".") -> list[str]:
        """Return the static release plan steps."""
        return list(DEFAULT_RELEASE_STEPS)

    def run_check(
        self, path: str = ".", dry_run: bool = True, approve: bool = False
    ) -> dict:
        mode = SafetyMode.EXECUTE if approve else SafetyMode.SUGGEST

        state = AgentState(
            goal="Validate that the repository is ready for a release. "
                 "Check tests, packaging, changelog, README, and git cleanliness.",
            safety_mode=mode,
            dry_run=dry_run,
            working_dir=path,
        )

        tools_allowed = [
            "git_status", "git_log", "git_diff",
            "repo_summary", "read_file", "list_files",
            "run_command",
        ]

        state.plan = self.planner.create_plan(state, tools_allowed)

        safety = SafetyGate(mode)
        executor = Executor(safety, TOOL_REGISTRY, dry_run=dry_run)
        executor.run_plan(state)

        verification = self.verifier.verify_plan(state.plan)

        return {
            "mode": mode.value,
            "dry_run": dry_run,
            "plan": [s.description for s in state.plan],
            "steps": [
                {
                    "description": s.description,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                }
                for s in state.plan
            ],
            "verification": verification,
            "ready": verification["all_passed"],
        }
