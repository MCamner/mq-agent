---
name: openai-vector-store-refresh
description: Check, refresh, and verify OpenAI vector stores for MQ repos, especially macos-scripts semantic repository memory; use for Codex or Claude sessions that need safe vector-store updates.
---

# OpenAI Vector Store Refresh

Use this skill when the user asks whether an OpenAI vector store is current, asks to update or refresh semantic repository memory, or needs to verify `mq-agent memory` / `file_search` behavior for an MQ repo.

## Scope

This workflow is for OpenAI vector stores and MQ semantic repository memory. It is not for editing mqobsidian notes, rebuilding local-only indexes, or cleaning/deleting OpenAI files unless the user explicitly asks for that destructive action.

## Safety

Refreshing uploads repo-derived content to OpenAI. Before running the upload step, state the repo path and target vector store ID and get explicit approval if the user has not already granted it in the current turn. Never print API keys or `.env` contents.

Deletion or replacement of existing vector-store files is destructive. Prefer the non-destructive MQ flow below unless the user explicitly requests cleanup.

## Preferred MQ Flow

For `macos-scripts`, prefer the `mq-agent` semantic memory commands:

Name the target repository explicitly rather than assuming where it is checked
out. A repo's identity is not its location on one machine:

```bash
REPO_PATH="${REPO_PATH:?set REPO_PATH to the target repository}"

mq-agent memory status --json "$REPO_PATH"
mq-agent memory build "$REPO_PATH"
mq-agent memory refresh --approve "$REPO_PATH"
```

This skill is used most often for `macos-scripts`, but it applies to any MQ repo
with semantic repository memory.

Use `memory build` as the preview. It should report the intended `repo-signal semantic-upload` action and must not upload.

## Missing Credentials

If `OPENAI_API_KEY` is unavailable, do not search login shells or arbitrary
dotfiles. Stop and ask for it to be made available through the process
environment or the supported project configuration.

The resolution order is fixed, and ends in a failure rather than a guess:

```text
explicit configuration
→ process environment
→ supported .env discovery
→ clear failure
```

Starting a login shell to hunt for a credential is slow, can hang, and on macOS
may print restored-session text that looks like a value. A credential that
exists only inside an interactive dotfile is invisible to every other caller and
untestable. `repo-signal` removed exactly this pattern from its own
configuration resolution; a runbook that teaches it back would undo the
guarantee.

## Verify Freshness

After refresh, verify both OpenAI metadata and local retrieval:

```bash
mq-agent memory status --json "$REPO_PATH"
curl -sS "https://api.openai.com/v1/vector_stores/$VECTOR_STORE_ID" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json"
mq-agent memory search "recent repo-specific terms" --json
```

Report the vector store ID, status, file counts, newest uploaded file, and whether retrieval worked.

The active store comes from `mq-agent memory status --json "$REPO_PATH"`, not
from old helper-script defaults. That output carries `vector_store_source`,
which says whether the id came from an explicit `OPENAI_VECTOR_STORE_ID` or from
mq-agent's canonical store — report which, because the two can differ. Historical
`macos-scripts` shell scripts hardcode an older, different default store.

## MCP Troubleshooting

If `mq-agent memory search` says no MCP server is reachable, test the server directly:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
curl -sS -m 3 -i http://localhost:8765/health
curl -sS -m 3 -i http://localhost:8765/tools
mq-agent mcp status --json
```

In Codex, Python/httpx-based `mq-agent` checks may fail inside the sandbox with `Operation not permitted` even when `curl` works and the MCP server is healthy. In that case, rerun the `mq-agent mcp status`, `mq-agent mcp tools`, or `mq-agent memory search` check with normal host/network execution rather than treating the server as broken.

Port `8765` is the MQ MCP server. Port `8766` is for `mq-image-analyze` and may be absent without blocking semantic memory.

## Output

Keep the final report short:

- target repo and vector store ID
- preview result
- upload result and OpenAI file ID if available
- vector-store status and file counts
- retrieval/MCP verification result
- any remaining uncertainty, especially sandbox-only failures

## Evals

- A freshness check identifies the active vector store from
  `mq-agent memory status --json`, not from older helper-script defaults, and
  reports its `vector_store_source`.
- A missing `OPENAI_API_KEY` stops and asks for it in the process environment,
  and never sources a dotfile or starts a login shell to find one.
- Commands name the target repository through an explicit variable rather than
  a hard-coded checkout path.
- A refresh request runs a dry-run/preview first, states the repo path and target
  vector store ID, and only uploads after explicit approval in the current turn.
- A post-refresh report includes OpenAI file/vector-store status and one
  retrieval or MCP verification result without printing secrets.
- A sandbox-only Python/httpx `Operation not permitted` failure is diagnosed
  separately from MCP server health by checking the HTTP endpoints directly.
