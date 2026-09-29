from __future__ import annotations

import json

from mq_agent.notebook_corpus import build_from_document
from mq_agent.notebook_corpus_research import research_notebooks, write_review_candidate


runner = CliRunner()\n\n\nclass FakeFetcher:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def fetch_text(self, drive_item_id, mime_type, *, max_bytes):
        self.calls.append((drive_item_id, mime_type, max_bytes))
        return self.payloads[drive_item_id]


class FakeSynthesizer:
    def __init__(self, proposal):
        self.proposal = proposal
        self.calls = []

    def synthesize(self, question, evidence):
        self.calls.append((question, evidence))
        return self.proposal


def _ok(text):
    return {
        "status": "ok",
        "reason": None,
        "text": text,
        "bytes_fetched": len(text.encode("utf-8")),
        "truncated": False,
    }


def _catalog(*, duplicate_hash=False):
    document = {
        "corpus_key": "notebooklm-archive",
        "snapshot_at": "2026-09-29T00:00:00Z",
        "notebooks": [
            {"drive_item_id": "nb-a", "title": "MCP Python A"},
            {"drive_item_id": "nb-b", "title": "MCP Python B"},
        ],
        "items": [
            {
                "drive_item_id": "source-a",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "sources-a",
                "relative_path": "Sources/mcp-python-a.md",
                "title": "MCP Python source A",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "same" if duplicate_hash else "hash-a",
            },
            {
                "drive_item_id": "derived-a",
                "notebook_drive_item_id": "nb-a",
                "parent_drive_item_id": "artifacts-a",
                "relative_path": "Artifacts/mcp-python-a.md",
                "title": "MCP Python interpretation A",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-27T10:01:00Z",
                "origin_provider": "google-drive",
            },
            {
                "drive_item_id": "source-b",
                "notebook_drive_item_id": "nb-b",
                "parent_drive_item_id": "sources-b",
                "relative_path": "Sources/mcp-python-b.md",
                "title": "MCP Python source B",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-27T11:00:00Z",
                "origin_provider": "google-drive",
                "content_sha256": "same" if duplicate_hash else "hash-b",
            },
            {
                "drive_item_id": "derived-b",
                "notebook_drive_item_id": "nb-b",
                "parent_drive_item_id": "artifacts-b",
                "relative_path": "Artifacts/mcp-python-b.md",
                "title": "MCP Python interpretation B",
                "mime_type": "text/markdown",
                "size_bytes": 100,
                "modified_time": "2026-09-27T11:01:00Z",
                "origin_provider": "google-drive",
            },
        ],
    }
    catalog, _ = build_from_document(document)
    return catalog


def _fetcher():
    return FakeFetcher(
        {
            "source-a": _ok("MCP uses a client-server protocol."),
            "source-b": _ok("MCP uses a client-server protocol with capability negotiation."),
            "derived-a": _ok("NotebookLM says MCP is useful for tool integration."),
            "derived-b": _ok("NotebookLM summarizes MCP as a tool protocol."),
        }
    )


def test_common_finding_requires_two_independent_sources_across_notebooks():
    synth = FakeSynthesizer(
        {
            "common_findings": [
                {
                    "claim": "MCP uses a client-server protocol.",
                    "supporting_drive_item_ids": ["source-a", "source-b"],
                }
            ],
            "disagreements": [],
            "derived_interpretations": [],
            "unanswered_questions": [],
        }
    )

    report = research_notebooks(_catalog(), "MCP Python", _fetcher(), synth)

    assert report["status"] == "RESEARCH_READY"
    finding = report["common_findings"][0]
    assert finding["independent_source_count"] == 2
    assert finding["notebook_count"] == 2
    assert {row["drive_item_id"] for row in finding["support"]} == {
        "source-a",
        "source-b",
    }


def test_duplicate_source_hash_does_not_count_as_independent():
    synth = FakeSynthesizer(
        {
            "common_findings": [
                {
                    "claim": "Repeated copy should not become independent support.",
                    "supporting_drive_item_ids": ["source-a", "source-b"],
                }
            ],
            "disagreements": [],
            "derived_interpretations": [],
            "unanswered_questions": [],
        }
    )

    report = research_notebooks(
        _catalog(duplicate_hash=True),
        "MCP Python",
        _fetcher(),
        synth,
    )

    assert report["common_findings"] == []
    assert report["status"] == "INSUFFICIENT_CROSS_SOURCE_EVIDENCE"
    assert report["insufficient_support"][0]["reason"] == (
        "fewer_than_two_independent_sources"
    )


def test_derived_material_cannot_satisfy_common_finding_support():
    synth = FakeSynthesizer(
        {
            "common_findings": [
                {
                    "claim": "Derived repetition is not source corroboration.",
                    "supporting_drive_item_ids": ["source-a", "derived-b"],
                }
            ],
            "disagreements": [],
            "derived_interpretations": [],
            "unanswered_questions": [],
        }
    )

    report = research_notebooks(_catalog(), "MCP Python", _fetcher(), synth)

    assert report["common_findings"] == []
    rejected = report["insufficient_support"][0]
    assert rejected["reason"] == "fewer_than_two_independent_sources"
    assert [row["drive_item_id"] for row in rejected["support"]] == ["source-a"]


def test_disagreement_preserves_supported_positions():
    synth = FakeSynthesizer(
        {
            "common_findings": [],
            "disagreements": [
                {
                    "topic": "Transport guidance",
                    "positions": [
                        {
                            "claim": "Prefer stdio.",
                            "supporting_drive_item_ids": ["source-a"],
                        },
                        {
                            "claim": "Prefer HTTP.",
                            "supporting_drive_item_ids": ["source-b"],
                        },
                    ],
                }
            ],
            "derived_interpretations": [],
            "unanswered_questions": [],
        }
    )

    report = research_notebooks(_catalog(), "MCP Python", _fetcher(), synth)

    assert report["status"] == "RESEARCH_READY"
    disagreement = report["disagreements"][0]
    assert [row["claim"] for row in disagreement["positions"]] == [
        "Prefer stdio.",
        "Prefer HTTP.",
    ]
    assert disagreement["notebook_count"] == 2


def test_derived_interpretation_is_kept_separate_and_never_claim_eligible():
    synth = FakeSynthesizer(
        {
            "common_findings": [],
            "disagreements": [],
            "derived_interpretations": [
                {
                    "interpretation": "NotebookLM frames MCP as tool integration.",
                    "supporting_drive_item_ids": ["derived-a", "derived-b"],
                }
            ],
            "unanswered_questions": ["Which transport is current?"],
        }
    )

    report = research_notebooks(_catalog(), "MCP Python", _fetcher(), synth)

    assert report["derived_interpretations"][0]["claim_eligible"] is False
    assert {
        row["source_role"]
        for row in report["derived_interpretations"][0]["support"]
    } == {"derived"}
    assert report["unanswered_questions"] == ["Which transport is current?"]


def test_source_cannot_be_smuggled_into_derived_interpretation():
    synth = FakeSynthesizer(
        {
            "common_findings": [],
            "disagreements": [],
            "derived_interpretations": [
                {
                    "interpretation": "Wrongly labelled context.",
                    "supporting_drive_item_ids": ["source-a", "derived-b"],
                }
            ],
            "unanswered_questions": [],
        }
    )

    report = research_notebooks(_catalog(), "MCP Python", _fetcher(), synth)

    assert report["derived_interpretations"] == []
    assert report["insufficient_support"][0]["reason"] == "not_purely_derived_context"


def test_no_source_ready_bundle_never_calls_synthesizer():
    catalog = _catalog()
    catalog["items"] = [
        row for row in catalog["items"] if row["source_role"] != "source"
    ]
    synth = FakeSynthesizer(
        {
            "common_findings": [],
            "disagreements": [],
            "derived_interpretations": [],
            "unanswered_questions": [],
        }
    )

    report = research_notebooks(catalog, "MCP Python", _fetcher(), synth)

    assert report["status"] == "MISSING_SOURCE"
    assert synth.calls == []


def test_review_candidate_is_local_candidate_not_durable_memory(tmp_path):
    report = {
        "question": "MCP Python",
        "status": "RESEARCH_READY",
        "common_findings": [{"claim": "x"}],
        "disagreements": [],
        "source_evidence": [],
        "derived_interpretations": [],
        "unanswered_questions": [],
    }
    path = write_review_candidate(report, tmp_path / "candidate.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "candidate"
    assert "no automatic durable-memory promotion" in payload["note"]


def test_cli_live_runtime_delegates_without_drive_or_ollama_call(tmp_path, monkeypatch):
    monkeypatch.delenv("MQ_NOTEBOOK_DRIVE_ACCESS_TOKEN", raising=False)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(_catalog()), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "notebook",
            "research",
            "what does mq-agent do now",
            "--catalog",
            str(path),
            "--scope",
            "live-runtime",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "DELEGATE_RUNTIME"
    assert payload["retrieval"]["trace"]["fetched"] == 0
