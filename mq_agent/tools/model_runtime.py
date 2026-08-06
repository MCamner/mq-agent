"""Ollama model runtime helpers for mq-agent."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_PROFILES: dict[str, str] = {
    "fast": "qwen3:4b-instruct",
    "review": "qwen3:4b-instruct",
    "planner": "qwen3:4b-instruct",
    "memory": "mq-learn",
}

DOCTOR_SMOKE_PROMPT = (
    "Review findings: version mismatch. Return one JSON object using your required keys. "
    "Use evidence [\"version mismatch\"] and should_store false."
)
DOCTOR_SMOKE_FIELDS = {
    "pattern_name", "pattern_type", "summary", "evidence",
    "recommended_action", "confidence", "should_store",
}
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


def models_config_path() -> Path:
    """Return the model runtime config path."""
    override = os.environ.get("MQ_AGENT_MODELS_CONFIG")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".mq-agent" / "models.json"


def default_models_config() -> dict[str, Any]:
    return {
        "current_profile": "fast",
        "profiles": DEFAULT_PROFILES.copy(),
    }


def load_models_config(path: Path | None = None) -> dict[str, Any]:
    """Load model profile config, falling back to defaults when missing."""
    config_path = path or models_config_path()
    if not config_path.exists():
        return default_models_config()
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        data = {}
    defaults = default_models_config()
    profiles = defaults["profiles"] | {
        str(key): str(value)
        for key, value in data.get("profiles", {}).items()
        if value
    }
    current = str(data.get("current_profile") or defaults["current_profile"])
    if current not in profiles:
        current = defaults["current_profile"]
    return {"current_profile": current, "profiles": profiles}


def save_models_config(config: dict[str, Any], path: Path | None = None) -> Path:
    """Persist model profile config."""
    config_path = path or models_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return config_path


def current_model(path: Path | None = None) -> dict[str, Any]:
    """Return the active profile and model."""
    config = load_models_config(path)
    profile = config["current_profile"]
    return {
        "profile": profile,
        "model": config["profiles"].get(profile),
        "config_path": str(path or models_config_path()),
        "profiles": config["profiles"],
    }


def switch_model(
    target: str,
    *,
    profile: str | None = None,
    approve: bool = False,
    path: Path | None = None,
) -> dict[str, Any]:
    """Switch current model profile or assign a model to a profile."""
    config = load_models_config(path)
    profiles: dict[str, str] = config["profiles"]
    requested_profile = profile or target

    if not approve:
        model = profiles.get(target, target)
        return {
            "changed": False,
            "profile": requested_profile,
            "model": model,
            "config_path": str(path or models_config_path()),
            "message": "dry-run; add --approve to write models config",
        }

    if profile:
        profiles[profile] = target
        config["current_profile"] = profile
    elif target in profiles:
        config["current_profile"] = target
    else:
        profiles["fast"] = target
        config["current_profile"] = "fast"

    written = save_models_config(config, path)
    current = current_model(written)
    current.update({"changed": True, "config_path": str(written)})
    return current


def list_ollama_models() -> dict[str, Any]:
    """List locally available Ollama models."""
    if not shutil.which("ollama"):
        return {
            "ok": False,
            "models": [],
            "detail": "ollama CLI not found",
            "hint": "install or start Ollama",
        }
    result = _ollama_command(["list"])
    if result.returncode != 0:
        return {
            "ok": False,
            "models": [],
            "detail": (result.stderr or result.stdout or "ollama list failed").strip(),
        }
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    names = [line.split()[0] for line in lines[1:] if line.split()]
    return {"ok": True, "models": names, "raw": result.stdout.strip()}


def _ollama_command(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    command = ["ollama", *args]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        detail = f"{' '.join(command)} timed out after {timeout}s"
        return subprocess.CompletedProcess(command, returncode=124, stdout="", stderr=detail)


def _ollama_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip() or DEFAULT_OLLAMA_HOST
    if "://" not in host:
        host = f"http://{host}"
    return host.rstrip("/")


def _ollama_generate(
    model: str,
    prompt: str,
    timeout: int,
    *,
    json_format: bool | dict[str, Any] = False,
    keep_alive: int | str = 0,
) -> dict[str, Any]:
    request_data: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }
    if json_format:
        request_data["format"] = json_format if isinstance(json_format, dict) else "json"
    body = json.dumps(request_data).encode("utf-8")
    request = urllib.request.Request(
        f"{_ollama_base_url()}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ollama_generate_json(model: str, prompt: str, timeout: int) -> dict[str, Any]:
    return _ollama_generate(model, prompt, timeout, json_format=True)


def _model_installed(model: str, installed: list[str]) -> bool:
    def aliases(name: str) -> set[str]:
        return {name, name.removesuffix(":latest")}

    requested = aliases(model)
    return any(requested & aliases(name) for name in installed)


def _mq_learn_modelfile_path() -> Path:
    mq_mcp_dir = Path(os.environ.get("MQ_MCP_DIR", Path.home() / "mq-mcp")).expanduser()
    return mq_mcp_dir / "models" / "ollama" / "Modelfile.mq-learn"


def _check_mq_learn_modelfile(model: str, installed: list[str]) -> dict[str, Any]:
    source_path = _mq_learn_modelfile_path()
    if not source_path.exists():
        return {
            "status": "WARN",
            "detail": "mq-mcp Modelfile.mq-learn not found; drift not checked",
            "source": str(source_path),
        }
    if not _model_installed(model, installed):
        return {"status": "FAIL", "detail": f"{model} is not installed", "source": str(source_path)}

    result = _ollama_command(["show", "--modelfile", model])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ollama show failed").strip()
        return {"status": "FAIL", "detail": detail, "source": str(source_path)}

    expected = source_path.read_text(encoding="utf-8")
    expected_parameters = {
        line.strip() for line in expected.splitlines() if line.strip().startswith("PARAMETER ")
    }
    installed_lines = {line.strip() for line in result.stdout.splitlines()}
    missing_parameters = sorted(expected_parameters - installed_lines)
    system_body = expected.split('SYSTEM """', 1)[-1].rsplit('"""', 1)[0].strip()
    system_matches = system_body in result.stdout
    if missing_parameters or not system_matches:
        return {
            "status": "FAIL",
            "detail": "installed mq-learn differs from repo Modelfile",
            "source": str(source_path),
            "missing_parameters": missing_parameters,
            "system_matches": system_matches,
        }
    return {"status": "PASS", "detail": "installed mq-learn matches repo parameters and system prompt", "source": str(source_path)}


def model_doctor(
    *,
    smoke: bool = True,
    timeout: int = 60,
    check_modelfile: bool = True,
) -> dict[str, Any]:
    """Run read-only diagnostics for the local Ollama model runtime."""
    items: list[dict[str, Any]] = []
    if not shutil.which("ollama"):
        return {
            "schema": "ollama_runtime_doctor.v1",
            "ok": False,
            "items": [{"check": "ollama-cli", "status": "FAIL", "detail": "ollama CLI not found"}],
            "profiles": {"configured": current_model()["profiles"], "missing": []},
            "smoke": {"status": "SKIPPED", "json_valid": False, "schema_valid": False},
        }

    version_result = _ollama_command(["--version"])
    version_ok = version_result.returncode == 0
    version = (version_result.stdout or version_result.stderr).strip()
    items.append({"check": "ollama-version", "status": "PASS" if version_ok else "FAIL", "detail": version})

    listed = list_ollama_models()
    installed = listed.get("models", []) if listed.get("ok") else []
    items.append({
        "check": "ollama-list",
        "status": "PASS" if listed.get("ok") else "FAIL",
        "detail": f"{len(installed)} model(s) installed" if listed.get("ok") else listed.get("detail", "failed"),
    })

    ps_result = _ollama_command(["ps"])
    ps_ok = ps_result.returncode == 0
    ps_lines = [line for line in ps_result.stdout.splitlines()[1:] if line.strip()]
    items.append({
        "check": "ollama-ps",
        "status": "PASS" if ps_ok else "FAIL",
        "detail": f"{len(ps_lines)} model(s) loaded" if ps_ok else (ps_result.stderr or "ollama ps failed").strip(),
    })

    profiles = current_model()["profiles"]
    missing = sorted({model for model in profiles.values() if not _model_installed(model, installed)})
    items.append({
        "check": "profile-models",
        "status": "PASS" if not missing else "FAIL",
        "detail": "all configured models are installed" if not missing else f"missing: {', '.join(missing)}",
    })

    if check_modelfile:
        modelfile = _check_mq_learn_modelfile(str(profiles["memory"]), installed)
        items.append({"check": "mq-learn-modelfile", **modelfile})
    else:
        modelfile = {"status": "SKIPPED", "detail": "disabled"}

    smoke_result: dict[str, Any] = {
        "status": "SKIPPED", "model": profiles["memory"], "json_valid": False, "schema_valid": False,
    }
    if smoke and _model_installed(str(profiles["memory"]), installed):
        try:
            response = _ollama_generate_json(str(profiles["memory"]), DOCTOR_SMOKE_PROMPT, timeout)
            payload = json.loads(str(response.get("response", "")))
            json_valid = isinstance(payload, dict)
            schema_valid = json_valid and DOCTOR_SMOKE_FIELDS == set(payload)
            smoke_result.update({
                "status": "PASS" if schema_valid else "FAIL",
                "json_valid": json_valid,
                "schema_valid": schema_valid,
                "detail": "valid mq-learn JSON schema" if schema_valid else "invalid mq-learn JSON schema",
            })
        except (json.JSONDecodeError, TimeoutError, urllib.error.URLError) as exc:
            smoke_result.update({"status": "FAIL", "detail": str(exc)})
        items.append({"check": "mq-learn-json-smoke", "status": smoke_result["status"], "detail": smoke_result.get("detail", "")})

    ok = all(item["status"] != "FAIL" for item in items)
    return {
        "schema": "ollama_runtime_doctor.v1",
        "ok": ok,
        "version": version,
        "installed_models": installed,
        "loaded_models": len(ps_lines),
        "profiles": {"configured": profiles, "missing": missing},
        "modelfile": modelfile,
        "smoke": smoke_result,
        "items": items,
    }


def bench_model(
    model: str | None = None,
    *,
    prompt: str = "Reply with OK.",
    timeout: int = 30,
    validate_schema: bool | None = None,
    keep_alive: int | str = 0,
) -> dict[str, Any]:
    """Benchmark one model through Ollama's API and return runtime metrics."""
    selected = model or str(current_model()["model"])
    if not shutil.which("ollama"):
        return {
            "schema": "ollama_model_benchmark.v1",
            "ok": False,
            "model": selected,
            "detail": "ollama CLI not found",
        }

    should_validate = selected.removesuffix(":latest").startswith("mq-learn") \
        if validate_schema is None else validate_schema
    try:
        response = _ollama_generate(
            selected,
            prompt,
            timeout,
            json_format=should_validate,
            keep_alive=keep_alive,
        )
    except (json.JSONDecodeError, TimeoutError, urllib.error.URLError) as exc:
        return {
            "schema": "ollama_model_benchmark.v1",
            "ok": False,
            "model": selected,
            "detail": str(exc),
        }

    output = str(response.get("response", "")).strip()
    parsed: Any = None
    json_valid = False
    try:
        parsed = json.loads(output)
        json_valid = isinstance(parsed, dict)
    except json.JSONDecodeError:
        pass
    schema_valid = json_valid and DOCTOR_SMOKE_FIELDS == set(parsed)

    def milliseconds(field: str) -> float:
        return round(float(response.get(field, 0)) / 1_000_000, 3)

    eval_count = int(response.get("eval_count", 0))
    eval_duration = int(response.get("eval_duration", 0))
    tokens_per_second = round(eval_count / (eval_duration / 1_000_000_000), 3) \
        if eval_count and eval_duration else 0.0
    metrics = {
        "total_duration_ms": milliseconds("total_duration"),
        "load_duration_ms": milliseconds("load_duration"),
        "prompt_eval_count": int(response.get("prompt_eval_count", 0)),
        "prompt_eval_duration_ms": milliseconds("prompt_eval_duration"),
        "eval_count": eval_count,
        "eval_duration_ms": milliseconds("eval_duration"),
        "tokens_per_second": tokens_per_second,
    }
    ok = bool(response.get("done", True)) and (not should_validate or schema_valid)
    return {
        "schema": "ollama_model_benchmark.v1",
        "ok": ok,
        "model": selected,
        "output": output,
        "done_reason": response.get("done_reason"),
        "metrics": metrics,
        "validation": {"json_valid": json_valid, "schema_valid": schema_valid},
        "keep_alive": keep_alive,
    }
