from openai import OpenAI

from ..core.executor import Executor
from ..core.planner import Planner
from ..core.safety import SafetyGate
from ..core.state import AgentState, SafetyMode
from ..core.verification import Verifier
from ..tools import TOOL_REGISTRY
from ..tools.shell_tools import run_command


class CIAgent:
    """Diagnoses CI failures and proposes fixes. Requires --approve to apply fixes."""

    def __init__(self, client: OpenAI):
        self.client = client
        self.planner = Planner(client)
        self.verifier = Verifier(client)

    def diagnose(self, path: str = ".", dry_run: bool = True, approve: bool = False) -> dict:
        # Collect CI context first
        test_output = _safe_run("pytest --tb=short -q 2>&1 | head -80", path)
        lint_output = _safe_run("ruff check . 2>&1 | head -40", path)
        type_output = _safe_run("mypy . --ignore-missing-imports 2>&1 | head -40", path)

        mode = SafetyMode.EXECUTE if approve else SafetyMode.SUGGEST

        state = AgentState(
            goal="Diagnose CI failures and suggest fixes. "
                 "Analyse test output, linting errors, and type errors. "
                 "Propose specific fixes for each failure.",
            safety_mode=mode,
            dry_run=dry_run,
            working_dir=path,
            context={
                "test_output": test_output,
                "lint_output": lint_output,
                "type_output": type_output,
            },
        )

        tools_allowed = [
            "git_status", "git_diff", "read_file", "find_files",
            "run_command", "list_files",
        ]

        state.plan = self.planner.create_plan(state, tools_allowed)

        safety = SafetyGate(mode)
        executor = Executor(safety, TOOL_REGISTRY, dry_run=dry_run)
        executor.run_plan(state)

        verification = self.verifier.verify_plan(state.plan)

        return {
            "ci_context": {
                "tests": test_output,
                "lint": lint_output,
                "types": type_output,
            },
            "mode": mode.value,
            "plan": [s.description for s in state.plan],
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


def _safe_run(command: str, cwd: str) -> str:
    try:
        return run_command(command, cwd=cwd, timeout=30)
    except Exception as exc:
        return f"(could not run: {exc})"
