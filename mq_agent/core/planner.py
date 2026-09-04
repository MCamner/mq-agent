import json
from pathlib import Path

from openai import OpenAI

from mq_agent.config import load_config

from .state import AgentState, PlanStep
from .tool_contract import describe_tool, produced_kind

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

        declarations = _collection_declarations(state.context)
        steps = []
        for i, step_data in enumerate(steps_data):
            tool = step_data.get("tool")
            args = step_data.get("args", {})
            min_items = None

            # Discovery semantics belong to the declared collection. If the
            # model selects another producer with the same plausible-looking
            # arguments, replace that choice with the declaration instead of
            # executing a different search than the audit contract describes.
            declaration = _matching_collection(declarations, tool, args)
            if declaration is not None:
                discovery = declaration["discovery"]
                tool = discovery["tool"]
                args = discovery["args"]
                min_items = declaration["min_items"]

            steps.append(
                PlanStep(
                    index=i,
                    description=step_data["description"],
                    tool=tool,
                    args=args,
                    for_each=step_data.get("for_each"),
                    min_items=min_items,
                )
            )
        return steps


def _collection_declarations(context: dict) -> list[dict]:
    targets = context.get("audit_targets")
    if not isinstance(targets, dict):
        return []
    collections = targets.get("collections")
    if not isinstance(collections, list):
        return []
    return [item for item in collections if isinstance(item, dict)]


def _matching_collection(
    declarations: list[dict], planned_tool: object, planned_args: object
) -> dict | None:
    """Return the collection whose declared call the planned call represents."""
    from mq_agent.tools import TOOL_REGISTRY

    planned_fn = TOOL_REGISTRY.get(planned_tool) if isinstance(planned_tool, str) else None
    if planned_fn is None or produced_kind(planned_fn) is None or not isinstance(planned_args, dict):
        return None

    for declaration in declarations:
        discovery = declaration.get("discovery")
        min_items = declaration.get("min_items")
        if (
            isinstance(discovery, dict)
            and isinstance(discovery.get("tool"), str)
            and discovery.get("args") == planned_args
            and isinstance(min_items, int)
            and not isinstance(min_items, bool)
            and min_items >= 0
        ):
            declared_fn = TOOL_REGISTRY.get(discovery["tool"])
            if declared_fn and produced_kind(declared_fn) == produced_kind(planned_fn):
                return declaration
    return None


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

When context names a target, plan against that name directly. Discovery is for
sets whose members are not known in advance; using it to locate something the
context already names produces a step that reads more than it says it reads.
For each context.audit_targets.collections entry, copy discovery.tool and
discovery.args exactly into its discovery step. Do not choose a different
discovery tool. The runtime carries min_items from that declaration.

Return JSON with a "steps" array:
{"steps": [{"description": "...", "tool": "tool_name", "args": {},
            "for_each": {"step": 0, "as": "path"}}]}
"""
