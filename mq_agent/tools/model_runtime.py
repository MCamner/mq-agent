"""Ollama model runtime helpers for mq-agent."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_PROFILES: dict[str, str] = {
    "fast": "qwen3",
    "review": "qwen3",
    "planner": "qwen3",
    "memory": "mq-learn",
}


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
    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return {
            "ok": False,
            "models": [],
            "detail": (result.stderr or result.stdout or "ollama list failed").strip(),
        }
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    names = [line.split()[0] for line in lines[1:] if line.split()]
    return {"ok": True, "models": names, "raw": result.stdout.strip()}


def bench_model(
    model: str | None = None,
    *,
    prompt: str = "Reply with OK.",
    timeout: int = 30,
) -> dict[str, Any]:
    """Run a small Ollama benchmark prompt against the selected model."""
    selected = model or str(current_model()["model"])
    if not shutil.which("ollama"):
        return {"ok": False, "model": selected, "detail": "ollama CLI not found"}
    result = subprocess.run(
        ["ollama", "run", selected, prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (result.stdout or result.stderr).strip()
    return {
        "ok": result.returncode == 0,
        "model": selected,
        "returncode": result.returncode,
        "output": output,
    }
