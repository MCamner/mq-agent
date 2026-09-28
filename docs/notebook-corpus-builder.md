# NotebookLM corpus catalog builder

D3 implements the deterministic materialization step for the Drive-backed
NotebookLM corpus.

It does **not** connect to Google Drive. A future inventory adapter supplies
normalized metadata; this builder turns that metadata into
`notebook-corpus-index.v1`.

## Boundary

```text
normalized Drive/archive metadata
  -> deterministic materializer
  -> local catalog
  -> local checkpoint
```

The builder never:

- opens a corpus file body;
- searches the corpus;
- embeds or vectorizes content;
- renames, moves or deletes a Drive item;
- repairs an item that lacks a real notebook relationship.

## Input

The input document contains:

```text
corpus_key
snapshot_at
notebooks[]
items[]
```

Notebook input requires `drive_item_id` and `title`.

Item input requires provider identity and metadata used by the D2 contract:
`drive_item_id`, `notebook_drive_item_id`, `parent_drive_item_id`,
`relative_path`, title, MIME type, size, modified time and origin/provider.
A measured SHA-256 is optional.

`relative_path` is classification input only and is not copied into the
catalog.

## Identity and determinism

Logical notebook and item IDs are deterministic hashes of opaque Google Drive
item identities. A display-title rename therefore does not change identity.

Notebook rows are sorted by `notebook_id`; item rows are sorted by `item_id`.
The checkpoint contains no build clock. Rebuilding the same logical metadata in
another input order yields the same catalog and checkpoint.

## Classification

The D1 structural rules are preserved:

```text
Sources/       -> source
Artifacts/     -> derived
Notes/         -> derived-note
Chat History/  -> interaction
root file      -> metadata-or-other
unrecognized   -> unknown
```

An explicit override requires `override_provenance`.

An item without a valid notebook relationship is excluded and counted as
`unmapped_notebook` in the checkpoint. It is never attached to a synthetic
notebook.

## Checkpoint

The local checkpoint records:

- source snapshot time;
- deterministic source fingerprint;
- resulting catalog SHA-256;
- included notebook/item counts;
- excluded count and reason totals.

This checkpoint is the D3 hand-off to the later incremental inventory work. It
is not a Drive pagination/resume cursor; that belongs to Phase 2.

## Local smoke run

```bash
python3 scripts/build-notebook-corpus-index.py \
  tests/fixtures/notebook-corpus-input.json \
  --catalog /tmp/notebook-corpus-index.json \
  --checkpoint /tmp/notebook-corpus-checkpoint.json
```

The generated catalog and checkpoint are disposable local state and must not be
committed.
