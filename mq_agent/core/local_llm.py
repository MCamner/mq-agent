"""Native local chat transport; errors never select a cloud provider."""
from __future__ import annotations

import json
import os
import urllib.request
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse


class OllamaClient:
    """Small chat-completions interface for the planner/reviewer contracts.

    Use native /api/chat: Ollama's compatibility endpoint can ignore think=false,
    consuming the output budget on reasoning and returning empty content.
    """

    def __init__(self, timeout: int = 180):
        self.timeout = timeout
        self.chat = SimpleNamespace(completions=self)

    def create(self, *, model: str, messages: list[dict[str, Any]],
               max_tokens: int = 2048, temperature: float = 0.2,
               response_format: dict[str, Any] | None = None) -> Any:
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
        if "://" not in host:
            host = "http://" + host
        parsed = urlparse(host)
        if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError("Local model endpoint must be loopback HTTP")
        payload: dict[str, Any] = {
            "model": model, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": temperature, "num_ctx": 16384,
                        "num_predict": max_tokens, "seed": 42},
        }
        if response_format:
            if response_format.get("type") == "json_schema":
                payload["format"] = response_format["json_schema"]["schema"]
            else:
                payload["format"] = "json"
        request = urllib.request.Request(
            host.rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read())
        if body.get("error") or not body.get("done") or body.get("done_reason") == "length":
            raise ValueError("Local model returned incomplete output")
        content = body.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Local model returned empty output")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
