# NotebookLM semantic retrieval experiment

D8 is an opt-in local experiment. It does not replace D4 and it is not an
activated archive path by default.

## Commands

```text
mq-agent notebook semantic-build
mq-agent notebook semantic-search
mq-agent notebook semantic-eval
```

The experiment uses a local Ollama embedding model by default:

```text
nomic-embed-text
```

No hosted embedding service is used by this implementation.

## Build path

```text
D3 catalog
  -> source/derived role filter
  -> text-fetchable MIME filter
  -> notebook-balanced bounded selection
  -> bounded D5 text fetch
  -> bounded chunks
  -> local Ollama embeddings
  -> disposable JSON index
```

The bounded selector walks notebooks round-robin and prefers source items before
derived material within each notebook. A single notebook is capped at two selected
items by default, so lexicographically early notebook ids cannot monopolize a
small experiment index. Unsupported MIME types are excluded before fetch rather
than counted as attempted retrieval failures.

Build trace records text-capable/unsupported counts, selected/fetched notebook
coverage, attempted/fetched/unavailable file counts and unavailable reasons.

Each chunk retains:

- Drive item id;
- notebook id and title;
- item title;
- source role;
- claim eligibility inherited from the source role;
- modified time;
- content hash when available;
- character offsets.

Deleting the index loses no canonical data.

## Search behavior

Semantic search ranks chunks by cosine similarity, then collapses repeated
chunks from the same Drive item. Source roles are preserved exactly as recorded
in D3. Similarity cannot turn a derived item into a source or make an
interaction claim eligible.

## Evaluation

`semantic-eval` compares D8 with D4 on the exact six frozen D4 queries. The
operator supplies a JSON map from each frozen query to expected Drive item ids.

The report records lexical and semantic pass counts, improvements, regressions,
provenance coverage and hosted-egress state.

Decision labels are descriptive:

- `SEMANTIC_BENEFIT_MEASURED`
- `NO_MEASURED_BENEFIT`
- `SEMANTIC_REGRESSION_OR_MIXED`

No label automatically activates semantic retrieval.

## Activation boundary

D8 should remain disabled unless a complete-catalog measurement shows a named
retrieval benefit without provenance loss or regression. D4 remains the clean
fallback and canonical baseline.
