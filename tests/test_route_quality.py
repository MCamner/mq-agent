"""Quality needs an exact, measured execution; fixtures never use live stores."""
import json

from mq_agent.tools.route_quality import complete_execution_quality


def execution(run_id="execution-1"):
    return {
        "schema": "mq.execution-outcome.v1", "run_id": run_id,
        "runtime": "agent", "task_class": "docs", "result": "PASS",
        "exit_status": "ok", "latency_ms": 1, "recorded_at": "2026-10-13T00:00:00Z",
        "completeness": {"status": "complete", "steps": [
            {"step": 1, "status": "complete", "source_item_count": 2,
             "executed_call_count": 2}]},
    }


def observation():
    return {"task_class": "docs-review", "application": "applied",
            "execution_run_id": "execution-1"}


def test_quality_requires_exact_valid_complete_execution(tmp_path):
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps([execution()]))
    included, excluded, _ = complete_execution_quality([observation()], source)
    assert included == [observation()]
    assert excluded == {}


def test_quality_fails_closed_for_bad_links_and_measurements(tmp_path):
    source = tmp_path / "mixed.jsonl"
    cases = [
        ([], "missing-execution"),
        ([execution(), execution()], "ambiguous-execution"),
        ([dict(execution(), latency_ms=-1)], "invalid-execution"),
        ([dict(execution(), task_class="audit")], "execution-task-class-mismatch"),
        ([dict(execution(), result="FAIL", exit_status="error")], "unsuccessful-execution"),
        ([{k: v for k, v in execution().items() if k != "completeness"}],
         "unmeasured-completeness"),
    ]
    for records, reason in cases:
        source.write_text("\n".join(json.dumps(item) for item in records))
        included, excluded, _ = complete_execution_quality([observation()], source)
        assert included == []
        assert excluded == {reason: 1}
    broken = execution()
    broken["completeness"]["steps"][0]["executed_call_count"] = 1
    source.write_text(json.dumps(broken))
    assert complete_execution_quality([observation()], source)[1] == {
        "inconsistent-completeness": 1}


def test_explicit_source_never_falls_back_to_canonical_execution_store(tmp_path, monkeypatch):
    canonical = tmp_path / "canonical.json"
    canonical.write_text(json.dumps(execution()))
    monkeypatch.setenv("MQ_AGENT_EXECUTION_OUTCOMES", str(canonical))
    explicit = tmp_path / "routes.json"
    explicit.write_text("[]")
    assert complete_execution_quality([observation()], explicit)[1] == {
        "missing-execution": 1}
    assert complete_execution_quality([observation()], None)[0] == [observation()]


def test_docs_review_quality_excludes_unlinked_pass_but_keeps_safety(tmp_path):
    from mq_agent.tools import model_routing

    route = model_routing._outcome(
        model_routing.inspect_route("Review README documentation"),
        attempted=True, model_output_received=True, schema_valid=True,
        verification_status="PASS", verification_checks=["evidence-grounded"],
    )
    route["application"] = "applied"
    route["selected_route"] = "approved-local"
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps([route]))
    review = model_routing.review_route_evidence("docs-review", source)
    assert review["verified_outcomes"] == 0
    assert review["unauthorized_writes"] == 1
    assert review["quality_population"]["exclusion_reasons"] == {
        "missing-execution-run-id": 1}


def test_partial_execution_is_explicitly_excluded(tmp_path):
    partial = execution()
    partial.update(result="FAIL", exit_status="error")
    partial["completeness"]["status"] = "partial"
    partial["completeness"]["steps"][0]["status"] = "partial"
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps(partial))
    assert complete_execution_quality([observation()], source)[1] == {
        "partial-completeness": 1}


def test_divergence_keeps_excluded_safety_failures_visible(tmp_path):
    from tests.test_route_divergence import _observation
    from mq_agent.tools.route_divergence import route_divergence

    route = _observation("local-shadow", status="FAIL", escalated=True,
                         escalation_reason="verification-failed")
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps(route))
    report = route_divergence(source)
    assert report["routes"] == {}
    assert report["behavioral_routes"]["local-shadow"]["execution"]["verification"]["FAIL"] == 1
    assert report["quality_population"]["excluded"] == 1


def test_invalid_duplicate_cannot_be_hidden_by_contract_split(tmp_path):
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps([execution(), dict(execution(), latency_ms=-1)]))
    assert complete_execution_quality([observation()], source)[1] == {
        "ambiguous-execution": 1}


def test_complete_requires_nonempty_unique_consistent_steps(tmp_path):
    source = tmp_path / "mixed.json"
    for steps, reason in [
        ([], "invalid-execution"),
        ([{"step": 1, "status": "complete"}, {"step": 1, "status": "complete"}],
         "inconsistent-completeness"),
        ([{"step": 1, "status": "complete", "source_item_count": 2}],
         "invalid-execution"),
        ([{"step": 1, "status": "skipped"}], "invalid-execution"),
    ]:
        record = execution()
        record["completeness"]["steps"] = steps
        source.write_text(json.dumps(record))
        assert complete_execution_quality([observation()], source)[1] == {reason: 1}


def test_only_observed_docs_producer_association_is_accepted(tmp_path):
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps(execution()))
    unsupported = dict(observation(), task_class="repo-review")
    advisory = dict(observation(), application="advisory")
    missing = {k: v for k, v in observation().items() if k != "execution_run_id"}
    assert complete_execution_quality([unsupported, advisory, missing], source)[1] == {
        "unsupported-task-class": 1, "not-applied": 1, "missing-execution-run-id": 1}


def test_docs_evidence_review_quality_uses_current_era_but_safety_keeps_history(tmp_path):
    from mq_agent.tools import model_routing
    from mq_agent.tools.analysis_cohort import current_era

    boundary = current_era().starts_at.isoformat()
    route = model_routing._outcome(
        model_routing.inspect_route("Review README documentation"),
        attempted=True, model_output_received=True, schema_valid=True,
        verification_status="PASS", verification_checks=["evidence-grounded"],
        execution_run_id="execution-1",
    )
    route.update(application="applied", recorded_at=boundary)
    old = dict(route, recorded_at="2026-01-01T00:00:00Z", selected_route="approved-local")
    advisory = dict(route, application="advisory")
    source = tmp_path / "mixed.json"
    source.write_text(json.dumps([route, old, advisory, execution()]))
    review = model_routing.review_route_evidence("docs-review", source)
    assert review["verified_outcomes"] == 1
    assert review["quality_population"]["exclusion_reasons"] == {
        "earlier-era": 1, "not-applied": 1}
    assert review["quality_population"]["era"] == current_era().name
    assert review["unauthorized_writes"] == 1
