"""The planner is told the call it should write, not left to invent one.

A list of bare tool names asks a model to guess the signature, and a guess that
reads well is still a guess: `directory` for a tool that takes `path`. #233 made
that failure honest. This makes it unnecessary — without removing the check,
because guidance that usually works is not a reason to stop verifying.
"""
from __future__ import annotations

import inspect
import json

from mq_agent.core import executor as executor_module
from mq_agent.core.planner import Planner, _FALLBACK_SYSTEM
from mq_agent.core.tool_contract import (
    accepted_parameters,
    describe_tool,
    invalid_arguments,
)
from mq_agent.tools.repo_tools import find_files, list_files


def test_the_planner_is_given_the_parameters_of_the_tools_it_may_use() -> None:
    contracts = Planner._tool_contracts(["list_files", "find_files"])

    assert contracts == [
        {
            "tool": "list_files",
            "required": [],
            "optional": ["path", "pattern"],
            "produces": "paths",
        },
        {
            "tool": "find_files",
            "required": [],
            "optional": ["path", "pattern"],
            "produces": "paths",
        },
    ]


def test_required_and_optional_are_separated() -> None:
    # They answer different questions: what must I supply, what may I supply.
    def sample(path: str, pattern: str = "*") -> str:
        return path

    assert describe_tool("sample", sample) == {
        "tool": "sample",
        "required": ["path"],
        "optional": ["pattern"],
    }


def test_a_tool_whose_arguments_cannot_be_pinned_down_says_so() -> None:
    """Unspecified, not empty.

    An empty parameter list is a claim that the tool takes nothing, which is a
    stronger and different statement from "this could not be determined".
    """
    def flexible(**kwargs) -> str:
        return "ok"

    assert describe_tool("flexible", flexible) == {
        "tool": "flexible",
        "parameters": "unspecified",
    }
    assert accepted_parameters(flexible) is None


def test_an_unregistered_tool_is_passed_through_as_a_name() -> None:
    # The caller asked for it. A plan naming an unregistered tool is a defect
    # the executor reports; the planner must not hide it by narrowing the list.
    assert Planner._tool_contracts(["not_a_real_tool"]) == [{"tool": "not_a_real_tool"}]


def test_the_prompt_forbids_synonyms_in_so_many_words() -> None:
    # The contract is only useful if the model is told the names are exact.
    assert "exact names" in _FALLBACK_SYSTEM
    assert "directory" in _FALLBACK_SYSTEM
    assert "unspecified" in _FALLBACK_SYSTEM


def test_both_layers_read_the_same_signature() -> None:
    """Guidance and validation must not be able to disagree.

    Two descriptions of one API drifting apart is the defect being closed here,
    one level up. If the planner were handed a hand-written parameter list, it
    could be corrected while the executor kept checking against the real
    function — or the reverse.
    """
    contract = describe_tool("list_files", list_files)
    accepted = set(contract["required"]) | set(contract["optional"])
    signature = {
        name
        for name, parameter in inspect.signature(list_files).parameters.items()
        if parameter.kind
        not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    }

    assert accepted == signature
    # And the executor accepts exactly that set and nothing else.
    assert invalid_arguments("list_files", list_files, dict.fromkeys(accepted, ".")) is None
    assert invalid_arguments("list_files", list_files, {"directory": "."}) is not None


def test_the_executor_check_survives_the_move() -> None:
    # invalid_arguments moved to the shared module; the executor still exposes
    # it, so nothing that validated before stops validating now.
    assert executor_module.invalid_arguments is invalid_arguments
    assert invalid_arguments("find_files", find_files, {"directory": "."}) is not None


def test_guidance_does_not_replace_validation() -> None:
    """The invariant worth stating as a test.

    Telling the planner the contract makes bad plans rarer. It cannot make them
    impossible — the planner is a model. Removing the executor check would mean
    the next drift is discovered by a user, not by the run.
    """
    source = inspect.getsource(executor_module.Executor.run_step)

    assert "invalid_arguments" in source


class _CapturingClient:
    """Stands in for the OpenAI client and keeps what was actually sent."""

    def __init__(self):
        self.sent: dict = {}
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.sent = kwargs

        class _Message:
            content = '{"steps": []}'

        class _Choice:
            message = _Message()

        class _Response:
            choices = [_Choice()]

        return _Response()


def test_the_contract_actually_reaches_the_model() -> None:
    """Built and not sent is the same as not built.

    Without this, `_tool_contracts` could be correct, tested, and entirely
    disconnected from the request — the planner would go back to shipping bare
    names and every test here would stay green.
    """
    from mq_agent.core.state import AgentState

    client = _CapturingClient()
    planner = Planner.__new__(Planner)
    planner.client = client  # type: ignore[assignment]
    planner._model = "test-model"
    planner._system_prompt = _FALLBACK_SYSTEM

    planner.create_plan(AgentState(goal="g"), ["list_files"])

    sent = json.loads(client.sent["messages"][1]["content"])
    assert sent["available_tools"] == [
        {
            "tool": "list_files",
            "required": [],
            "optional": ["path", "pattern"],
            "produces": "paths",
        }
    ]
    assert "exact names" in client.sent["messages"][0]["content"]
