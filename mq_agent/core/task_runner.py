"""Declarative task execution from YAML task files."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TEMPLATE_RE = re.compile(r"\{\{step:([^}]+)\}\}")


@dataclass
class TaskStep:
    name: str
    tool: str
    description: str = ""
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    step: str
    tool: str
    status: str  # "ok" | "error" | "unknown-tool" | "dry-run"
    output: str


@dataclass
class Task:
    name: str
    steps: list[TaskStep]
    version: str = "0.1"
    description: str = ""


def _resolve_templates(args: dict[str, Any], step_outputs: dict[str, str]) -> dict[str, Any]:
    """Replace {{step:name}} in string args with output from a completed step."""
    resolved: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            resolved[key] = _TEMPLATE_RE.sub(
                lambda m: step_outputs.get(m.group(1), m.group(0)), value
            )
        else:
            resolved[key] = value
    return resolved


def load_task(path: Path) -> Task:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required for task runner — uv pip install pyyaml") from exc

    data = yaml.safe_load(path.read_text())
    steps = [
        TaskStep(
            name=s["name"],
            tool=s["tool"],
            description=s.get("description", ""),
            args=s.get("args", {}),
        )
        for s in data.get("steps", [])
    ]
    return Task(
        name=data.get("name", path.stem),
        version=str(data.get("version", "0.1")),
        description=data.get("description", ""),
        steps=steps,
    )


def run_task(task: Task, dry_run: bool = False) -> list[StepResult]:
    from mq_agent.tools import TOOL_REGISTRY

    results: list[StepResult] = []
    step_outputs: dict[str, str] = {}

    for step in task.steps:
        if dry_run:
            results.append(StepResult(
                step=step.name,
                tool=step.tool,
                status="dry-run",
                output=f"Would call {step.tool}({step.args})",
            ))
            continue

        fn = TOOL_REGISTRY.get(step.tool)
        if fn is None:
            results.append(StepResult(
                step=step.name,
                tool=step.tool,
                status="unknown-tool",
                output=f"Tool not registered: {step.tool}",
            ))
            continue

        try:
            resolved_args = _resolve_templates(step.args, step_outputs)
            output = fn(**resolved_args)
            output_str = str(output)
            step_outputs[step.name] = output_str
            results.append(StepResult(
                step=step.name,
                tool=step.tool,
                status="ok",
                output=output_str,
            ))
        except Exception as exc:
            results.append(StepResult(
                step=step.name,
                tool=step.tool,
                status="error",
                output=str(exc),
            ))

    return results


def find_task_files(*search_dirs: Path) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for d in search_dirs:
        if not d.exists():
            continue
        for f in sorted(d.glob("*.yaml")):
            if f.resolve() not in seen:
                seen.add(f.resolve())
                result.append(f)
    return result
