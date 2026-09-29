"""Freshness and replacement semantics for semantic repository memory."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import mq_agent.memory.semantic as sem


class FakeStoreFiles:
    def __init__(self, data):
        self.data = data

    def list(self, vector_store_id, **kwargs):
        return list(self.data.setdefault(vector_store_id, []))

    def retrieve(self, file_id, *, vector_store_id):
        return next(
            item
            for item in self.data.get(vector_store_id, [])
            if item.id == file_id
        )

    def update(self, file_id, *, vector_store_id, attributes):
        item = self.retrieve(file_id, vector_store_id=vector_store_id)
        item.attributes = dict(attributes)
        return item

    def delete(self, file_id, *, vector_store_id):
        self.data[vector_store_id] = [
            item
            for item in self.data.get(vector_store_id, [])
            if item.id != file_id
        ]
        return SimpleNamespace(id=file_id, deleted=True)


class FakeVectorStores:
    def __init__(self, data):
        self.files = FakeStoreFiles(data)
        self.stores = [
            SimpleNamespace(id=store_id, name=store_id)
            for store_id in data
        ]

    def retrieve(self, vector_store_id):
        return next(store for store in self.stores if store.id == vector_store_id)

    def list(self, **kwargs):
        return list(self.stores)


class FakeFiles:
    def __init__(self, filenames):
        self.filenames = filenames
        self.list_calls = 0
        self.retrieve_calls = 0

    def list(self, **kwargs):
        self.list_calls += 1
        return [
            SimpleNamespace(id=file_id, filename=filename)
            for file_id, filename in self.filenames.items()
        ]

    def retrieve(self, file_id):
        self.retrieve_calls += 1
        return SimpleNamespace(id=file_id, filename=self.filenames[file_id])


class FakeClient:
    def __init__(self, data, filenames):
        self.vector_stores = FakeVectorStores(data)
        self.files = FakeFiles(filenames)


def item(
    file_id,
    created_at,
    *,
    revision="",
    repo="macos-scripts",
    status="completed",
):
    attributes = {
        "repo": repo,
        "memory_type": "symbols",
        "source": "repo-signal",
    }
    if revision:
        attributes["source_revision"] = revision
        attributes["artifact_type"] = "symbol-memory"

    return SimpleNamespace(
        id=file_id,
        created_at=created_at,
        status=status,
        attributes=attributes,
    )


def _patch_identity(monkeypatch, client, revision="rev-new"):
    monkeypatch.setattr(sem, "_openai_client", lambda: client)
    monkeypatch.setattr(sem, "_source_revision", lambda repo: revision)
    monkeypatch.setattr(sem, "_repo_name", lambda repo: "macos-scripts")
    monkeypatch.setattr(sem, "repo_signal_available", lambda: True)
    monkeypatch.delenv("OPENAI_VECTOR_STORE_ID", raising=False)


def test_status_marks_duplicate_authoritative_generations_stale(
    monkeypatch,
    tmp_path,
):
    store = sem.CANONICAL_VECTOR_STORE_ID
    data = {
        store: [
            item("file_old", 10, revision="rev-old"),
            item("file_new", 20, revision="rev-new"),
        ]
    }
    client = FakeClient(
        data,
        {
            "file_old": "macos-scripts-symbol-memory.md",
            "file_new": "macos-scripts-symbol-memory.md",
        },
    )
    _patch_identity(monkeypatch, client)

    state = sem.status(tmp_path)

    assert state.reachable is True
    assert state.authoritative_active_count == 2
    assert state.freshness == "stale"
    assert state.status == "degraded"
    assert state.enabled is False


def test_status_is_ready_only_for_one_current_generation(monkeypatch, tmp_path):
    store = sem.CANONICAL_VECTOR_STORE_ID
    data = {store: [item("file_new", 20, revision="rev-new")]}
    client = FakeClient(data, {"file_new": "macos-scripts-symbol-memory.md"})
    _patch_identity(monkeypatch, client)

    state = sem.status(tmp_path)

    assert state.reachable is True
    assert state.authoritative_active_count == 1
    assert state.non_authoritative_retrieval_count == 0
    assert state.freshness == "fresh"
    assert state.fresh is True
    assert state.status == "ready"
    assert state.enabled is True


def test_single_unversioned_generation_is_unknown_not_ready(monkeypatch, tmp_path):
    store = sem.CANONICAL_VECTOR_STORE_ID
    data = {store: [item("file_old", 10)]}
    client = FakeClient(data, {"file_old": "macos-scripts-symbol-memory.md"})
    _patch_identity(monkeypatch, client)

    state = sem.status(tmp_path)

    assert state.authoritative_active_count == 1
    assert state.stored_source_revision == ""
    assert state.freshness == "unknown"
    assert state.status == "degraded"


def test_legacy_filename_fallback_loads_file_index_once(monkeypatch, tmp_path):
    store = sem.CANONICAL_VECTOR_STORE_ID
    legacy = SimpleNamespace(
        id="file_legacy",
        created_at=10,
        status="completed",
        attributes={},
    )
    unrelated = SimpleNamespace(
        id="file_other",
        created_at=11,
        status="completed",
        attributes={},
    )
    data = {store: [legacy, unrelated]}
    client = FakeClient(
        data,
        {
            "file_legacy": "macos-scripts-symbol-memory.md",
            "file_other": "unrelated.md",
        },
    )
    _patch_identity(monkeypatch, client)

    state = sem.status(tmp_path)

    assert state.authoritative_active_count == 1
    assert client.files.list_calls == 1
    assert client.files.retrieve_calls == 0


def test_build_pins_repo_signal_to_the_reported_store(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_VECTOR_STORE_ID", "vs_explicit")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sem.subprocess, "run", fake_run)
    sem.build(tmp_path, dry_run=True)

    assert seen["cmd"] == [
        "repo-signal",
        "semantic-upload",
        "--vector-store-id",
        "vs_explicit",
        "--dry-run",
    ]


def test_postcondition_wait_retries_until_detach_is_visible(
    monkeypatch,
    tmp_path,
):
    stale = sem._IdentityInspection(
        authoritative_files=(),
        authoritative_active_count=2,
        known_non_authoritative_retrieval_count=0,
        non_authoritative_scope_complete=True,
        freshness="stale",
        stored_source_revision="",
        latest_upload="",
    )
    fresh = sem._IdentityInspection(
        authoritative_files=(),
        authoritative_active_count=1,
        known_non_authoritative_retrieval_count=0,
        non_authoritative_scope_complete=True,
        freshness="fresh",
        stored_source_revision="rev-new",
        latest_upload="",
    )
    inspections = iter([stale, fresh])
    sleeps: list[float] = []

    monkeypatch.setattr(
        sem,
        "_inspect_identity",
        lambda *args, **kwargs: next(inspections),
    )
    monkeypatch.setattr(sem.time, "sleep", sleeps.append)

    after, outside_count, status = sem._wait_for_postcondition(
        object(),
        tmp_path,
        sem.CANONICAL_VECTOR_STORE_ID,
        "rev-new",
        attempts=5,
        delay_seconds=0.25,
    )

    assert after is fresh
    assert outside_count == 0
    assert status == "PASS"
    assert sleeps == [0.25]


def test_postcondition_wait_stays_bounded_when_state_never_converges(
    monkeypatch,
    tmp_path,
):
    stale = sem._IdentityInspection(
        authoritative_files=(),
        authoritative_active_count=2,
        known_non_authoritative_retrieval_count=0,
        non_authoritative_scope_complete=True,
        freshness="stale",
        stored_source_revision="",
        latest_upload="",
    )
    calls = []
    sleeps: list[float] = []

    def _inspect(*args, **kwargs):
        calls.append(True)
        return stale

    monkeypatch.setattr(sem, "_inspect_identity", _inspect)
    monkeypatch.setattr(sem.time, "sleep", sleeps.append)

    after, outside_count, status = sem._wait_for_postcondition(
        object(),
        tmp_path,
        sem.CANONICAL_VECTOR_STORE_ID,
        "rev-new",
        attempts=3,
        delay_seconds=0.25,
    )

    assert after is stale
    assert outside_count == 0
    assert status == "FAIL"
    assert len(calls) == 3
    assert sleeps == [0.25, 0.25]


def test_refresh_refuses_append_without_explicit_cleanup(monkeypatch, tmp_path):
    store = sem.CANONICAL_VECTOR_STORE_ID
    data = {store: [item("file_old", 10, revision="rev-old")]}
    client = FakeClient(data, {"file_old": "macos-scripts-symbol-memory.md"})
    _patch_identity(monkeypatch, client)

    def fail_if_uploaded(*args, **kwargs):
        raise AssertionError("must not upload")

    monkeypatch.setattr(sem, "build", fail_if_uploaded)

    result = sem.refresh(tmp_path, cleanup_stale=False)

    assert result.returncode == 2
    assert result.uploaded is False
    assert "cleanup-stale" in result.error


def test_cleanup_replaces_canonical_and_detaches_retired_macos_store(
    monkeypatch,
    tmp_path,
):
    store = sem.CANONICAL_VECTOR_STORE_ID
    retired = sem.RETIRED_VECTOR_STORE_IDS_BY_REPO["macos-scripts"][0]
    data = {
        store: [
            item("file_old_a", 10, revision="rev-old"),
            item("file_old_b", 11, revision="rev-older"),
        ],
        retired: [item("file_legacy", 5, revision="rev-legacy")],
    }
    filenames = {
        "file_old_a": "macos-scripts-symbol-memory.md",
        "file_old_b": "macos-scripts-symbol-memory.md",
        "file_legacy": "macos-scripts-symbol-memory.md",
        "file_new": "macos-scripts-symbol-memory.md",
    }
    client = FakeClient(data, filenames)
    _patch_identity(monkeypatch, client)

    def fake_build(*args, **kwargs):
        data[store].append(item("file_new", 30))
        return subprocess.CompletedProcess(
            [],
            0,
            "# OpenAI Vector Store Upload\nOpenAI file: \x60file_new\x60\n",
            "",
        )

    monkeypatch.setattr(sem, "build", fake_build)

    result = sem.refresh(tmp_path, cleanup_stale=True)

    assert result.returncode == 0
    assert result.postcondition_status == "PASS"
    assert result.authoritative_active_count == 1
    assert result.non_authoritative_retrieval_count == 0
    assert result.freshness == "fresh"
    assert {entry.split(":")[-1] for entry in result.detached} == {
        "file_old_a",
        "file_old_b",
        "file_legacy",
    }
    assert [entry.id for entry in data[store]] == ["file_new"]
    assert data[retired] == []
    assert data[store][0].attributes["source_revision"] == "rev-new"


def test_cleanup_never_deletes_underlying_openai_file_objects(monkeypatch, tmp_path):
    store = sem.CANONICAL_VECTOR_STORE_ID
    data = {store: [item("file_old", 10, revision="rev-old")]}
    filenames = {
        "file_old": "macos-scripts-symbol-memory.md",
        "file_new": "macos-scripts-symbol-memory.md",
    }
    client = FakeClient(data, filenames)
    _patch_identity(monkeypatch, client)

    def fake_build(*args, **kwargs):
        data[store].append(item("file_new", 30))
        return subprocess.CompletedProcess(
            [],
            0,
            "OpenAI file: \x60file_new\x60\n",
            "",
        )

    monkeypatch.setattr(sem, "build", fake_build)

    result = sem.refresh(tmp_path, cleanup_stale=True)

    assert result.returncode == 0
    assert client.files.filenames["file_old"] == "macos-scripts-symbol-memory.md"
