# Ollama-backed learn extraction

This document defines the mq-agent boundary for optional Ollama-backed learn
workflows in the mq ecosystem.

## Role

Ollama may be used by mq-mcp as a local extraction model for learn workflows:

```text
review output -> pattern extraction -> structured learning record
```

Ollama is not an autonomous agent. It should not execute commands, mutate
repositories, write memory silently, override mq-mcp safety classes, or perform
final risk scoring.

## Ownership

```text
mq-mcp
  owns learn contracts, safety classes, review logic, validation and storage

Ollama
  optionally extracts patterns from mq-mcp review findings into structured JSON

mq-agent
  surfaces learn status/search/explain through the mq-mcp bridge
```

mq-agent must not implement local learn extraction, schema validation, memory
storage, prompt handling, or model-specific learn policy. Those behaviors belong
in mq-mcp so the safety and storage rules stay centralized.

## Expected mq-mcp policy

When mq-mcp adds or configures an Ollama learn provider, the provider should be
treated as optional and local-first. The recommended model profile is a
deterministic pattern extractor, for example `mq-learn`, with low temperature,
fixed seed, bounded context and JSON-only output.

The learn record contract should be validated by mq-mcp before storage. At a
minimum, mq-mcp should reject:

- non-JSON output
- missing evidence
- unknown fields unless the contract explicitly allows them
- records with `should_store=true` without caller approval
- low-confidence records from automatic storage
- prompt-injection text inside reviewed content being treated as instructions

Storage must require explicit approval from the caller or operator. A dry-run or
read-only extraction mode should be the default.

## mq-agent surface

mq-agent only exposes read-only learn commands:

```bash
mq-agent learn status
mq-agent learn search <query>
mq-agent learn explain <pattern-id>
```

If mq-mcp does not expose the required learn tools, mq-agent should report a
clear optional-provider or missing-tool message and keep the rest of the command
surface usable.

## Implementation order

The Ollama-specific implementation should land in mq-mcp first:

1. Add the `mq-learn` Modelfile or equivalent provider configuration.
2. Add the JSON learn record contract and validation.
3. Add a read-only or dry-run extraction path.
4. Require explicit approval for storage.
5. Add tests for invalid JSON, prompt-injection-as-data, missing Ollama and
   no-storage-without-approval.

After that exists in mq-mcp, mq-agent may update docs or rendering for any new
read-only status fields returned by the bridge.
