"""F2 active-versus-shadow context experiment runner.

The runner measures two pure context-pack selections against the same clean Git
snapshot and the same authorized evidence boundary. It never executes the task,
changes routing, writes prompts, mutates durable memory, or accepts shadow
output. Only bounded identifiers, logical source references and measurements are
persisted.
"""
from __future__ import annotations

import hashlib
import re
import signal
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from git import Repo

from mq_agent.tools.context_export import default_vault
from mq_agent.tools.context_pack import build_task_pack

from .evaluation import build_operational_comparison
from .models import build_feedback_experiment
from .store import append_comparison, append_experiment

BASELINE_STRATEGY = "context-pack-v1"
CANDIDATE_STRATEGY = "context-pack-v1+codegraph-guidance"
ACTIVE_STRATEGY = BASELINE_STRATEGY
SHADOW_STRATEGY = CANDIDATE_STRATEGY
DEFAULT_TIMEOUT_MS = 2000
DEFAULT_MAX_CONTEXT_BYTES = 65536
DEFAULT_MAX_SOURCES = 64
TASK_CLASS = "repo-review"


class FeedbackExperimentError(RuntimeError):
    """Bounded, public-safe experiment failure."""


class FeedbackBudgetExceeded(FeedbackExperimentError):
    """A pure shadow collection exceeded an explicit local budget."""


def _safe_repo_identity(repo: Repo) -> str:
    try:
        url = str(repo.remotes.origin.url)
    except (AttributeError, IndexError, ValueError):
        url = ""
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(repo.working_tree_dir or ".").name)


def _snapshot(repo: Repo) -> dict[str, str]:
    if repo.is_dirty(untracked_files=True):
        raise FeedbackExperimentError("repo-worktree-dirty")
    try:
        ref = repo.active_branch.name
    except TypeError:
        ref = "HEAD"
    return {"kind": "git", "ref": ref, "commit": repo.head.commit.hexsha}


def _same_snapshot(repo: Repo, expected: dict[str, str]) -> bool:
    if repo.is_dirty(untracked_files=True):
        return False
    return repo.head.commit.hexsha == expected["commit"]


def _evidence_fingerprint(vault: Path, repo_name: str) -> str:
    paths = [vault / ".mq" / "context-selection-vocabulary.json"]
    cards = vault / "memory" / "context-cards"
    paths.extend([cards / f"{repo_name}-card.md", cards / f"{repo_name}.md"])
    digest = hashlib.sha256()
    found = False
    for path in paths:
        if not path.is_file():
            continue
        found = True
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest() if found else "none"


@contextmanager
def _deadline(timeout_ms: int) -> Iterator[None]:
    if timeout_ms <= 0:
        raise ValueError("timeout_ms must be positive")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _timeout(_signum: int, _frame: object) -> None:
        raise TimeoutError("feedback-context-timeout")

    signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _logical_sources(pack: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    repos = pack.get("relevant_repos", [])
    if isinstance(repos, list) and repos:
        refs.append("repo-context:repo-card.md")
    for card in pack.get("cards", []):
        refs.append("context-card:" + Path(str(card)).name)
    return list(dict.fromkeys(refs))

def _measurement(
    pack: dict[str, Any],
    *,
    elapsed_ms: float,
    max_context_bytes: int,
    max_sources: int,
) -> tuple[dict[str, float | int | None], list[str]]:
    content = str(pack["content"])
    encoded = content.encode("utf-8")
    sources = _logical_sources(pack)
    if len(encoded) > max_context_bytes:
        raise FeedbackBudgetExceeded("context-byte-budget-exceeded")
    if len(sources) > max_sources:
        raise FeedbackBudgetExceeded("source-count-budget-exceeded")

    card_metadata = pack.get("card_metadata", {})
    card_values = list(card_metadata.values()) if isinstance(card_metadata, dict) else []
    stale = sum(
        1 for item in card_values
        if isinstance(item, dict) and item.get("freshness") in {"stale", "archived"}
    )
    stale_rate = (stale / len(card_values)) if card_values else None

    return (
        {
            "context_lines": len(content.splitlines()),
            "context_bytes": len(encoded),
            # No tokenizer is called here. Estimating and labelling it measured
            # would violate the roadmap's evidence rule.
            "context_tokens": None,
            "retrieval_latency_ms": round(elapsed_ms, 3),
            "source_count": len(sources),
            "deduplicated_source_count": len(set(sources)),
            "provenance_coverage": 1.0 if sources else 0.0,
            "stale_source_rate": stale_rate,
            "external_api_calls": 0,
            "cost": 0.0,
        },
        sources,
    )


def _collect_pack(
    task: str,
    *,
    repo_name: str,
    repo_parent: Path,
    vault: Path,
    codegraph: str,
    generated_at: str,
    timeout_ms: int,
    max_context_bytes: int,
    max_sources: int,
) -> tuple[dict[str, float | int | None], list[str]]:
    started = time.perf_counter()
    with _deadline(timeout_ms):
        pack = build_task_pack(
            task,
            target="both",
            repo=repo_name,
            vault=vault,
            repos_root=repo_parent,
            codegraph=codegraph,
            generated_at=generated_at,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    return _measurement(
        pack,
        elapsed_ms=elapsed_ms,
        max_context_bytes=max_context_bytes,
        max_sources=max_sources,
    )


def run_context_experiment(
    task: str,
    repo_path: str | Path,
    *,
    task_class: str = TASK_CLASS,
    execution_run_id: str | None = None,
    vault: Path | None = None,
    state_root: Path | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    max_context_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
    max_sources: int = DEFAULT_MAX_SOURCES,
) -> dict[str, Any]:
    """Run one zero-effect F2 context experiment and persist bounded evidence."""
    if task_class != TASK_CLASS:
        raise ValueError("F2 supports only task class repo-review")
    if not task.strip():
        raise ValueError("task must not be empty")
    if max_context_bytes <= 0 or max_sources <= 0:
        raise ValueError("feedback budgets must be positive")

    repo_root = Path(repo_path).expanduser().resolve()
    repo = Repo(repo_root)
    snapshot = _snapshot(repo)
    repository = _safe_repo_identity(repo)
    repo_name = repo_root.name
    vault_root = (
        vault.expanduser().resolve()
        if vault is not None
        else default_vault()
    )
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    feedback_run_id = f"fb-{uuid.uuid4()}"
    from .control import effective_strategy, strategy_codegraph

    active_strategy = effective_strategy(task_class, state_root)
    if active_strategy not in {BASELINE_STRATEGY, CANDIDATE_STRATEGY}:
        raise FeedbackExperimentError(f"unsupported-active-strategy:{active_strategy}")
    shadow_strategy = (
        CANDIDATE_STRATEGY
        if active_strategy == BASELINE_STRATEGY
        else BASELINE_STRATEGY
    )
    active_codegraph = strategy_codegraph(active_strategy)
    shadow_codegraph = strategy_codegraph(shadow_strategy)
    evidence_boundary = ["repo-context", "mqobsidian-context", "codegraph-local-guidance"]
    fingerprint = _evidence_fingerprint(vault_root, repo_name)

    def record_terminal(state: str) -> dict[str, Any]:
        experiment = build_feedback_experiment(
            task_class=task_class,
            repository=repository,
            active_strategy=active_strategy,
            shadow_strategy=shadow_strategy,
            snapshot_ref=snapshot["ref"],
            snapshot_commit=snapshot["commit"],
            evidence_sources=evidence_boundary,
            state=state,
            execution_run_id=execution_run_id,
            network_backends=[],
            evidence_boundary_sha256=(fingerprint if fingerprint != "none" else None),
            feedback_run_id=feedback_run_id,
        )
        append_experiment(experiment, state_root)
        return experiment

    try:
        active_metrics, active_sources = _collect_pack(
            task,
            repo_name=repo_name,
            repo_parent=repo_root.parent,
            vault=vault_root,
            codegraph=active_codegraph,
            generated_at=generated_at,
            timeout_ms=timeout_ms,
            max_context_bytes=max_context_bytes,
            max_sources=max_sources,
        )
        if not _same_snapshot(repo, snapshot) or _evidence_fingerprint(vault_root, repo_name) != fingerprint:
            return {
                "experiment": record_terminal("blocked"),
                "comparison": None,
                "status": "BLOCKED",
                "reason": "evidence-snapshot-drift",
            }

        shadow_metrics, shadow_sources = _collect_pack(
            task,
            repo_name=repo_name,
            repo_parent=repo_root.parent,
            vault=vault_root,
            codegraph=shadow_codegraph,
            generated_at=generated_at,
            timeout_ms=timeout_ms,
            max_context_bytes=max_context_bytes,
            max_sources=max_sources,
        )
        if not _same_snapshot(repo, snapshot) or _evidence_fingerprint(vault_root, repo_name) != fingerprint:
            return {
                "experiment": record_terminal("blocked"),
                "comparison": None,
                "status": "BLOCKED",
                "reason": "evidence-snapshot-drift",
            }
    except KeyboardInterrupt:
        record_terminal("cancelled")
        raise
    except TimeoutError:
        return {
            "experiment": record_terminal("cancelled"),
            "comparison": None,
            "status": "BLOCKED",
            "reason": "feedback-context-timeout",
        }
    except (FeedbackBudgetExceeded, OSError, ValueError) as exc:
        return {
            "experiment": record_terminal("blocked"),
            "comparison": None,
            "status": "BLOCKED",
            "reason": str(exc),
        }

    experiment = build_feedback_experiment(
        task_class=task_class,
        repository=repository,
        active_strategy=active_strategy,
        shadow_strategy=shadow_strategy,
        snapshot_ref=snapshot["ref"],
        snapshot_commit=snapshot["commit"],
        evidence_sources=evidence_boundary,
        state="completed",
        execution_run_id=execution_run_id,
        network_backends=[],
        evidence_boundary_sha256=(fingerprint if fingerprint != "none" else None),
        feedback_run_id=feedback_run_id,
    )
    comparison = build_operational_comparison(
        experiment,
        active_metrics=active_metrics,
        shadow_metrics=shadow_metrics,
        active_sources=active_sources,
        shadow_sources=shadow_sources,
    )
    # Both records are validated before the first append. A crash between these
    # appends is visible as an experiment without a comparison, never as a
    # silently fabricated comparison.
    append_experiment(experiment, state_root)
    append_comparison(comparison, state_root)
    return {
        "experiment": experiment,
        "comparison": comparison,
        "status": "PASS",
        "reason": None,
    }
