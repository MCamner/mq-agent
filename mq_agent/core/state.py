from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SafetyMode(StrEnum):
    READ_ONLY = "read-only"
    SUGGEST = "suggest"
    EXECUTE = "execute"
    DANGEROUS = "dangerous"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    index: int
    description: str
    tool: str | None = None
    args: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Any | None = None
    error: str | None = None
    verified: bool = False
    verification_note: str = ""


@dataclass
class AgentState:
    goal: str
    safety_mode: SafetyMode = SafetyMode.SUGGEST
    dry_run: bool = False
    json_output: bool = False
    working_dir: str = "."
    plan: list[PlanStep] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    current_step: int = 0

    @property
    def is_complete(self) -> bool:
        return bool(self.plan) and all(
            s.status in (StepStatus.SUCCESS, StepStatus.SKIPPED, StepStatus.FAILED)
            for s in self.plan
        )

    @property
    def has_failures(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.plan)

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.plan if s.status == StepStatus.SUCCESS)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "safety_mode": self.safety_mode.value,
            "dry_run": self.dry_run,
            "working_dir": self.working_dir,
            "steps": [
                {
                    "index": s.index,
                    "description": s.description,
                    "tool": s.tool,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                    "verified": s.verified,
                    "verification_note": s.verification_note,
                }
                for s in self.plan
            ],
            "is_complete": self.is_complete,
            "has_failures": self.has_failures,
        }
