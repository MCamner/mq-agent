# Exact-code review receipts

`mq-agent review` can request an evidence receipt from mq-mcp:

```bash
mq-agent review file README.md --receipt
mq-agent review diff --receipt --json
mq-agent review repo ../repo-signal --receipt
```

The receipt is produced by mq-mcp, which owns the review execution and source
read. mq-agent does not reconstruct, re-hash, or strengthen the evidence.

The contract is `mq.review-receipt.v1`. It binds a review result to the exact
git commit and content fingerprint observed by mq-mcp. Dirty working trees are
supported because the content fingerprint identifies the bytes actually
reviewed; the commit alone is not treated as sufficient evidence.

A receipt with `status=REFUSED` makes the mq-agent command exit non-zero. The
raw review result remains present in the receipt so the operator can inspect
what ran without confusing it with code-version-bound evidence.

Human output renders the review result first and then a compact receipt summary.
`--json` returns the mq-mcp receipt unchanged.

When `--receipt` is requested, mq-agent verifies the receipt's own content
address and persists only `ISSUED` receipts under:

```text
~/.mq-agent/review-receipts/<sha256>.json
```

Set `MQ_AGENT_REVIEW_RECEIPTS_DIR` to use another operator-local directory.
Writes are atomic and content-addressed, so retrying the same receipt is
idempotent. `REFUSED`, malformed or tampered receipts are never stored.

## Safety boundary

Receipt generation remains read-only in mq-mcp. mq-agent's persistence is an
explicit local side effect of `--receipt`; it does not modify the reviewed
repository. When `--brain` is also used, mq-agent sends only the underlying
review result to the existing brain write path rather than treating receipt
metadata as findings.

This surface requires an mq-mcp runtime that supports the optional
`receipt=true` argument on its review tools.
