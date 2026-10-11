# Broader Repo-review Retrieval Evidence Implementation Plan

## Goal

Measure repo-review retrieval across more operator-authored cases before
proposing automatic agent integration.

## Owner repo

mq-agent.

## Secondary repos

mq-mcp supplies active semantic search. No secondary repository changes.

## Architecture boundary

- mq-agent owns candidate discovery, fixture-backed measurement and reporting.
- mq-mcp owns the active semantic search adapter and execution boundary.
- Notebook relevance labels belong to the operator.
- mqobsidian remains durable memory rather than live measurement truth.

## Verified starting point

Runtime `8f3b457afbab96d7aa1edad6ba79d09bcf2176a0` passed one bounded
repo-review/keyword consumption and rollback validation. The receipt was
revoked. That validates runtime mechanics, not general retrieval quality.
Existing suite, discovery, ablation and admission contracts already support
multiple cases; no new runtime implementation is required for this phase.

## Non-goals

- Automatic agent integration or issuing another consumption receipt.
- Altering RRF/top-k, or relabelling cases to obtain a desired result.
- Treating titles, channel exclusivity or candidate overlap as relevance labels.
- Inventing a statistically justified promotion threshold from a small sample.

## Approval gates

- Before plan/local preparation writes: no; requested by the operator.
- Before relevance fixtures: operator supplies or confirms labels after review.
- Before commit or push/merge: separate authorization for this change.
- Before optional runtime consumption: a new exact receipt and explicit budget.
- Before deletion/settings changes: explicit authorization.

## Test gates

```bash
bash scripts/check-docs-consistency.sh
uv run python tools/generate_command_reference.py --check
git diff --check
```

Measurement gates appear below. They use existing CLI commands; no code change
or new test suite is required merely to prepare operator inputs.

## Rollback

Revert only this documentation change through the usual PR flow. Retain local
candidate pools and all persisted evidence; do not delete or rewrite history.

### Task 1: Freeze the question set

**Files:** local ignored `.mq/hybrid-challenge/repo-review-expansion/QUESTIONS.md`.

Ask the operator for 3–5 real repo-review questions and the answer each should
support. Record task scope and question wording before discovery. Keep the
existing measured case separately as a historical control. New queries are
local input only; publish hashes and compact conclusions rather than raw input.
Do not select solely for expected keyword gains. Include common review needs,
active-only-sufficient cases and ambiguous/off-topic outcomes in the report.

**Expected result:** operator-confirmed questions, fixed top-k=10, and no labels.

### Task 2: Collect candidate pools and review sources

**Files:** local ignored `repo-review-expansion/<case-id>-candidates.json` and
`repo-review-expansion/REVIEW.md` beneath `.mq/hybrid-challenge/`.

For each confirmed question, run existing discovery against the current catalog:

```bash
uv run mq-agent memory hybrid-evidence challenge-candidates "$REVIEW_QUERY" \
  --catalog .mq/notebook-corpus/catalog.json --no-codegraph --top-k 10 --json
```

Omitting a semantic index keeps Notebook vector out of this keyword-focused
discovery. Retain the exact output locally. Record catalog fingerprint and
active availability. Separate derivative slides from logical source documents;
apply the existing diversity rule from `.mq/hybrid-challenge/EXCLUSIONS.md`.
Document unavailable, duplicate-dominated and off-topic pools with reasons.
Do not silently discard low-gain or active-only-ceiling cases.

The operator reviews actual source material and supplies exact expected,
contradicted and stale references. Record unjudged references explicitly in the
local worksheet; they are not automatically irrelevant. Candidate discovery
reports optional references plus active identities, not a complete independently
judged relevance universe. Review baseline sources too and state pool limits.

**Expected result:** source-reviewed labels with provenance; no inferred labels.

### Task 3: Build and measure the frozen suite

**Files:** local ignored `repo-review-expansion/suite.json` and per-case fixtures.

Use `mq.hybrid-retrieval-suite.v1`, `task_class=repo-review`, top-k=10,
`notebook_keyword=true`, `notebook_vector=false`, `codegraph=false`, and catalog
`../../notebook-corpus/catalog.json` relative to the suite. Use the existing
fixture schema and exact reviewed refs. Leave `challenge_target` unset for
ordinary coverage cases; do not require every case to be discriminating.

```bash
uv run mq-agent memory hybrid-evidence ablate \
  .mq/hybrid-challenge/repo-review-expansion/suite.json --no-write --json
```

The fixed ablation matrix runs all seven variants; variants can override suite
channel flags. A missing semantic index makes enabled vector retrieval
unavailable; enabled CodeGraph variants can use the default runtime even without
an explicit root. Record actual availability for every variant and compare the
active-only baseline with the notebook-keyword singleton. Do not interpret
overall matrix status as proof of unavailable channels or change the matrix to
manufacture a PASS.

Report per-case precision, recall, contradiction/stale rates, token estimates,
channel latency, availability and delta versus baseline. Preserve regressions
and zero gains. These are fixture/pool-relative measurements and total channel
latencies, not end-to-end incremental overhead or a general safety guarantee.

After operator review of dry-run results, persist the unchanged suite with the
same command without `--no-write`; verify with `ablation-status <ablation-id>`.
Admission remains a separate existing evidence gate, not runtime authorization.

**Expected result:** verified measured evidence plus candid coverage limitations.

### Task 4: Report and decide the next design step

**Files:** `ROADMAP.md` and this plan; reference existing runtime consumption plan.

Summarize coverage, evidence IDs, unavailable variants and per-case outcomes.
Ask whether evidence warrants an agent-integration design. Do not declare this
task complete while questions or source labels remain unreviewed. Automatic
integration still requires explicit task-class mapping, outcome correlation and
new content-bound approval.

## Current status

The operator supplied five questions before discovery on 2026-10-11, prioritizing
cases 1, 3 and 5. All five keyword discovery runs returned PASS, with active
search AVAILABLE and ten keyword candidates each. Vector was not configured and
CodeGraph was disabled for this first discovery phase. Exact questions, complete
candidate pools and the source-review worksheet remain in ignored local files.

Many candidate titles appear outside the intended MQ topic; this is a metadata
observation, not a source-reviewed relevance verdict. All pools are retained.
Source review is complete. Labels were drafted with AI assistance, then the
operator reviewed the decisive sources and reached the same judgment: one
expected reference (review-2-03) and 49 reviewed-irrelevant candidates; no
contradicted or stale references. Active identities remain unjudged because
they are digests of whole active responses, not reviewable source documents.

The frozen suite (`sha256:964b65a4d8d46135d2b19f2ec91259eac0c576fe1dfd23593cd0547c84621767`)
was persisted as ablation
`sha256:7e4d6cc8e830eb026dfce9835c7c597ee70978225b6c3135f92ade9a4adb6808`;
`ablation-status` returned VERIFIED. Overall status is INSUFFICIENT_EVIDENCE
because the active-only baseline disables every optional channel.

| Variant | Mean precision | Mean recall | Token delta vs active |
|---|---|---|---|
| active-only baseline | 0.0 | 0.0 | 0 |
| notebook-keyword | 0.02 | 1.0 | +1,761.2 |
| codegraph | 0.0 | 0.0 | +5,476.4 |

Notebook vector was not configured, so vector variants equal their non-vector
counterparts. Read these numbers narrowly:

- Mean recall 1.0 comes from review-2 alone; the four cases without expected
  references have undefined recall and are excluded from the mean.
- Baseline precision 0.0 counts unjudged active identities as non-expected. It is
  not a measured relevance verdict and does not show keyword beats active.
- Keyword returned one answer-bearing source in 50 reviewed candidates, at about
  1,760 additional estimated tokens per question. Four of five cases had none.

This evidence does not support an automatic agent-integration design. No new
consumption receipt was issued and RRF/top-k are unchanged.

### Correction after the evaluation

The persisted ablation correctly measures the keyword implementation as it was
then. After the evaluation a concrete ranking defect was identified: Swedish
function words were missing from `_STOP_WORDS` and could therefore contribute
to the match score and lift irrelevant Swedish titles. The corpus does contain
MQ-relevant material, so the result must not be read as evidence that such
material is missing. The fix adds Swedish function words only; scoring weights,
top-k, RRF, fusion and fallback are unchanged. The keyword channel still matches
exact title tokens only, so other limits remain. The effect of the fix has not
been re-measured; that requires a new frozen candidate collection and new
labels, and is a separate decision.

### Re-measurement after the stop-word fix

A new candidate collection ran on runtime
`eaaccce8627ac2b5bab5d05017ac14a1a76e0ee2` (PR #374) with the same five
questions, unchanged, and the same catalog
(`sha256:20bc31ea1ff2773d6ecde0747ae8ab2e97ecf4449471f64aee4f429a85f8ad59`).
It was stored separately from the first collection; earlier labels were not
reused. All five pools passed the source-diversity check. The new pools were
labelled from scratch with AI-assisted source review, then operator-confirmed:
10 expected and 40 reviewed-irrelevant references, with no contradicted or stale
references. Expected references were content files; their `metadata.json`
siblings were labelled irrelevant. Active identities remain unjudged.

Ablation `sha256:0f53f3f98fe9edc602e6c76a3407a113c21f6697079a7adeb7de9a85dda16abc`
was persisted and `ablation-status` returned VERIFIED. The earlier ablation
`sha256:7e4d6cc8…` is unchanged.

| Variant | Mean precision | Mean recall | Token delta vs active |
|---|---|---|---|
| active-only baseline | 0.0 | 0.0 | 0 |
| keyword, before fix | 0.02 | 1.0 (1 measurable case) | +1,761.2 |
| keyword, after fix | 0.18 | 0.889 (3 measurable cases) | +1,553.4 |
| keyword+codegraph, after fix | 0.08 | 0.356 | +7,029.8 |

Per case after the fix: review-1 found 2 of 3 expected references (the third was
keyword rank 10 and fell outside the fused top-10 next to the active result);
review-2 found 5 of 5; review-5 found 2 of 2; review-3 and review-4 had no
expected references in their pools. Those two pools still matched on single
exact title tokens ("closed", "version") and returned off-topic material.

Read narrowly:

- The stop-word defect was real and material for these questions: answer-bearing
  references rose from 1 to 9 of 50 with the same questions and catalog.
- Exact title-token matching remains a separate limit; it is not addressed here.
- Recall averages three cases; baseline precision still counts unjudged active
  identities as non-expected and is not a relevance verdict.
- The suite file is byte-identical to the first run (same questions and fixture
  names), so its digest does not distinguish the two label sets; the per-case
  fixture digests in the evidence records do.
- Adding CodeGraph displaces Notebook references within top-10 for this task class.

This is a before/after comparison on five questions, not a general quality
measurement. It does not by itself justify automatic agent integration. No
consumption receipt was issued and RRF/top-k are unchanged.
