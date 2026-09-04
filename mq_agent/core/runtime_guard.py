"""Refuse to produce evidence a run cannot account for.

`tests/conftest.py` already made this a property for the test suite, and states
the half it could not reach:

    Keeping test runs out of it was a discipline — remember to set the variable
    — and a discipline is not a property. [...] A manual `docs-audit` still
    needs the variable set by hand; the suite is the half that can be enforced.

This is the other half. Observations are placed in eras by commit
(`mq_agent.tools.analysis_cohort`), so an observation produced by a dirty
working tree, or by a commit that is on no branch anyone has seen, belongs to no
era. It is not weak evidence — it is unattributable evidence, and once written
the store cannot tell it apart from the rest. That happened: a debugging run
reached the production store and was later counted as real, and the agreed rule
is that history is never deleted or backfilled.

The check runs before execution starts, for the reason established when a
missing API key stopped opening an execution record: a condition that means the
run must not happen belongs before the record, not inside it.

Two limits, stated rather than papered over:

* It proves HEAD is an ancestor of the **locally known** `origin/main`, not of
  whatever GitHub holds right now. Nothing here touches the network.
* It sees the working tree, not the interpreter. A checkout that is clean and
  integrated can still be running an editable install of something else.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The ref an observation's commit must be reachable from. Local, never fetched.
CANONICAL_REF = "origin/main"

#: Seconds any single git probe may take. Telemetry-adjacent work never hangs a
#: run; a probe that times out is a probe that failed, and failure is closed.
PROBE_TIMEOUT = 10

#: Every environment variable naming a durable evidence store, and the file each
#: one defaults to under the operator's home. Kept in step with
#: `tests/conftest.py`, which redirects exactly these.
EVIDENCE_STORES: dict[str, str] = {
    "MQ_AGENT_ROUTE_OUTCOMES": "route-outcomes.jsonl",
    "MQ_AGENT_EXECUTION_OUTCOMES": "execution-outcomes.jsonl",
}


@dataclass(frozen=True)
class Verdict:
    """Whether this runtime may write production evidence, and why not."""

    allowed: bool
    reason: str | None = None
    detail: str = ""


def repository_root(package_file: str | Path | None = None) -> Path | None:
    """The checkout the *running code* lives in, or None when it is installed.

    Deliberately derived from this module's own path and never from the working
    directory: `mq-agent docs-audit /some/other/repo` must be judged on the code
    doing the auditing, not on the repository being audited.
    """
    here = Path(package_file or __file__).resolve()
    root = here.parents[2]
    return root if (root / ".git").exists() else None


def production_stores_at_risk(environ: dict[str, str] | None = None) -> tuple[str, ...]:
    """The evidence stores this run would write in the operator's home.

    Empty means the run cannot corrupt production evidence no matter what it
    does, and there is nothing for the guard to protect. That is the escape, and
    it is the same one the suite uses: point the stores elsewhere.

    `MQ_AGENT_TELEMETRY=off` is not enough on its own — it silences execution
    outcomes and leaves the route store exactly where it was.
    """
    env = os.environ if environ is None else environ
    at_risk = []
    for name, filename in EVIDENCE_STORES.items():
        configured = env.get(name)
        if configured and Path(configured).expanduser() != Path.home() / ".mq-agent" / filename:
            continue
        at_risk.append(name)
    return tuple(at_risk)


def _probe(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def check(root: Path | None = None) -> Verdict:
    """May a run from this runtime write production evidence?

    `root` names the checkout to judge; omitting it resolves the one the running
    code lives in. No checkout at all is the released wheel: there is no working
    tree to be dirty and its code is whatever was published, so it is the
    canonical case rather than the suspicious one. Refusing there would brick
    every installed copy of the tool.
    """
    checkout = root if root is not None else repository_root()
    if checkout is None:
        return Verdict(allowed=True)

    status = _probe(checkout, "status", "--porcelain")
    if status is None or status.returncode != 0:
        return Verdict(
            allowed=False,
            reason="git-probe-failed",
            detail=f"could not read the state of {checkout}",
        )
    if status.stdout.strip():
        changed = len(status.stdout.strip().splitlines())
        return Verdict(
            allowed=False,
            reason="dirty-worktree",
            detail=f"{changed} uncommitted change(s) in {checkout}",
        )

    head = _probe(checkout, "rev-parse", "--verify", "HEAD")
    if head is None or head.returncode != 0:
        return Verdict(
            allowed=False, reason="no-head", detail=f"{checkout} has no HEAD commit"
        )

    canonical = _probe(checkout, "rev-parse", "--verify", CANONICAL_REF)
    if canonical is None or canonical.returncode != 0:
        return Verdict(
            allowed=False,
            reason="no-canonical-ref",
            detail=f"{checkout} has no {CANONICAL_REF} to check against",
        )

    ancestor = _probe(checkout, "merge-base", "--is-ancestor", "HEAD", CANONICAL_REF)
    if ancestor is None:
        return Verdict(
            allowed=False,
            reason="git-probe-failed",
            detail=f"could not compare HEAD with {CANONICAL_REF}",
        )
    if ancestor.returncode != 0:
        return Verdict(
            allowed=False,
            reason="unintegrated-head",
            detail=f"{head.stdout.strip()[:7]} is not reachable from {CANONICAL_REF}",
        )

    return Verdict(allowed=True)
