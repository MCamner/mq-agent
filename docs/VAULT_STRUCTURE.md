# Vault Structure — `mq-agent brain structure`

The standard mqobsidian export layout. Every durable memory record the
mq-stack produces lands in a predictable place; `brain structure` checks the
vault against the standard and can create the missing directories.

## Command

```bash
mq-agent brain structure                    # check (read-only, exit 1 if incomplete)
mq-agent brain structure --json             # machine-readable report
mq-agent brain structure --init --approve   # create missing standard directories
```

The vault path is `MQ_OBSIDIAN_DIR`, or `~/mqobsidian` — the same contract as
mq-mcp's `obsidian_writer`. A missing vault is always an error; `--init`
creates directories inside the vault, never the vault itself.

## The standard directories

| Directory | Contents | Writer |
|---|---|---|
| `memory/stack-truth/` | Dated stack truth snapshots (contract + release gates) | `mq-agent stack truth-export` |
| `memory/reviews/` | Code review summaries | mq-mcp `brain_record_review` (`mq-agent review --brain`) |
| `memory/learn/` | Learned patterns and verified promotions | mq-mcp `brain_record_learning` (`mq-agent learn --brain`) |
| `mq-stack/runs/` | Stack run logs (sweeps, orchestrated releases) | `mq-agent stack release` / `stack sweep` |
| `mq-stack/roadmaps/` | Exported per-repo roadmaps | manual export (reserved) |

## Legacy directories

mq-mcp's `obsidian_writer` currently writes reviews and learn notes to the
vault root (`reviews/`, `learn/`). The check reports these as `legacy` with a
note count and the standard location they map to, but never touches them —
migrating the writers is an mq-mcp change, tracked separately.

## Behaviour

* **Read-only by default.** The plain check creates and modifies nothing.
* **`--init` requires `--approve`** — it writes to the vault (flag contract).
* **`--init` only creates what is missing.** Each created directory gets a
  small `README.md` stating its purpose and writer, so the structure is
  self-documenting in Obsidian and the empty directories survive git. Existing
  directories and their contents are never modified.
* **Exit codes are gate-friendly:** 0 when the structure is complete, 1 when
  the vault is missing or any standard directory is absent — so the check can
  run inside a release gate.

## JSON output

```json
{
  "vault": "/Users/you/mqobsidian",
  "vault_exists": true,
  "checked_at": "2026-06-11T12:00:00+00:00",
  "status": "OK",
  "dirs": [
    {
      "path": "memory/stack-truth",
      "purpose": "Dated stack truth snapshots (contract + release gates)",
      "writer": "mq-agent stack truth-export",
      "exists": true,
      "notes": 1,
      "newest": "2026-06-11"
    }
  ],
  "legacy": [
    {"path": "reviews", "standard": "memory/reviews", "notes": 13, "newest": "2026-06-09"}
  ],
  "created": []
}
```

`status` is `OK`, `INCOMPLETE`, or `NO_VAULT`.

## Tool registry

Registered as `vault_structure` in the mq-agent tool registry
(`mq_agent/tools/vault_structure.py`), so plans and tasks can call it like
any other tool.
