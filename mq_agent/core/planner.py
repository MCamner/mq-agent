import json
from pathlib import Path

from openai import OpenAI

from .state import AgentState, PlanStep

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planner.md"


class Planner:
    """Uses OpenAI to decompose a goal into a sequence of tool-backed steps."""

    def __init__(self, client: OpenAI):
        self.client = client
        self._system_prompt = (
            PROMPT_PATH.read_text() if PROMPT_PATH.exists() else _FALLBACK_SYSTEM
        )

    def create_plan(self, state: AgentState, available_tools: list[str]) -> list[PlanStep]:
        user_msg = json.dumps(
            {
                "goal": state.goal,
                "working_dir": state.working_dir,
                "available_tools": available_tools,
                "context": state.context,
                "safety_mode": state.safety_mode.value,
            },
            indent=2,
        )

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        raw = json.loads(response.choices[0].message.content)
        steps_data = raw.get("steps", raw) if isinstance(raw, dict) else raw

        return [
            PlanStep(
                index=i,
                description=s["description"],
                tool=s.get("tool"),
                args=s.get("args", {}),
            )
            for i, s in enumerate(steps_data)
        ]


_FALLBACK_SYSTEM = """\
You are an expert software engineering agent planner.

Break the goal into specific, ordered steps. Use only tools from the available_tools list.
Prefer read operations before write operations.
Return JSON with a "steps" array:
{"steps": [{"description": "...", "tool": "tool_name", "args": {}}]}
"""
