"""Read owner-managed contracts. No private vocabulary or schema fallback."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from mq_agent.tools.agent_views import default_vault


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate(data: dict, schema: dict) -> None:
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(data)


def load_contracts(vault: Path | None = None) -> tuple[dict, dict]:
    root = (vault or default_vault()).expanduser()
    try:
        vocabulary = json.loads(
            (root / ".mq/skill-selection-vocabulary.json").read_text()
        )
        schemas = {
            name: json.loads((root / "schemas" / f"{name}.json").read_text())
            for name in (
                "skill-selection-vocabulary.v1",
                "mq.skill-profile.v1",
                "mq.skill-route.v1",
            )
        }
    except OSError as exc:
        raise ContractError(
            "SKS001_VOCABULARY_UNAVAILABLE",
            "Owner vocabulary or schema unavailable in mqobsidian.",
        ) from exc
    except (ValueError, UnicodeError) as exc:
        raise ContractError(
            "SKS002_VOCABULARY_INVALID", "Owner vocabulary or schema is not valid JSON."
        ) from exc
    try:
        for schema in schemas.values():
            Draft202012Validator.check_schema(schema)
        validate(vocabulary, schemas["skill-selection-vocabulary.v1"])
    except (SchemaError, ValidationError) as exc:
        raise ContractError(
            "SKS002_VOCABULARY_INVALID", "Owner vocabulary or schema is malformed."
        ) from exc
    return vocabulary, schemas


def reason(
    code: str, message: str, skill: str | None = None, target: str | None = None
) -> dict:
    return dict(code=code, skill=skill, target=target, message=message)
