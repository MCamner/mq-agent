"""Independent report expectations over isolated, schema-valid history."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mq_agent.tools.execution_efficiency import execution_efficiency

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def outcome(run_id="one", **fields):
    return {"schema": "mq.execution-outcome.v1", "run_id": run_id, "runtime": "agent",
            "task_class": "docs", "result": "PASS", "exit_status": "ok", "latency_ms": 100,
            "recorded_at": "2026-11-15T10:00:00Z", **fields}


def route(**fields):
    return {"schema": "mq.model-route-outcome.v1", "decision_id": "route-one",
            "task_class": "docs-review", "selected_route": "local-shadow", "local_model": "local-test",
            "authoritative_agent": "codex", "attempted": True, "model_output_received": True,
            "schema_valid": True, "verification": {"status": "PASS", "checks": []},
            "accepted_by_agent": False, "accepted_by_operator": False,
            "escalated": False, "escalation_reason": None,
            "recorded_at": "2026-11-15T10:00:00Z", **fields}


def write(path, records):
    path.write_text("".join(json.dumps(r)+"\n" for r in records))


def report(tmp_path, records, routing=(), **kwargs):
    source, routes = tmp_path/"executions.jsonl", tmp_path/"routes.jsonl"
    write(source, records)
    write(routes, routing)
    return execution_efficiency(source, routing_source=routes, now=NOW, **kwargs)


def test_missing_is_not_zero_and_partial_totals_are_not_full_totals(tmp_path):
    r = report(tmp_path, [outcome(tool_calls=0, tokens={"input": 12}, cost=0),
                          outcome("two", latency_ms=300)])
    m = r["execution"]["resources"]
    assert m["tool_calls"]["measured"] == 1
    assert m["tool_calls"]["missing"] == 1
    assert m["tool_calls"]["measured_total"] == 0
    assert m["tool_calls"]["total"] is None
    assert m["tokens_input"]["measured_total"] == 12
    assert m["tokens_output"]["measured"] == 0
    assert m["tokens_output"]["measured_total"] is None
    assert m["cost"]["measured_total"] == 0
    assert m["cost"]["total"] is None
    assert m["latency_ms"]["median"] == 200
    assert m["latency_ms"]["p90"] == 300
    assert r["execution"]["rework"]["status"] == "unavailable"


def test_quality_requires_measured_complete_success_not_just_pass(tmp_path):
    complete = {"status": "complete", "steps": [{"step": 1, "status": "complete"}]}
    partial = {"status": "partial", "steps": [{"step": 1, "status": "failed"}]}
    r = report(tmp_path, [outcome(), outcome("two", completeness=complete),
                          outcome("three", result="FAIL", exit_status="error", completeness=partial)])
    q = r["execution"]["quality"]
    assert q == {"reported_passes": 2, "reported_failures": 1, "reported_skipped": 0,
                 "completeness_measured": 2, "completeness_missing": 1,
                 "complete_successes": 1, "complete_success_rate": 0.5,
                 "complete_success_rate_denominator": 2}
    assert "score" not in r and r["recommendation"] is None


def test_empty_history_is_explicit_and_does_not_create_files(tmp_path):
    source, routes = tmp_path/"missing", tmp_path/"no-routes"
    r = execution_efficiency(source, routing_source=routes, now=NOW)
    assert r["status"] == "EMPTY"
    assert r["execution"]["outcomes"] == 0
    assert r["execution"]["resources"]["latency_ms"]["total"] is None
    assert r["routing"]["escalation_rate"] is None
    assert not source.exists() and not routes.exists()


def test_rotated_history_is_read_and_identical_run_ids_count_once(tmp_path):
    source = tmp_path/"executions.jsonl"
    old = outcome("old")
    write(Path(str(source)+".1"), [old])
    r = report(tmp_path, [old, outcome("new")])
    assert r["execution"]["outcomes"] == 2
    assert r["duplicates"]["identical"] == 1
    assert r["status"] == "DEGRADED"


def test_conflicting_run_ids_are_excluded_instead_of_arbitrarily_selected(tmp_path):
    r = report(tmp_path, [outcome(), outcome(latency_ms=500), outcome("valid")])
    assert r["execution"]["outcomes"] == 1
    assert r["duplicates"]["conflicting_ids"] == 1
    assert r["status"] == "DEGRADED"


def test_malformed_rows_and_timestamps_are_reported_without_raw_content(tmp_path):
    r = report(tmp_path, [outcome(), {"private-content": "secret-fixture"},
                          outcome("bad-time", recorded_at="not-a-timestamp")])
    assert r["execution"]["outcomes"] == 1
    assert r["status"] == "DEGRADED"
    assert len(r["issues"]) == 2
    assert "secret-fixture" not in json.dumps(r)


def test_time_windows_exclude_old_and_future_records(tmp_path):
    r = report(tmp_path, [outcome("old", recorded_at="2026-09-01T10:00:00Z"), outcome(),
                          outcome("future", recorded_at="2026-12-01T10:00:00Z")], since="7d")
    assert r["execution"]["outcomes"] == 1
    assert r["execution"]["newest_recorded_at"] == "2026-11-15T10:00:00+00:00"
    assert any("future" in issue for issue in r["issues"])


def test_routing_and_execution_task_classes_are_independent(tmp_path):
    r = report(tmp_path, [outcome(), outcome("ci", task_class="ci")],
               routing=[route(application="applied", execution_run_id="one"),
                        route(decision_id="other", escalated=True, escalation_reason="verification-failed")],
               task_class="docs")
    assert r["execution"]["outcomes"] == 1
    assert r["routing"]["observations"] == 2
    assert r["routing"]["escalated"] == 1
    assert r["routing"]["escalation_rate"] == 0.5
    assert r["routing"]["linked_selected_executions"] == 1
    assert r["routing"]["groups"][0]["task_class"] == "docs-review"
    assert all(g["task_class"] == "docs" for g in r["execution"]["cohorts"])


def test_cohorts_separate_runtime_model_commit_and_metric_scope(tmp_path):
    fingerprint = {"component": "mq-agent", "version": "1.37.0", "commit": "a"*40, "identity_quality": "verified"}
    r = report(tmp_path, [outcome(model="model-a", runtime_fingerprint=fingerprint),
                          outcome("b", model="model-b", runtime_fingerprint=fingerprint),
                          outcome("c", model="model-a", runtime_fingerprint={**fingerprint,"commit":"b"*40}),
                          outcome("d", model="model-a", runtime_fingerprint=fingerprint,
                                  events=[{"kind":"metrics-scope:mq-agent-local"}])])
    assert len(r["execution"]["cohorts"]) == 4


def test_report_never_rewrites_source_files(tmp_path):
    source, routes = tmp_path/"e.jsonl", tmp_path/"r.jsonl"
    write(source, [outcome()])
    write(routes, [route()])
    before={p:p.read_bytes() for p in [source,routes]}
    execution_efficiency(source, routing_source=routes, now=NOW)
    assert all(p.read_bytes()==content for p,content in before.items())


@pytest.mark.parametrize("options", [{"since":"yesterday"},{"task_class":"docs-review"}])
def test_invalid_execution_filters_are_rejected(tmp_path, options):
    with pytest.raises(ValueError):
        report(tmp_path, [], **options)


def test_cli_exposes_json_and_human_coverage(tmp_path, monkeypatch):
    from mq_agent.main import app
    source, routes = tmp_path/"e.jsonl", tmp_path/"r.jsonl"
    write(source, [outcome(recorded_at="2000-01-01T00:00:00Z")])
    write(routes, [])
    runner=CliRunner()
    args=["execution","efficiency","--source",str(source),"--routing-source",str(routes)]
    result=runner.invoke(app,[*args,"--json"])
    assert result.exit_code==0, result.output
    assert json.loads(result.stdout)["schema"]=="mq.execution-efficiency.v1"
    human=runner.invoke(app,args)
    assert human.exit_code==0, human.output
    assert "Quality" in human.stdout and "Resources" in human.stdout
    assert "missing" in human.stdout.lower()
    assert "unknown" in human.stdout.lower()


def test_routing_observation_ids_deduplicate_without_using_decision_id(tmp_path):
    r = report(tmp_path, [], routing=[route(run_id="first"), route(run_id="first"),
                                      route(run_id="second", escalated=True, escalation_reason="verification-failed")])
    assert r["routing"]["observations"] == 2
    assert r["routing"]["escalated"] == 1
    assert r["routing"]["duplicates"]["identical"] == 1
    assert r["status"] == "DEGRADED"


def test_conflicting_routing_identity_is_excluded_and_legacy_ids_are_unknown(tmp_path):
    r = report(tmp_path, [], routing=[route(run_id="conflict"),
                                      route(run_id="conflict", escalated=True, escalation_reason="verification-failed"),
                                      route()])
    assert r["routing"]["observations"] == 1
    assert r["routing"]["duplicates"]["conflicting_ids"] == 1
    assert r["routing"]["duplicates"]["missing_ids"] == 1


def test_mixed_metric_scope_has_cohort_values_without_misleading_combined_total(tmp_path):
    r = report(tmp_path, [outcome(tokens={"input":10}, tool_calls=1),
                          outcome("local", tokens={"input":20}, tool_calls=2,
                                  events=[{"kind":"metrics-scope:mq-agent-local"}])])
    assert r["execution"]["resources"]["tokens_input"]["measured"] == 2
    assert r["execution"]["resources"]["tokens_input"]["total"] is None
    assert r["execution"]["resources"]["tokens_input"]["measured_total"] is None
    assert sorted(c["resources"]["tokens_input"]["total"] for c in r["execution"]["cohorts"]) == [10,20]


def test_cli_reports_degraded_json_and_invalid_filter_exit_codes(tmp_path):
    from mq_agent.main import app
    source, routes = tmp_path/"e.jsonl", tmp_path/"r.jsonl"
    write(source,[{"invalid":"fixture"}])
    write(routes,[])
    args=["execution","efficiency","--source",str(source),"--routing-source",str(routes),"--json"]
    result=CliRunner().invoke(app,args)
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "DEGRADED"
    result=CliRunner().invoke(app,[*args,"--since","yesterday"])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["status"] == "ERROR"


def test_execution_without_required_id_is_rejected_before_linking(tmp_path):
    invalid=outcome()
    invalid.pop('run_id')
    r=report(tmp_path,[invalid,outcome('valid')],routing=[route(execution_run_id='valid'),route()])
    assert r['status']=='DEGRADED'
    assert r['execution']['outcomes']==1
    assert r['routing']['observations']==2
    assert r['routing']['linked_selected_executions']==1
    assert r['routing']['duplicates']['missing_ids']==2
