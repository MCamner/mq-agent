"""What an older mq-agent does with a record a newer one wrote.

`mq.execution-outcome.v1` gained an optional `runtime_fingerprint`
(mqobsidian DEC-006). The field is optional, so every record written before it
stays valid — that is backward compatibility, and it holds.

Forward compatibility does not, and cannot: the contract is closed with
`additionalProperties: false`, so a schema that predates the field rejects a
record carrying it. The evidence store is append-only and shared by whatever
mq-agent is installed, so an operator who rolls back, or who has two copies on
one machine, reads new records with an old schema.

DEC-006 requires this to be tested before any producer writes the field, and
names `_split_contracts` as the seam. The point is not that the incompatibility
is avoidable. It is that the reader should not describe it as corruption.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from mq_agent.tools import model_routing
from mq_agent.tools.execution_outcome import SCHEMA_FILE as EXECUTION_SCHEMA_FILE
from mq_agent.tools.execution_outcome import build_execution_outcome


def _schema() -> dict[str, Any]:
    return json.loads(model_routing._schema_path(EXECUTION_SCHEMA_FILE).read_text("utf-8"))


def _older_schema() -> dict[str, Any]:
    """This contract as it stood before the fingerprint was added.

    Derived from the current file rather than pinned as a fixture, so it stays
    an accurate 'one version back' as the contract keeps evolving.
    """
    schema = _schema()
    schema["properties"].pop("runtime_fingerprint", None)
    return schema


def _newer_record() -> dict[str, Any]:
    record = build_execution_outcome(
        runtime="agent",
        task_class="task",
        result="PASS",
        exit_status="ok",
        latency_ms=12,
    )
    record["runtime_fingerprint"] = {
        "component": "mq-agent",
        "version": "1.29.0",
        "commit": "a" * 40,
        "identity_quality": "verified",
    }
    return record


@pytest.fixture
def older_reader(monkeypatch):
    """Make `_split_contracts` read with a schema that predates the field."""
    older = Draft202012Validator(_older_schema())
    real = model_routing._validator

    def _pick(name: str) -> Draft202012Validator:
        return older if name == EXECUTION_SCHEMA_FILE else real(name)

    monkeypatch.setattr(model_routing, "_validator", _pick)


# --- the compatibility that does hold --------------------------------------


def test_a_record_without_the_field_is_read_by_a_newer_schema() -> None:
    """Backward compatibility, which is what `optional` buys."""
    today = build_execution_outcome(
        runtime="agent", task_class="task", result="PASS", exit_status="ok", latency_ms=12
    )

    assert list(Draft202012Validator(_schema()).iter_errors(today)) == []


def test_the_field_is_optional_in_the_vendored_contract() -> None:
    assert "runtime_fingerprint" not in _schema()["required"]


# --- the compatibility that does not ---------------------------------------


def test_an_older_schema_rejects_a_newer_record(older_reader) -> None:
    """The cost, stated. A closed contract cannot accept a field it does not
    declare, and no version bump would change that — an older reader does not
    know a new schema identity either."""
    _, execution, invalid = model_routing._split_contracts([_newer_record()])

    assert execution == []
    assert invalid == 1


def test_the_older_reader_still_reads_its_own_records(older_reader) -> None:
    """The rejection is confined to the newer record. A mixed store is not
    wholly unreadable, which is what makes the miscount easy to miss."""
    mine = build_execution_outcome(
        runtime="agent", task_class="task", result="PASS", exit_status="ok", latency_ms=12
    )

    _, execution, invalid = model_routing._split_contracts([mine, _newer_record()])

    assert len(execution) == 1
    assert invalid == 1


# --- the part that is a decision, not a fact -------------------------------


def test_a_newer_record_is_still_recognisably_an_execution_outcome() -> None:
    """It is not junk, and it does not look like junk.

    `_split_contracts` states its own principle: an execution record found in a
    routing source "is a valid record of another contract, not a broken one —
    counting it as invalid would make a healthy store look corrupt and bury
    real corruption in noise." A record from a newer version of this contract
    is the same situation, and today it is counted as corruption.

    This test records that gap rather than asserting it away. Whether the
    reader should grow a third classification is a consumer-policy decision
    DEC-006 deliberately left open; what is settled is that the store is
    append-only, so the record will be there either way.
    """
    record = _newer_record()

    assert record["schema"] == "mq.execution-outcome.v1"
    assert set(record) - set(_older_schema()["properties"]) == {"runtime_fingerprint"}


def test_nothing_writes_the_field_yet() -> None:
    """DEC-006's sequencing: the reader question is answered before a producer
    creates records that ask it."""
    written = build_execution_outcome(
        runtime="agent", task_class="task", result="PASS", exit_status="ok", latency_ms=12
    )

    assert "runtime_fingerprint" not in written
