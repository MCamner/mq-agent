"""Multi-agent swarm coordinator — runs multiple agents and merges results."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentManifest:
    """Declarative metadata for a single agent in a swarm."""

    name: str
    purpose: str
    safety_class: str  # "read-only" | "write-capable" | "subprocess"
    allowed_tools: list[str]
    requires_approve: bool = False
    output_contract: list[str] = field(default_factory=list)
    failure_behavior: str = "warn"  # "warn" | "skip" | "abort"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "safety_class": self.safety_class,
            "allowed_tools": self.allowed_tools,
            "requires_approve": self.requires_approve,
            "output_contract": self.output_contract,
            "failure_behavior": self.failure_behavior,
        }


@dataclass
class AgentResult:
    """Result from a single agent run inside a swarm."""

    agent: str
    status: str  # "ok" | "error" | "skipped" | "dry-run"
    output: dict = field(default_factory=dict)
    error: str = ""
    elapsed_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "elapsed_s": round(self.elapsed_s, 2),
        }


@dataclass
class SwarmConfig:
    """A named collection of agents to run together."""

    name: str
    description: str
    manifests: list[AgentManifest]
    goal: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "goal": self.goal,
            "agents": [m.to_dict() for m in self.manifests],
        }

    @property
    def agent_names(self) -> list[str]:
        return [m.name for m in self.manifests]

    @property
    def requires_approve(self) -> bool:
        return any(m.requires_approve for m in self.manifests)

    @property
    def safety_classes(self) -> list[str]:
        return list({m.safety_class for m in self.manifests})


@dataclass
class SwarmResult:
    """Aggregated results from a full swarm run."""

    config: str
    path: str
    dry_run: bool
    results: list[AgentResult]
    elapsed_s: float = 0.0

    @property
    def passed(self) -> bool:
        return all(r.status in ("ok", "dry-run", "skipped") for r in self.results)

    @property
    def failed_agents(self) -> list[str]:
        return [r.agent for r in self.results if r.status == "error"]

    def to_dict(self) -> dict:
        return {
            "config": self.config,
            "path": self.path,
            "dry_run": self.dry_run,
            "passed": self.passed,
            "elapsed_s": round(self.elapsed_s, 2),
            "failed_agents": self.failed_agents,
            "results": [r.to_dict() for r in self.results],
        }


class SwarmRunner:
    """Coordinates multiple specialist agents in a swarm run.

    SwarmRunner is a separate runtime mode from the Executor loop. Where
    Executor drives a single planner-generated PlanStep sequence, SwarmRunner
    dispatches to multiple independent agents defined in a SwarmConfig and
    merges their AgentResults into a SwarmResult. The two runtimes do not
    share step state or overlap in responsibility.
    """

    def __init__(self, client: Any):
        self.client = client

    def run(
        self,
        config: SwarmConfig,
        path: str = ".",
        dry_run: bool = False,
        approve: bool = False,
    ) -> SwarmResult:
        results: list[AgentResult] = []
        swarm_start = time.monotonic()

        for manifest in config.manifests:
            if dry_run:
                results.append(AgentResult(agent=manifest.name, status="dry-run"))
                continue

            if manifest.requires_approve and not approve:
                results.append(AgentResult(
                    agent=manifest.name,
                    status="skipped",
                    error="requires --approve",
                ))
                continue

            start = time.monotonic()
            try:
                output = self._run_agent(manifest, path, dry_run=False, approve=approve)
                results.append(AgentResult(
                    agent=manifest.name,
                    status="ok",
                    output=output,
                    elapsed_s=time.monotonic() - start,
                ))
            except Exception as exc:
                elapsed = time.monotonic() - start
                if manifest.failure_behavior == "abort":
                    results.append(AgentResult(
                        agent=manifest.name,
                        status="error",
                        error=str(exc),
                        elapsed_s=elapsed,
                    ))
                    break
                results.append(AgentResult(
                    agent=manifest.name,
                    status="error",
                    error=str(exc),
                    elapsed_s=elapsed,
                ))

        return SwarmResult(
            config=config.name,
            path=path,
            dry_run=dry_run,
            results=results,
            elapsed_s=time.monotonic() - swarm_start,
        )

    def plan(self, config: SwarmConfig, path: str = ".") -> list[dict]:
        """Return a dry plan — no execution, no API calls."""
        return [
            {
                "agent": m.name,
                "purpose": m.purpose,
                "safety_class": m.safety_class,
                "requires_approve": m.requires_approve,
                "failure_behavior": m.failure_behavior,
                "tools": m.allowed_tools,
            }
            for m in config.manifests
        ]

    def _run_agent(
        self,
        manifest: AgentManifest,
        path: str,
        dry_run: bool,
        approve: bool,
    ) -> dict:
        """Dispatch to the correct agent class based on manifest name."""
        name = manifest.name

        if name == "audit":
            from ..agents.audit_agent import AuditAgent
            return AuditAgent(self.client).run(path, dry_run=dry_run)

        if name == "signal":
            from ..agents.signal_agent import SignalAgent
            from ..tools.signal_tools import signal_available
            if not signal_available():
                return {"skipped": True, "reason": "repo-signal not installed"}
            return SignalAgent(self.client).run(path, dry_run=dry_run)

        if name == "docs":
            from ..agents.docs_agent import DocsAgent
            return DocsAgent(self.client).audit(path)

        if name == "ci":
            from ..agents.ci_agent import CIAgent
            return CIAgent(self.client).diagnose(path, dry_run=dry_run, approve=approve)

        if name == "release":
            from ..agents.release_agent import ReleaseAgent
            return ReleaseAgent(self.client).run_check(path, dry_run=dry_run, approve=approve)

        raise ValueError(f"Unknown agent in swarm: {name!r}")
