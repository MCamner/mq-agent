# Review Receipts

`mq-agent review file|diff|repo --receipt` requires
`mq.review-receipt.v1` from mq-mcp and persists the receipt only when mq-mcp
returns `ISSUED`.

mq-agent does not calculate the source fingerprint itself. mq-mcp owns the
review and the proof because it is the component that reads the source being
reviewed.

## Usage

```bash
mq-agent review file README.md --receipt
mq-agent review diff --receipt
mq-agent review repo ../repo-signal --receipt

mq-agent review file README.md --receipt --json
```

An issued receipt is stored by content address under:

```text
~/.mq-agent/review-receipts/<sha256>.json
```

Set `MQ_AGENT_REVIEW_RECEIPTS_DIR` to use another local directory.

## Fail-closed behavior

mq-agent exits non-zero and stores no reusable receipt when:

- mq-mcp does not return `mq.review-receipt.v1`;
- the receipt's own SHA-256 content address does not verify;
- required receipt fields do not contain a review result; or
- mq-mcp returns `REFUSED`, for example because the reviewed source changed
  while the review was running.

A refused receipt is still shown to the operator, exits non-zero, and is not persisted as proof.

## Brain write isolation

`--receipt --brain` sends only the underlying review result to the existing
brain write path. Receipt metadata is not reinterpreted as findings and does not
change review severity semantics.

Receipt persistence is opt-in: ordinary review commands retain their previous
arguments and output path when `--receipt` is absent.
