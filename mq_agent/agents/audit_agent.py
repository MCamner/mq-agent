from openai import OpenAI

from ..core.executor import Executor
from ..core.planner import Planner
from ..core.safety import SafetyGate
from ..core.state import AgentState, SafetyMode
from ..core.verification import Verifier
from ..tools import TOOL_REGISTRY
from ..tools.repo_tools import repo_summary


class AuditAgent:
    """Read-only repo audit: gathers context, plans inspection steps, verifies results."""

    def __init__(self, client: OpenAI):
        self.client = client
        self.planner = Planner(client)
        self.verifier = Verifier(client)

    def run(self, path: str = ".", dry_run: bool = False) -> dict:
        from ..core.memory import Memory

        memory = Memory()
        summary = repo_summary(path)

        prior = memory.get(f"audit:{path}")
        extra_context = {"prior_audit": prior} if prior else {}

        state = AgentState(
            goal=f"Perform a thorough audit of the repository at '{path}'. "
                 "Inspect git status, recent commits, file structure, and surface any issues.",
            safety_mode=SafetyMode.READ_ONLY,
            dry_run=dry_run,
            working_dir=path,
            context={"repo_summary": summary, **extra_context},
            memory=memory,
        )

        safety = SafetyGate(SafetyMode.READ_ONLY)
        executor = Executor(safety, TOOL_REGISTRY, dry_run=dry_run)

        read_only_tools = [
            "git_status", "git_log", "git_diff", "git_branch", "git_remote",
            "repo_summary", "list_files", "read_file", "find_files",
        ]

        state.plan = self.planner.create_plan(state, read_only_tools)
        executor.run_plan(state)
        verification = self.verifier.verify_plan(state.plan)

        result = {
            "repo": path,
            "summary": summary,
            "plan": [s.description for s in state.plan],
            "steps": [
                {
                    "description": s.description,
                    "tool": s.tool,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                    "verified": s.verified,
                    "note": s.verification_note,
                }
                for s in state.plan
            ],
            "verification": verification,
            "passed": verification["all_passed"],
        }

        memory.set(f"audit:{path}", {"summary": summary, "passed": result["passed"]}, persistent=True)
        return result
