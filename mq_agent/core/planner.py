import json
from pathlib import Path

from openai import OpenAI

from mq_agent.config import load_config

from .state import AgentState, PlanStep
from .tool_contract import describe_tool

PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "planner.md"


class Planner:
    """Uses OpenAI to decompose a goal into a sequence of tool-backed steps."""

    def __init__(self, client: OpenAI):
        self.client = client
        self._model = load_config().effective_model()
        self._system_prompt = (
            PROMPT_PATH.read_text() if PROMPT_PATH.exists() else _FALLBACK_SYSTEM
        )

    @property
    def model(self) -> str:
        """The model this planner actually calls.

        Exposed so execution telemetry can read the model the run used instead
        of resolving the configuration a second time and hoping the two agree.
        """
        return self._model

    @staticmethod
    def _tool_contracts(available_tools: list[str]) -> list[dict]:
        """Name each tool with the parameters it actually takes.

        A list of bare names asks the model to invent the call signature, and a
        model asked to invent one will write something plausible — `directory`
        for a tool that takes `path`. That is not a mistake it can avoid
        without the contract, so the contract is what it gets.

        A tool the registry does not hold is passed through as a name alone
        rather than dropped: the caller asked for it, and a plan that names an
        unregistered tool is a defect the executor should report, not one the
        planner should hide by quietly narrowing the list.
        """
        from mq_agent.tools import TOOL_REGISTRY

        contracts: list[dict] = []
        for name in available_tools:
            tool_fn = TOOL_REGISTRY.get(name)
            contracts.append(
                describe_tool(name, tool_fn) if tool_fn else {"tool": name}
            )
        return contracts

    def create_plan(self, state: AgentState, available_tools: list[str]) -> list[PlanStep]:
        user_msg = json.dumps(
            {
                "goal": state.goal,
                "working_dir": state.working_dir,
                "available_tools": self._tool_contracts(available_tools),
                "context": state.context,
                "safety_mode": state.safety_mode.value,
            },
            indent=2,
        )

        response = self.client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        raw = json.loads(response.choices[0].message.content or "{}")
        steps_data = raw.get("steps", raw) if isinstance(raw, dict) else raw

        return [
            PlanStep(
                index=i,
                description=s["description"],
                tool=s.get("tool"),
                args=s.get("args", {}),
                for_each=s.get("for_each"),
            )
            for i, s in enumerate(steps_data)
        ]


_FALLBACK_SYSTEM = """\
You are an expert software engineering agent planner.

Break the goal into specific, ordered steps. Use only tools from the available_tools list.
Prefer read operations before write operations.

Each entry in available_tools gives the tool name and the argument names it accepts:
"required" must all be supplied, "optional" may be. Use those exact names. A
synonym is a failed step, not a near miss: a tool documented with "path" does not
accept "directory", "folder", or "dir". When a tool lists "parameters":
"unspecified", its arguments could not be determined — keep them minimal.

A step that must act on what an earlier step found declares that dependency
instead of writing a placeholder path. Only a tool whose contract shows
"produces" can be depended on. Add "for_each": {"step": N, "as": "param"} and
the tool runs once per item step N produced, with the item bound to "param" —
leave that argument out of "args". Never write "<source_file_path>" or any
other stand-in: an argument that only looks like a reference resolves to
nothing.

Return JSON with a "steps" array:
{"steps": [{"description": "...", "tool": "tool_name", "args": {},
            "for_each": {"step": 0, "as": "path"}}]}
"""
