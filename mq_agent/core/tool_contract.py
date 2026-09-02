"""One reading of what a tool accepts, used by both layers that need it.

The planner is told what the tools take; the executor checks what the plan
actually wrote. Those are different jobs, and neither replaces the other —
guidance that usually works is not a reason to drop an independent check, and
the check is what makes it observable when the guidance stops working.

What they must not do is disagree. If the planner were handed a hand-written
list of parameter names while the executor introspected the real functions, the
two descriptions of the same API could drift apart — which is precisely the
defect this module exists to close, one level up. Both read the signature here.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable

#: The parameter kinds a keyword call can never name.
_UNNAMEABLE = (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)


def accepted_parameters(tool_fn: Callable) -> dict[str, inspect.Parameter] | None:
    """The keyword parameters this tool accepts, or None when anything goes.

    None means "cannot be pinned down": the tool takes `**kwargs`, or its
    signature cannot be read at all. Both are reported as unknown rather than
    as empty, because an empty parameter list is a claim that the tool takes
    nothing — a different and much stronger statement.
    """
    try:
        signature = inspect.signature(tool_fn)
    except (TypeError, ValueError):
        return None
    parameters = list(signature.parameters.values())
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return None
    return {p.name: p for p in parameters if p.kind not in _UNNAMEABLE}


def describe_tool(name: str, tool_fn: Callable) -> dict:
    """The contract to show a planner: what this tool is called and what it takes.

    Required and optional are separated because they answer different questions
    for whoever writes the call — one is "what must I supply", the other is
    "what may I supply".
    """
    parameters = accepted_parameters(tool_fn)
    if parameters is None:
        return {"tool": name, "parameters": "unspecified"}
    return {
        "tool": name,
        "required": [
            p.name
            for p in parameters.values()
            if p.default is inspect.Parameter.empty
        ],
        "optional": [
            p.name
            for p in parameters.values()
            if p.default is not inspect.Parameter.empty
        ],
    }


def invalid_arguments(tool_name: str, tool_fn: Callable, args: dict) -> str | None:
    """Say why these arguments cannot call this tool, or None when they can.

    A plan is model output, and a model naming `directory` where the tool takes
    `path` has written a plausible, wrong call. Passing it through to
    `tool_fn(**args)` turns that into a `TypeError` at call time, which is
    reported as a failed step whose explanation reads like a bug in the tool.
    The failure is real; the description is of the wrong thing.

    Nothing here repairs the call. Mapping `directory` onto `path` would mean
    the run silently did something other than what the plan said, and a plan
    that cannot be trusted to describe its own execution is worse than one that
    fails loudly.
    """
    named = accepted_parameters(tool_fn)
    if named is None:
        # Either the tool takes anything, or we could not read it. Rejecting on
        # our own blindness would fail the plan for something it did not do.
        return None

    unknown = sorted(set(args) - set(named))
    missing = sorted(
        name
        for name, parameter in named.items()
        if parameter.default is inspect.Parameter.empty and name not in args
    )
    if not unknown and not missing:
        return None

    lines = ["invalid-tool-arguments", f"tool: {tool_name}"]
    if unknown:
        lines.append(f"unknown: {', '.join(unknown)}")
    if missing:
        lines.append(f"missing: {', '.join(missing)}")
    # Naming what the tool does accept is the part that lets a caller — or the
    # next planning pass — fix the call instead of guessing at it.
    lines.append(f"accepted: {', '.join(named)}")
    return "\n".join(lines)
