"""Resolve OpenAI credentials without exposing secret values."""
from __future__ import annotations

import getpass
import os
import subprocess
import sys
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Literal

DEFAULT_KEYCHAIN_SERVICE = "mq-openai-api-key"
SECURITY_BIN = "/usr/bin/security"


@dataclass(frozen=True)
class OpenAICredential:
    """Resolved credential and its non-secret provenance."""

    key: str | None = field(repr=False)
    source: Literal["env", "keychain", "missing"]


def resolve_openai_api_key(
    env: Mapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> OpenAICredential:
    """Resolve OPENAI_API_KEY from the process first, then macOS Keychain.

    The resolver never prints the secret. An explicitly inherited process value
    remains authoritative. On macOS, the fallback matches mq-mcp's `bridget`
    launcher: service `mq-openai-api-key`, account `$USER`, with optional
    `MQ_OPENAI_KEYCHAIN_SERVICE` and `MQ_OPENAI_KEYCHAIN_ACCOUNT` overrides.
    """
    values = os.environ if env is None else env

    inherited = values.get("OPENAI_API_KEY", "").strip()
    if inherited:
        return OpenAICredential(inherited, "env")

    active_platform = sys.platform if platform is None else platform
    if active_platform != "darwin":
        return OpenAICredential(None, "missing")

    service = (
        values.get("MQ_OPENAI_KEYCHAIN_SERVICE", "").strip()
        or DEFAULT_KEYCHAIN_SERVICE
    )
    account = (
        values.get("MQ_OPENAI_KEYCHAIN_ACCOUNT", "").strip()
        or values.get("USER", "").strip()
        or getpass.getuser()
    )

    try:
        result = subprocess.run(
            [
                SECURITY_BIN,
                "find-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return OpenAICredential(None, "missing")

    key = result.stdout.strip() if result.returncode == 0 else ""
    if not key:
        return OpenAICredential(None, "missing")
    return OpenAICredential(key, "keychain")


def install_openai_api_key(
    env: MutableMapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> OpenAICredential:
    """Install a Keychain-resolved key into this process only.

    Existing process-scoped credentials are never overwritten.
    """
    values = os.environ if env is None else env
    credential = resolve_openai_api_key(values, platform=platform)
    if credential.source == "keychain" and credential.key:
        values.setdefault("OPENAI_API_KEY", credential.key)
    return credential
