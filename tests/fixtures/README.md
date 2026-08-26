# Vendored consumer contracts

mqobsidian owns these schemas. This directory holds byte copies so mq-agent's
suite validates against the real contract instead of a hand-written stub that
cannot drift-check.

**Temporary consumer strategy, not a second contract owner.** Per
mqobsidian `docs/memory-model.md`, consumer repos may validate against these
shapes but must not redefine them locally. Nothing here may be edited to make a
test pass: the fix is always to copy the owner's file over it.

| File | Owner path | Kept honest by |
| --- | --- | --- |
| `notebook-pack.v1.json` | `mqobsidian/schemas/notebook-pack.v1.json` | `test_vendored_schema_matches_mqobsidian` |

## Known gap

The drift test compares against a local vault resolved via `MQ_OBSIDIAN_DIR`,
so it can only run where that vault is reachable — a developer machine, not
CI. mqobsidian roadmap 12f tracks deterministic distribution; until then, drift
is caught locally and repaired by copying the owner's file.

To refresh after an owner-side contract change:

```sh
cp "$MQ_OBSIDIAN_DIR/schemas/notebook-pack.v1.json" tests/fixtures/
```
