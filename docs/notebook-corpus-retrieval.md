# NotebookLM evidence-aware selective retrieval

D5 turns D4 candidates into a bounded evidence bundle. It does not synthesize
an answer and it does not change the authority of the underlying material.

## Authority rules

```text
source
  -> claim-eligible when successfully fetched

derived / derived-note / metadata-or-other / unknown
  -> navigation or secondary context only

interaction
  -> never fetched as claim evidence
```

A derived artifact can never become primary evidence merely because it ranks
well. When a ranked source exists in the same notebook, source retrieval is
attempted first. If no source evidence is available, the bundle reports
`MISSING_SOURCE`.

## Selective fetch boundary

The default budget is:

```text
max files           4
max bytes per file  64 KiB
max total bytes     256 KiB
excerpt              4,000 characters
```

Only text-capable material is fetched in this slice:

- plain text;
- Markdown;
- HTML/XHTML;
- native Google Docs exported as text.

Unsupported binary formats, including PDF, are reported as
`unavailable/unsupported_mime` rather than being silently parsed or treated as
read evidence.

This is intentional: the Takeout corpus commonly contains text/HTML
representations of imported sources, and D5 must stay fail-closed when a body
cannot be interpreted by the approved reader.

## Provenance

Every evidence record includes:

- logical notebook identity and current notebook title;
- logical item identity and opaque Drive item identity;
- title and MIME type;
- modified time;
- origin provider;
- source role and classification method;
- content SHA-256 when the catalog actually measured one;
- fetch status/reason;
- bytes fetched and truncation state.

Quoted or paraphrased claims may only use entries with
`claim_eligible=true`.

## Conflict handling

D5 does not merge source contents into one narrative. Independent source
excerpts remain separate evidence records so disagreement stays observable.

## Runtime truth

The retrieval API accepts `scope=live-runtime`. In that mode it performs zero
corpus reads and returns `DELEGATE_RUNTIME`, preserving the rule that current
code/runtime questions use current source/runtime tools rather than archive
material.

## Provider failure

Provider failures become explicit per-item `unavailable` evidence records.
They do not become empty text, guessed claims or a successful evidence bundle.

## Activation boundary

This implementation may be merged before the full local D3 run, but production
activation over the whole archive remains blocked until a complete current D3
catalog exists and the six frozen D4 queries pass over it.
