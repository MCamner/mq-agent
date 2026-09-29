# NotebookLM Drive inventory adapter

Phase 2 adds a read-only, resumable metadata inventory path for the configured
NotebookLM Drive corpus.

## Boundary

The adapter uses only Google Drive read APIs:

- `files.list` scoped by parent folder;
- `changes.getStartPageToken`;
- `changes.list`.

It does not download file bodies and contains no Drive create/update/delete,
move, rename or sharing operation.

## Initial scan

A full scan is breadth-first and page-resumable.

The checkpoint stores the current folder plus Google's opaque
`nextPageToken`. The token is never parsed or synthesized. A failed request
leaves the previous cursor in place.

```text
root
  -> files.list(parent=root)
  -> enqueue child folders
  -> files.list(parent=child)
  -> ...
  -> complete
  -> changes.getStartPageToken
```

The resulting inventory is disposable local state and may contain real Drive
IDs. It must not be committed.

## Incremental refresh

After a complete scan, the checkpoint stores Google's change token. Later
refreshes use `changes.list` instead of traversing every folder again.

A no-change refresh therefore needs one change-feed request rather than a full
corpus traversal.

Removed or trashed known items are retained under `missing` with their last
known metadata. History is not erased.

## Rate limits

The concrete REST client retries only:

- HTTP 429;
- HTTP 500/502/503/504;
- HTTP 403 when Drive reports `rateLimitExceeded` or
  `userRateLimitExceeded`.

Retries use bounded exponential backoff and honor numeric `Retry-After` when
present. Other 403 responses fail immediately instead of being mislabelled as
quota errors.

## D3 projection

A complete checkpoint can be projected into the normalized D3 input shape.

All top-level folders under the configured root are notebook candidates except
folder IDs excluded by local configuration. This is how the private archive
manifest folder stays out of the notebook set without committing its name or
ID.

The projection refuses a partial checkpoint.

## Truth states

```text
partial  traversal/change processing incomplete
current  all pages processed and a current change token is stored
```

Provider failure never becomes `current`.

## Exit-gate coverage

The test suite proves:

- interrupted pagination resumes from the opaque cursor;
- a failed page does not advance the cursor;
- retries do not duplicate inventory records;
- an unchanged incremental refresh uses one change call;
- deleted/trashed items become explicit missing history;
- D3 projection rejects partial state;
- the REST transport retries quota/transient failures but not ordinary
  permission errors.

Real-corpus execution and D4 measurement remain operational follow-up steps.
