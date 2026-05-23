import json
import os
from pathlib import Path

from openai import OpenAI

from .state import PlanStep, StepStatus

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "verifier.md"

_DEFAULT_MODEL = "gpt-4o-mini"

_FALLBACK_SYSTEM = """\
You are a verification agent. Determine whether a step completed successfully.
Be strict: errors, empty output where content was expected, and exceptions mean failure.
Return JSON: {"success": true/false, "reason": "brief explanation", "issues": []}
"""


class Verifier:
    """Uses OpenAI to verify whether each step's output indicates success."""

    def __init__(self, client: OpenAI):
        self.client = client
        self._model = os.environ.get("MQ_AGENT_VERIFIER_MODEL", _DEFAULT_MODEL)
        self._system_prompt = (
            PROMPT_PATH.read_text() if PROMPT_PATH.exists() else _FALLBACK_SYSTEM
        )

    def verify(self, step: PlanStep) -> tuple[bool, str]:
        if step.status == StepStatus.FAILED:
            return False, step.error or "Step failed with no error message"

        if step.status == StepStatus.SKIPPED:
            return True, step.result or "Step skipped"

        if step.status == StepStatus.PENDING:
            return False, "Step never ran"

        response = self.client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "step": step.description,
                            "tool": step.tool,
                            "result": str(step.result)[:4000],
                        }
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        data = json.loads(response.choices[0].message.content or "{}")
        success = bool(data.get("success", True))
        reason = data.get("reason", "")

        step.verified = success
        step.verification_note = reason
        return success, reason

    def verify_plan(self, steps: list[PlanStep]) -> dict:
        results = []
        for step in steps:
            ok, note = self.verify(step)
            results.append({"step": step.description, "passed": ok, "note": note})

        return {
            "results": results,
            "all_passed": all(r["passed"] for r in results),
            "failures": [r for r in results if not r["passed"]],
        }
