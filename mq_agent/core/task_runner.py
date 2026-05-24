"""Declarative task execution from YAML task files."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
            output = fn(**step.args)
            results.append(StepResult(
                step=step.name,
                tool=step.tool,
                status="ok",
                output=str(output),
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
