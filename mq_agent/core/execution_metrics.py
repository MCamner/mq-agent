"""Scoped counters at mq-agent dispatch and provider boundaries.

No prompts, responses, prices or inferred rework are retained. Counts exclude
backend work performed inside tools and external agents. Missing provider usage
invalidates that token field for the run rather than emitting a partial total.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

SCOPE_EVENT = {"kind": "metrics-scope:mq-agent-local"}


@dataclass
class ExecutionMetrics:
    tool_calls: int = 0
    tool_scope: bool = False
    tool_scope_incomplete: bool = False
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    input_measured: int = 0
    output_measured: int = 0
    model_scope_incomplete: bool = False

    def fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if self.tool_scope and not self.tool_scope_incomplete:
            fields["tool_calls"] = self.tool_calls
        tokens = {}
        if self.model_calls and not self.model_scope_incomplete:
            if self.input_measured == self.model_calls:
                tokens["input"] = self.input_tokens
            if self.output_measured == self.model_calls:
                tokens["output"] = self.output_tokens
        if tokens:
            fields["tokens"] = tokens
        return fields

    def merge(self, child: ExecutionMetrics) -> None:
        self.tool_calls += child.tool_calls
        self.tool_scope |= child.tool_scope
        self.tool_scope_incomplete |= child.tool_scope_incomplete or not child.tool_scope
        self.model_calls += child.model_calls
        self.input_tokens += child.input_tokens
        self.output_tokens += child.output_tokens
        self.input_measured += child.input_measured
        self.output_measured += child.output_measured
        self.model_scope_incomplete |= (
            child.model_scope_incomplete or (not child.tool_scope and not child.model_calls)
        )


_ACTIVE: ContextVar[ExecutionMetrics | None] = ContextVar("execution_metrics", default=None)


@contextmanager
def collect_execution_metrics(*, merge_into_parent: bool = False) -> Iterator[ExecutionMetrics]:
    parent = _ACTIVE.get()
    metrics = ExecutionMetrics()
    token = _ACTIVE.set(metrics)
    try:
        yield metrics
    finally:
        _ACTIVE.reset(token)
        if merge_into_parent and parent is not None:
            parent.merge(metrics)


def current_metrics_fields() -> dict[str, Any]:
    metrics = _ACTIVE.get()
    return metrics.fields() if metrics is not None else {}


def mark_tool_scope() -> None:
    metrics = _ACTIVE.get()
    if metrics is not None:
        metrics.tool_scope = True


def record_tool_call() -> None:
    metrics = _ACTIVE.get()
    if metrics is not None:
        metrics.tool_calls += 1


def invalidate_model_usage() -> None:
    """A known local model call does not expose usage through this collector."""
    metrics = _ACTIVE.get()
    if metrics is not None:
        metrics.model_scope_incomplete = True


def _count(usage: Any, name: str) -> int | None:
    try:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    except Exception:  # Telemetry must not replace the model result or exception.
        return None
    return value if type(value) is int and value >= 0 else None


def create_chat_completion(client: Any, **kwargs: Any) -> Any:
    metrics = _ACTIVE.get()
    if metrics is not None:
        metrics.model_calls += 1
    response = client.chat.completions.create(**kwargs)
    if metrics is not None:
        try:
            usage = getattr(response, "usage", None)
        except Exception:
            usage = None
        input_tokens = _count(usage, "prompt_tokens")
        output_tokens = _count(usage, "completion_tokens")
        if input_tokens is not None:
            metrics.input_tokens += input_tokens
            metrics.input_measured += 1
        if output_tokens is not None:
            metrics.output_tokens += output_tokens
            metrics.output_measured += 1
    return response


def scope_events(fields: dict[str, Any], existing: list[dict[str, str]] | None = None) -> list[dict[str, str]] | None:
    events = list(existing or [])
    if fields and SCOPE_EVENT not in events:
        events.append(dict(SCOPE_EVENT))
    return events or None
