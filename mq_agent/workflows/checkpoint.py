"""Bounded, content-addressed workflow session checkpoints.

A checkpoint is a small resume authorization record over one already-persisted
workflow run. It does not copy the run body, tool args/results, task prose,
transcripts, file contents, environment state, or credentials.

The existing WorkflowRun remains authoritative. A checkpoint only binds:
- exact persisted run bytes;
- exact workflow template definition;
- an explicit owner label;
- an expiry;
- bounded step ids needed to explain what can resume.

Because resume persists the run before execution, the run fingerprint changes
on first use. Reusing the same checkpoint therefore fails closed as stale.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mq_agent.tools.contract_validation import validate_contract

from .models import StepApproval, StepStatus, WorkflowStatus
from .state import WorkflowRun, WorkflowStateError
from .storage import WorkflowStore
from .templates import TemplateError, load_template

SCHEMA = "mq.workflow-checkpoint.v1"
DEFAULT_TTL_HOURS = 24
MAX_TTL_HOURS = 168
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+\-]{0,127}$")


class WorkflowCheckpointError(WorkflowStateError):
    """Checkpoint cannot be created, verified, or used safely."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _checkpoint_id(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "checkpoint_id"}
    return _fingerprint(body)


def _iso(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkflowCheckpointError(f"invalid checkpoint timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise WorkflowCheckpointError("checkpoint timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _validate_owner(owner: str) -> str:
    owner = owner.strip()
    if not _OWNER_RE.fullmatch(owner):
        raise WorkflowCheckpointError(
            "owner must be 1-128 characters using letters, numbers, . _ : @ + or -"
        )
    return owner


def template_fingerprint(template: str) -> str:
    try:
        raw = load_template(template)
    except TemplateError as exc:
        raise WorkflowCheckpointError(str(exc)) from exc
    return _fingerprint(raw)


def _resumable_step_ids(run: WorkflowRun) -> list[str]:
    resumable_status = {
        StepStatus.PENDING,
        StepStatus.AWAITING_APPROVAL,
        StepStatus.RUNNING,
        StepStatus.FAILED,
    }
    return [
        step.id
        for step in run.plan.steps
        if step.status in resumable_status
        and step.approval not in (StepApproval.STEP, StepApproval.FORBIDDEN)
    ]


def build_checkpoint(
    run: WorkflowRun,
    *,
    run_fingerprint: str,
    owner: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build and validate one immutable checkpoint payload."""
    owner = _validate_owner(owner)
    if not 1 <= ttl_hours <= MAX_TTL_HOURS:
        raise WorkflowCheckpointError(
            f"ttl_hours must be between 1 and {MAX_TTL_HOURS}"
        )
    if run.status not in (WorkflowStatus.PAUSED, WorkflowStatus.FAILED):
        raise WorkflowCheckpointError(
            "checkpoint requires a paused or failed workflow run"
        )

    created = (now or datetime.now(UTC)).astimezone(UTC)
    expires = created + timedelta(hours=ttl_hours)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "created_at": _iso(created),
        "expires_at": _iso(expires),
        "owner": owner,
        "run": {
            "run_id": run.run_id,
            "run_fingerprint": run_fingerprint,
            "status": run.status.value,
            "template": run.plan.template,
            "template_fingerprint": template_fingerprint(run.plan.template),
            "repo_name": Path(run.plan.repo).name,
            "current_step": run.current_step,
            "passed_steps": [
                step.id for step in run.plan.steps if step.status is StepStatus.PASSED
            ],
            "resumable_steps": _resumable_step_ids(run),
            "replans_used": run.replans_used,
        },
    }
    payload["checkpoint_id"] = _checkpoint_id(payload)
    validate_contract("workflow_checkpoint.schema.json", payload)
    return payload


def _atomic_create(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise WorkflowCheckpointError(f"checkpoint already exists: {payload['checkpoint_id']}")
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise WorkflowCheckpointError(
                f"checkpoint already exists: {payload['checkpoint_id']}"
            )
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


class WorkflowCheckpointStore:
    """Checkpoint persistence and fail-closed verification over WorkflowStore."""

    def __init__(self, workflow_store: WorkflowStore | None = None) -> None:
        self.workflow_store = workflow_store or WorkflowStore()
        self.dir = self.workflow_store.dir / "checkpoints"

    def _path(self, checkpoint_id: str) -> Path:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", checkpoint_id):
            raise WorkflowCheckpointError("invalid checkpoint id")
        return self.dir / f"{checkpoint_id.removeprefix('sha256:')}.json"

    def create(
        self,
        run_id: str,
        *,
        owner: str,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        run = self.workflow_store.load_run(run_id)
        run_fingerprint = self.workflow_store.run_fingerprint(run_id)
        payload = build_checkpoint(
            run,
            run_fingerprint=run_fingerprint,
            owner=owner,
            ttl_hours=ttl_hours,
            now=now,
        )
        _atomic_create(self._path(payload["checkpoint_id"]), payload)
        return payload

    def load(self, checkpoint_id: str) -> dict[str, Any]:
        path = self._path(checkpoint_id)
        if path.is_symlink() or not path.is_file():
            raise WorkflowCheckpointError(f"no such checkpoint: {checkpoint_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowCheckpointError("checkpoint is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WorkflowCheckpointError("checkpoint must be a JSON object")
        try:
            validate_contract("workflow_checkpoint.schema.json", payload)
        except Exception as exc:
            raise WorkflowCheckpointError(
                f"checkpoint contract validation failed: {exc}"
            ) from exc
        if payload.get("checkpoint_id") != _checkpoint_id(payload):
            raise WorkflowCheckpointError("checkpoint fingerprint mismatch")
        return payload

    def verify(
        self,
        checkpoint_id: str,
        *,
        owner: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        owner = _validate_owner(owner)
        payload = self.load(checkpoint_id)
        errors: list[str] = []
        if payload["owner"] != owner:
            errors.append("owner mismatch")

        current = (now or datetime.now(UTC)).astimezone(UTC)
        expires = _parse_time(payload["expires_at"])
        if current >= expires:
            errors.append("checkpoint expired")

        run_ref = payload["run"]
        run_id = str(run_ref["run_id"])
        try:
            current_fingerprint = self.workflow_store.run_fingerprint(run_id)
        except WorkflowStateError as exc:
            errors.append(str(exc))
            current_fingerprint = None

        if current_fingerprint is not None and current_fingerprint != run_ref["run_fingerprint"]:
            errors.append("workflow run changed since checkpoint creation")

        try:
            run = self.workflow_store.load_run(run_id)
        except WorkflowStateError as exc:
            errors.append(str(exc))
            run = None

        if run is not None:
            if run.status.value != run_ref["status"]:
                errors.append("workflow run status drift")
            if run.plan.template != run_ref["template"]:
                errors.append("workflow template identity drift")
            if Path(run.plan.repo).name != run_ref["repo_name"]:
                errors.append("repository identity drift")
            if run.current_step != run_ref["current_step"]:
                errors.append("current step drift")
            if run.replans_used != run_ref["replans_used"]:
                errors.append("replan count drift")
            passed = [
                step.id for step in run.plan.steps if step.status is StepStatus.PASSED
            ]
            if passed != run_ref["passed_steps"]:
                errors.append("passed step set drift")
            if _resumable_step_ids(run) != run_ref["resumable_steps"]:
                errors.append("resumable step set drift")

        try:
            current_template_fingerprint = template_fingerprint(str(run_ref["template"]))
        except WorkflowCheckpointError as exc:
            errors.append(str(exc))
        else:
            if current_template_fingerprint != run_ref["template_fingerprint"]:
                errors.append("workflow template changed since checkpoint creation")

        return {
            "kind": "mq-workflow-checkpoint-status",
            "schema": SCHEMA,
            "checkpoint_id": checkpoint_id,
            "status": "READY" if not errors else "REFUSED",
            "run_id": run_id,
            "owner": payload["owner"],
            "created_at": payload["created_at"],
            "expires_at": payload["expires_at"],
            "current_step": run_ref["current_step"],
            "passed_steps": list(run_ref["passed_steps"]),
            "resumable_steps": list(run_ref["resumable_steps"]),
            "errors": errors,
        }

    def prepare_resume(
        self,
        checkpoint_id: str,
        *,
        owner: str,
        now: datetime | None = None,
    ) -> tuple[dict[str, Any], WorkflowRun]:
        report = self.verify(checkpoint_id, owner=owner, now=now)
        if report["status"] != "READY":
            raise WorkflowCheckpointError(
                "checkpoint resume refused: " + "; ".join(report["errors"])
            )
        payload = self.load(checkpoint_id)
        run = self.workflow_store.load_run(str(payload["run"]["run_id"]))
        return payload, run
