# Execution efficiency

`mq-agent execution efficiency` reads existing execution and routing history.
It separates runtime completion, resources and measurement coverage so that a
fast or cheap run cannot silently become a claim of better answer quality.
It never invokes a model, writes evidence or changes a routing/feedback policy.

```bash
mq-agent execution efficiency
mq-agent execution efficiency --since 30d --task-class docs --json
mq-agent execution efficiency --source executions.jsonl --routing-source routes.jsonl --json
```

The default sources are the existing `MQ_AGENT_EXECUTION_OUTCOMES` and
`MQ_AGENT_ROUTE_OUTCOMES` paths. Execution history includes the current file and
its three retained rotations. Explicit sources accept JSON or JSONL. Missing
files yield empty populations without creating directories or files.

## Quality

The report distinguishes declared `PASS`/`FAIL`/`SKIPPED` from measured complete
successful execution: `completeness.status=complete`, `result=PASS` and
`exit_status=ok`. The complete-success fraction uses records with measured
completeness as its denominator, including partial/failed executions. Historical
records without completeness are shown as missing, never upgraded to complete.

This measures whether runtime work finished, not whether a model's answer was
correct or an operator accepted it. Use the existing review/Feedback Engine
quality evidence for that separate question.

## Resources and coverage

For latency, tool calls, retries, fallbacks, token input/output and cost:

- `measured` and `missing` state the population behind each value.
- `measured_total` is a subtotal of only the measured records.
- `total` exists only when the whole selected population measured that field.
- `median` and nearest-rank `p90` describe the measured subset.
- Empty/unmeasured values are `null`, rendered as `unknown`.
- A measured zero is retained as zero.

Cost uses the producer's recorded numeric units. The current contract supplies
no currency field; this report adds no price assumptions, dollar labels or
currency conversion. Missing cost stays unknown. Retry counts are not rework:
there is no explicit rework signal in the current execution contract, so rework
is reported as unavailable.

Cohorts separate execution task class, runtime, model, producer version/commit
and measurement scope. Missing identity remains unknown. These are descriptive
populations, not randomized comparisons or route recommendations. Token and
tool-call totals/percentiles are suppressed across mixed scopes; JSON cohorts
retain their own measured values.

## New runtime measurement boundary

New records can carry the existing event marker
`metrics-scope:mq-agent-local`. It identifies these measurement boundaries:

- Executor/YAML dispatch counts actual registered tool invocation attempts,
  including failures and fan-out. Skips, denied steps and dry runs are not calls.
- Planner/Verifier count only provider-reported `prompt_tokens` and
  `completion_tokens`. Native Ollama exposes its actual `prompt_eval_count` and
  `eval_count` through the same interface.
- A token direction is emitted only if every observed model call reports it.
  Missing usage, provider exceptions or known unsupported local model paths
  leave the affected total absent rather than publishing a partial run total.
- Swarms aggregate observable child scopes into their existing single outcome;
  unsupported executed children make the corresponding totals unavailable.
- Workflow Runner reports dispatches attempted during the current run, including
  failure/timeout, rather than summing historical attempts on resumed steps.
  Each emitted execution outcome describes the current operator invocation and
  its duration; it is not a cumulative workflow-lifetime total.

These are mq-agent orchestration measurements. They exclude backend model/tool
work inside mq-mcp, SDK-internal retries, and external Codex/Claude sessions.
Legacy measurements without a scope marker remain `unspecified`. No new cost,
rework or retry value is invented. Existing shared schemas and policies remain
unchanged.

## Routing population and provenance

Routing classes such as `docs-review` are independent of execution classes such
as `docs`. The execution `--task-class` filter does not relabel or filter routing
observations. The same time window applies to both populations. The report shows
routing escalations separately and counts links to selected executions only
through an already recorded `execution_run_id`; it never reconstructs links.

Routing groups retain the declared route and `application` (`applied`, `shadow`,
`advisory`, or `unreported`). Historical routing counts do not establish current
implementation quality or permit promotion. Use `route divergence` for the
existing era-aware quality population and `route readiness` for its own gates.

Identical duplicate execution run IDs count once; conflicting versions of one
run ID are excluded. Routing uses its observation `run_id` in the same way;
`decision_id` is not a unique observation identity. Legacy routing records
without `run_id` retain unknown deduplication coverage, disclosed as
`routing.duplicates.missing_ids`; no identity is reconstructed.
Invalid records/timestamps and future records are reported
without dumping raw content. No record is repaired, backfilled or rewritten.
Other valid contracts found in a source are counted separately and ignored.

## Exit status

- `0`: `OK` or `EMPTY`; emptiness grants no execution or promotion right.
- `1`: `DEGRADED`; issues are present in the report and must be inspected.
- `2`: invalid options or a source that cannot be read.

Reports remain read-only in every state. Tests and experimental executions must
use scratch evidence paths; acceptance fixtures are not production feedback or
routing evidence.
