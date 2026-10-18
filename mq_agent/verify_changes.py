"""Deterministic repo-owned verification. Receipts are evidence, never approval."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONFIG = ".mq/verification.json"
RECEIPT_SCHEMA = "mq.verification-receipt.v1"


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, timeout=15,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError("Git query failed; check the repository and base revision") from exc


def _root(path: Path) -> Path:
    return Path(os.fsdecode(_git(path, "rev-parse", "--show-toplevel")).strip()).resolve()


def _names(raw: bytes) -> list[str]:
    return [os.fsdecode(item) for item in raw.split(b"\0") if item]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _target(root: Path, value: str) -> Path:
    if not value or value.startswith("-") or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("Check targets must be repo-relative paths, without options or traversal")
    path = root / value
    if not path.resolve().is_relative_to(root):
        raise ValueError("Check target escapes the repository")
    return path


def _config(root: Path) -> dict[str, Any]:
    try:
        config = json.loads(_target(root, CONFIG).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Missing or invalid {CONFIG}") from exc
    if not isinstance(config, dict) or config.get("schema") != "mq.verification-config.v1":
        raise ValueError("Unsupported verification config schema")
    if set(config) - {"schema", "checks", "python_project"}:
        raise ValueError("Unknown verification config field")
    checks = config.get("checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 64:
        raise ValueError("Config must declare 1 to 64 checks")
    if "python_project" in config:
        project = config["python_project"]
        if not isinstance(project, str) or not _target(root, project).is_dir():
            raise ValueError("python_project must name an existing repo directory")
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "runner", "targets", "paths", "timeout_seconds"}:
            raise ValueError("Invalid check fields")
        name = check["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) or name in ids:
            raise ValueError("Check ids must be unique lowercase names")
        ids.add(name)
        if not isinstance(check["runner"], str) or check["runner"] not in {"bash", "bash-syntax", "python", "pytest"}:
            raise ValueError("Runner must be bash, bash-syntax, python or pytest")
        for field in ("targets", "paths"):
            values = check[field]
            if not isinstance(values, list) or not values or not all(isinstance(v, str) and v for v in values):
                raise ValueError(f"Check {field} must be a nonempty string list")
        if any(Path(v).is_absolute() or ".." in Path(v).parts for v in check["paths"]):
            raise ValueError("Matching patterns must be repo-relative")
        for value in check["targets"]:
            _target(root, value)
        if check["runner"] in {"bash", "bash-syntax", "python"} and len(check["targets"]) != 1:
            raise ValueError("Script runners take exactly one script")
        timeout = check["timeout_seconds"]
        if type(timeout) is not int or not 1 <= timeout <= 900:
            raise ValueError("Check timeout must be an integer between 1 and 900 seconds")
    return config


def _snapshot(root: Path, base: str) -> dict[str, Any]:
    if _git(root, "ls-files", "--unmerged", "-z"):
        raise ValueError("Resolve merge conflicts before verification")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    base_id = _git(root, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
    untracked = _names(_git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    changed = sorted(set(_names(_git(root, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base_id, "--")) + untracked))
    files = sorted(set(_names(_git(root, "ls-files", "-z")) + untracked + [CONFIG]))
    entries: list[list[Any]] = []
    for name in files:
        path = root / name
        if path.is_symlink():
            target = path.resolve()
            # External dependency contents are outside this receipt's scope.
            digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_relative_to(root) and target.is_file() else None
            entries.append([name, "symlink", os.readlink(path), digest])
        elif path.is_file():
            h = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
            entries.append([name, bool(path.stat().st_mode & 0o111), h.hexdigest()])
        elif path.exists():
            raise ValueError("Submodules and non-file entries need a dedicated verification rule")
        else:
            entries.append([name, "deleted"])
    return {
        "head": head, "base": base_id, "changed_files": changed,
        "fingerprint": _digest({"verifier": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "root": str(root), "head": head, "base": base_id, "files": entries,
                                "index": hashlib.sha256(_git(root, "ls-files", "--stage", "-z")).hexdigest()}),
    }


def _command(root: Path, check: dict[str, Any], config: dict[str, Any]) -> list[str]:
    targets = check["targets"]
    if not all(_target(root, t).exists() for t in targets):
        raise ValueError("Selected check target is missing")
    runner = check["runner"]
    if runner == "bash":
        return ["bash", "--", *targets]
    if runner == "bash-syntax":
        return ["bash", "-n", "--", *targets]
    python = [sys.executable]
    if "python_project" in config:
        python = ["uv", "--directory", config["python_project"], "run", "--no-sync", "python"]
        # uv changes cwd to the project; keep test/script paths rooted at the repo.
        targets = [str(root / t) for t in targets]
    if runner == "pytest":
        return [*python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--", *targets]
    return [*python, *targets]


def _run(root: Path, command: list[str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MACOS_SCRIPTS_HOME": str(root)}
    # Child output may contain secrets. Do not persist or forward it as evidence.
    try:
        process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
    except OSError:
        return {"status": "ERROR", "exit_code": None, "duration_seconds": 0}
    try:
        try:
            code = process.wait(timeout=timeout)
            status = "PASS" if code == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            code, status = None, "TIMEOUT"
    finally:
        # Terminate descendants too, including a timed-out script's children.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    return {"status": status, "exit_code": code, "duration_seconds": round(time.monotonic() - started, 3)}


def _receipt_path(root: Path) -> Path:
    value = os.fsdecode(_git(root, "rev-parse", "--git-path", "mq-verification/receipt.json")).strip()
    path = Path(value)
    return path if path.is_absolute() else root / path


def _save(root: Path, result: dict[str, Any]) -> None:
    result["receipt_id"] = _digest(result)
    path = _receipt_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="receipt-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify(path: Path, *, base: str = "HEAD", plan_only: bool = False) -> dict[str, Any]:
    root = _root(path)
    before = _snapshot(root, base)
    config = _config(root)
    selected = [c for c in config["checks"] if any(
        fnmatch.fnmatchcase(f, pattern) for f in before["changed_files"] for pattern in c["paths"]
    )]
    uncovered = [f for f in before["changed_files"] if not any(
        fnmatch.fnmatchcase(f, pattern) for c in selected for pattern in c["paths"]
    )]
    # Validate every selected target before executing any check.
    commands = [_command(root, c, config) for c in selected]
    result: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA, **before, "status": "PLAN" if plan_only else "NO_CHANGES",
        "uncovered_files": uncovered, "checks": [],
        "not_verified": ["API credential validity", "ignored files and external dependencies", "unmatched files"],
    }
    for check, command in zip(selected, commands):
        item = {"id": check["id"], "runner": check["runner"], "targets": check["targets"],
                "timeout_seconds": check["timeout_seconds"]}
        if not plan_only:
            item.update(_run(root, command, check["timeout_seconds"]))
        result["checks"].append(item)
    if plan_only:
        return result
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    if before["fingerprint"] != _snapshot(root, base)["fingerprint"]:
        result["status"] = "STALE"
    elif any(c["status"] != "PASS" for c in result["checks"]):
        result["status"] = "FAIL"
    elif uncovered:
        result["status"] = "INCOMPLETE"
    elif selected:
        result["status"] = "PASS"
    _save(root, result)
    return result


def check_receipt(path: Path, *, base: str = "HEAD") -> dict[str, Any]:
    root = _root(path)
    try:
        result = json.loads(_receipt_path(root).read_text())
    except FileNotFoundError:
        return {"schema": RECEIPT_SCHEMA, "status": "MISSING"}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid verification receipt") from exc
    if not isinstance(result, dict) or result.get("schema") != RECEIPT_SCHEMA:
        raise ValueError("Unsupported verification receipt")
    unsigned = {k: v for k, v in result.items() if k != "receipt_id"}
    if result.get("receipt_id") != _digest(unsigned):
        raise ValueError("Receipt checksum mismatch")
    if result.get("fingerprint") != _snapshot(root, base)["fingerprint"]:
        return {**result, "status": "STALE"}
    return result
