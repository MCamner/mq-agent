"""Test isolation for the evidence stores.

`MQ_AGENT_ROUTE_OUTCOMES` decides where an applied routing observation is
written, and its default is the real store in the user's home directory. Keeping
test runs out of it was a discipline — remember to set the variable — and a
discipline is not a property. It was broken once in practice: a debugging run
went to the production store and was later counted as real evidence. The agreed
rule is that history is never deleted or backfilled, so that mistake could not
be undone, only excluded by era.

This makes it a property for anything running under pytest. A manual
`docs-audit` still needs the variable set by hand; the suite is the half that
can be enforced.

The execution store is redirected for the same reason, and it turned out to need
it more. `test_the_suite_never_writes_to_the_operators_real_store` passed in a
full run and failed on its own: it was satisfied by an environment variable
another test happened to leave behind, not by anything guaranteeing the claim it
makes. A green check standing for something other than what it says is the
failure this whole line of work keeps finding.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest


#: Every environment variable naming a durable evidence store.
_EVIDENCE_STORES = {
    "MQ_AGENT_ROUTE_OUTCOMES": "route-outcomes.jsonl",
    "MQ_AGENT_EXECUTION_OUTCOMES": "execution-outcomes.jsonl",
}


@pytest.fixture(autouse=True, scope="session")
def _isolate_evidence_stores(tmp_path_factory) -> Iterator[None]:
    directory = tmp_path_factory.mktemp("evidence-stores")
    previous = {name: os.environ.get(name) for name in _EVIDENCE_STORES}
    for name, filename in _EVIDENCE_STORES.items():
        os.environ[name] = str(directory / filename)
    yield
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(autouse=True)
def _production_stores_are_unreachable() -> None:
    """Redirection is only worth anything if it actually points elsewhere."""
    for name, filename in _EVIDENCE_STORES.items():
        configured = os.environ.get(name)
        assert configured is not None, f"{name} was not redirected for tests"
        assert Path(configured) != Path.home() / ".mq-agent" / filename
