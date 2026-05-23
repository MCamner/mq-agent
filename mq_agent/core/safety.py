from .state import PlanStep, SafetyMode

SAFE_TOOLS = {
    "git_status",
    "git_log",
    "git_diff",
    "git_branch",
    "git_remote",
    "repo_summary",
    "list_files",
    "read_file",
    "find_files",
    "which",
    # repo-signal tools are read-only by definition
    "repo_scan",
    "repo_readme_score",
    "repo_publish_checklist",
    "repo_analyze",
}

DESTRUCTIVE_PATTERNS = [
    "delete",
    "remove",
    "drop",
    "force push",
    "git push",
    "publish",
    "deploy",
    "rm -rf",
    "format",
]


class SafetyGate:
    def __init__(self, mode: SafetyMode):
        self.mode = mode

    def check(self, step: PlanStep) -> tuple[bool, str]:
        """Returns (allowed, reason). If not allowed, executor should skip."""
        if self.mode == SafetyMode.READ_ONLY:
            if step.tool and step.tool not in SAFE_TOOLS:
                return False, f"Tool '{step.tool}' not permitted in read-only mode"
            return True, ""

        if self.mode == SafetyMode.SUGGEST:
            return False, "Suggest mode: showing plan only, not executing"

        if self.mode == SafetyMode.EXECUTE:
            if self._is_destructive(step):
                return False, "Destructive operation requires --approve flag or dangerous mode"
            return True, ""

        if self.mode == SafetyMode.DANGEROUS:
            return True, ""

        return False, f"Unknown safety mode: {self.mode}"

    def _is_destructive(self, step: PlanStep) -> bool:
        desc = step.description.lower()
        return any(pattern in desc for pattern in DESTRUCTIVE_PATTERNS)

    def requires_approval(self, step: PlanStep) -> bool:
        return self._is_destructive(step)

    @property
    def can_execute(self) -> bool:
        return self.mode in (SafetyMode.EXECUTE, SafetyMode.DANGEROUS)
