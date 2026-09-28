# NotebookLM corpus search baseline

D4 adds the first retrieval baseline over the D3 local catalog.

The baseline is intentionally lexical and inspectable. It does not use
embeddings, semantic expansion or model ranking.

## Retrieval path

```text
query
  -> normalized lexical terms
  -> item title + notebook title metadata
  -> optional provider text-match metadata
  -> relevance score
  -> source-role tie-break
  -> bounded top-k results
  -> query trace
```

The search code never opens a file body. A future Drive adapter may supply
provider text hits as opaque item identity plus the query terms that matched.
No text body or snippet is required by this layer.

## Ranking

Each query term contributes:

- item-title match: 4
- provider-text match: 3
- notebook-title match: 2

Results sort by score descending. Equal-score results then use source-role
priority:

```text
source
derived
derived-note
metadata-or-other
unknown
interaction
```

Stable notebook/item identity is the final tie-breaker.

This ordering is retrieval behavior, not a universal quality judgment. It keeps
original source candidates ahead of NotebookLM-generated artifacts when
relevance is otherwise equal.

## Query trace

Every search reports:

- catalog notebooks/items;
- metadata items considered;
- provider text hits supplied/matched;
- candidates before top-k;
- returned count and source-role mix;
- file bodies fetched and bytes fetched;
- connector calls supplied by the adapter;
- explicit no-result state;
- deterministic ranking rule.

D4 itself always reports zero bodies and zero bytes fetched.

## Negative-control behavior

Search never broadens the query until something plausible appears. If none of
the normalized terms match metadata or supplied provider-text terms, the result
is empty and `no_result=true`.

## Frozen D4 evaluation set

The six queries remain exactly the D1 set:

1. Find sources about building an MCP server in Python.
2. What design patterns recur across material about agentic AI and multi-agent
   systems?
3. Find material explaining TOGAF 10 and enterprise architecture.
4. Find sources about pentatonic guitar technique and recurring rock licks.
5. For a matching notebook, return original sources before
   NotebookLM-generated artifacts.
6. Find sources about Akkadian cuneiform accounting tablets.

The tracked tests use a sanitized synthetic corpus to verify retrieval
semantics. They are not evidence of real-corpus relevance; real-corpus
measurement requires the authorized Drive inventory/search adapter.

## Boundary

D4 does not implement:

- Drive listing or pagination;
- Drive mutation;
- selective file-body fetch;
- answer synthesis;
- embeddings or vector search;
- durable-memory promotion.

Those stay in later roadmap slices.
