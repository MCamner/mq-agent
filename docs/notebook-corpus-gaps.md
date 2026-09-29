# NotebookLM interaction-history and research-gap analysis

D7 uses interaction exports to describe **what has been asked**, not what is
true. It is a read-only analysis layer over the D3 catalog and D4 metadata/text
search.

## Operator surfaces

```text
mq-agent notebook questions --catalog <catalog.json>
mq-agent notebook gaps --catalog <catalog.json>
```

Both commands require the Drive access token used by the existing selective
reader. Only catalog items classified as `interaction` are fetched by the
question extractor.

## Question extraction

Question extraction is deterministic:

- split bounded interaction text into candidate utterances;
- keep utterances ending in `?` or beginning with an English/Swedish question
  word;
- normalize case, prefixes and punctuation;
- deduplicate by the normalized question key;
- assign a stable SHA-256-derived question id.

The report records occurrence count, notebook count and whether the same
normalized question recurred across notebooks.

Interaction traces always carry:

```text
source_role: interaction
claim_eligible: false
evidence_role: inquiry-history-only
```

## Gap classification

`notebook gaps` compares each extracted question with D4 metadata/text search
results and assigns one state:

| State | Meaning |
| --- | --- |
| `NO_SOURCE_EVIDENCE` | no source or derived candidate matched |
| `DERIVED_ONLY` | derived material matched but no source did |
| `STALE_SOURCE_THEME` | source matches exist, but all matched sources exceed the age threshold |
| `SOURCE_MATCHES_PRESENT` | at least one current-enough source candidate matched |

The default stale threshold is 365 days and is measured against the catalog
snapshot timestamp.

These are research-state labels, not factual verdicts. A metadata or text match
does not prove that the source answers the question.

## Privacy boundary

D7 does not write extracted interaction text to tracked files. The CLI may show
question text in the local terminal or JSON response for operator review, but no
command in this phase persists that output into Git or durable mqobsidian
memory.

Tracked tests and documentation use synthetic interaction text only.

## No semantic dependency

D7 deliberately uses:

- deterministic question normalization;
- catalog roles;
- D4 lexical metadata/text matching;
- timestamps.

No embeddings or semantic index are required. That keeps D7 independent from
the optional D8 semantic experiment.

## Evidence boundary

Interaction history can establish:

- that a question was asked;
- that it recurred;
- which notebooks contained the inquiry;
- that the current catalog search found source, derived or no matching material.

Interaction history can never establish:

- the answer to the question;
- that a previous assistant statement was correct;
- source corroboration;
- claim eligibility.

No D7 output is automatically promoted into durable memory.
