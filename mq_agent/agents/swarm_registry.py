"""Built-in swarm configurations — named collections of agents with declared safety contracts."""
from __future__ import annotations

from ..core.swarm import AgentManifest, SwarmConfig

# ── manifests ──────────────────────────────────────────────────────────────

AUDIT_MANIFEST = AgentManifest(
    name="audit",
    purpose="Read-only repo audit: git state, file structure, recent commits",
    safety_class="read-only",
    allowed_tools=["git_status", "git_log", "git_diff", "git_branch", "git_remote",
                   "repo_summary", "list_files", "read_file", "find_files"],
    requires_approve=False,
    output_contract=["summary", "steps", "passed"],
    failure_behavior="warn",
)

SIGNAL_MANIFEST = AgentManifest(
    name="signal",
    purpose="repo-signal quality assessment: README score, publish checklist, improvement plan",
    safety_class="read-only",
    allowed_tools=["repo_scan", "repo_readme_score", "repo_publish_checklist",
                   "repo_analyze", "repo_signal_json"],
    requires_approve=False,
    output_contract=["scores", "readme", "publish", "steps"],
    failure_behavior="skip",
)

DOCS_MANIFEST = AgentManifest(
    name="docs",
    purpose="Documentation audit: README, CHANGELOG, docstrings, /docs folder",
    safety_class="read-only",
    allowed_tools=["read_file", "list_files", "find_files", "repo_summary"],
    requires_approve=False,
    output_contract=["steps", "verification"],
    failure_behavior="warn",
)

CI_MANIFEST = AgentManifest(
    name="ci",
    purpose="CI diagnosis: run tests, lint, type check, surface failures",
    safety_class="subprocess",
    allowed_tools=["run_command", "read_file"],
    requires_approve=False,
    output_contract=["ci_context", "steps"],
    failure_behavior="warn",
)

RELEASE_MANIFEST = AgentManifest(
    name="release",
    purpose="Release readiness: tests, packaging, changelog, git cleanliness",
    safety_class="write-capable",
    allowed_tools=["git_status", "git_log", "git_diff", "repo_summary",
                   "read_file", "list_files", "run_command"],
    requires_approve=True,
    output_contract=["steps", "ready"],
    failure_behavior="warn",
)

# ── swarm configs ──────────────────────────────────────────────────────────

SWARM_AUDIT = SwarmConfig(
    name="audit",
    description="Full read-only repo health check: audit + signal + docs",
    goal="Produce a comprehensive read-only assessment of repository health, "
         "quality signals and documentation coverage.",
    manifests=[AUDIT_MANIFEST, SIGNAL_MANIFEST, DOCS_MANIFEST],
)

SWARM_RELEASE_CHECK = SwarmConfig(
    name="release-check",
    description="Release readiness: CI + audit + release validation",
    goal="Validate the repository is ready for a release. "
         "Runs CI checks, repo audit and release gate validation.",
    manifests=[CI_MANIFEST, AUDIT_MANIFEST, RELEASE_MANIFEST],
)

SWARM_CI = SwarmConfig(
    name="ci",
    description="CI-focused swarm: tests, lint, types",
    goal="Diagnose CI health and surface actionable failures.",
    manifests=[CI_MANIFEST, AUDIT_MANIFEST],
)

# ── registry ───────────────────────────────────────────────────────────────

SWARM_REGISTRY: dict[str, SwarmConfig] = {
    "audit": SWARM_AUDIT,
    "release-check": SWARM_RELEASE_CHECK,
    "ci": SWARM_CI,
}


def get_swarm(name: str) -> SwarmConfig:
    if name not in SWARM_REGISTRY:
        available = ", ".join(SWARM_REGISTRY)
        raise KeyError(f"Unknown swarm config {name!r}. Available: {available}")
    return SWARM_REGISTRY[name]


def list_swarms() -> list[dict]:
    return [
        {
            "name": cfg.name,
            "description": cfg.description,
            "agents": cfg.agent_names,
            "requires_approve": cfg.requires_approve,
            "safety_classes": cfg.safety_classes,
        }
        for cfg in SWARM_REGISTRY.values()
    ]
