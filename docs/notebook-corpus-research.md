# NotebookLM cross-notebook research

D6 adds synthesis above the bounded D5 evidence bundle. It does not create a
second retrieval path and it does not give the synthesizer authority over source
classification.

## Operator surface

```text
mq-agent notebook research "<question>" --catalog <catalog.json>
```

The command uses D4 ranking and D5 selective retrieval first, then asks the
configured Ollama model to propose a structured synthesis. The proposal is not
trusted as evidence. mq-agent validates every support reference against the D5
bundle before a result is accepted.

Useful bounds remain explicit:

```text
top-k                 20
max files              8
max bytes per file    64 KiB
max total bytes       512 KiB
excerpt              4,000 characters
```

These are D6 defaults, not permission to scan the archive.

## Cross-source authority

A common finding is accepted only when all of these are true:

1. every cited support item is a successfully fetched D5
   `claim_eligible=true` source;
2. at least two independent source documents support the finding;
3. the support spans at least two notebooks.

Independence is content-aware when the catalog has a digest. Two files carrying
the same `content_sha256` count as one source even when they have different
Drive item ids. When no digest was measured, the opaque Drive item identity is
the conservative fallback.

Derived and interaction material can never satisfy this requirement.

## Disagreements

D6 keeps conflicting source positions separate. A disagreement survives only
when it contains at least two source-supported positions backed by at least two
independent sources across at least two notebooks.

The implementation does not vote, average or select a winner.

## Derived interpretations

NotebookLM-generated interpretations remain a separate
`derived_interpretations` section and always carry
`claim_eligible=false`. A proposal that mixes a source item into a derived
interpretation is rejected rather than silently reclassified.

## Unanswered questions

The synthesizer may return unanswered questions and missing evidence. They are
reported as gaps, not filled from chat history or derived material.

If D5 cannot produce claim-eligible source evidence, D6 does not call the
synthesizer and returns the D5 failure state instead.

## Review candidate

A result can be written explicitly as a local review candidate:

```text
mq-agent notebook research "<question>" \
  --catalog <catalog.json> \
  --review-candidate-out .mq/notebook-corpus/review-candidate.json
```

This writes only the requested local JSON candidate. It does not write to
mqobsidian durable memory, decisions, learn records or promotion state.

## Runtime truth

`--scope live-runtime` keeps the D5 boundary: D6 returns
`DELEGATE_RUNTIME` and performs no corpus fetch or research synthesis. Current
runtime/code truth still belongs to current runtime/source tooling.

## Activation boundary

D6 implementation can be tested behind the existing activation gate, but
whole-archive activation remains blocked until:

1. a complete current D3 catalog exists;
2. the six frozen D4 queries pass over that complete catalog;
3. D5 retrieval over that catalog shows no authority/provenance violations.

Only then can D6 be described as active over the complete archive.
