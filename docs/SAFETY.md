# Safety

mq-agent is designed to be safe by default. Every operation is gated by a safety mode, and the agent explains and plans before it acts.

## Safety modes

| Mode        | Behavior                                                      |
|-------------|---------------------------------------------------------------|
| `read-only` | Only read tools are permitted (git, file reads, repo info)    |
| `suggest`   | A plan is shown but nothing is executed — default for most commands |
| `execute`   | Safe actions run after safety check; destructive ops need `--approve` |
| `dangerous` | All restrictions disabled — must be explicitly requested      |

Most commands default to `suggest` or `read-only`. You must pass `--approve` to allow writes.

## Approval flow

Commands that can modify state require explicit approval:

```bash
# Shows plan only (suggest mode default)
mq-agent release-check

# Executes the plan
mq-agent release-check --approve

# Previews without executing anything
mq-agent release-check --dry-run
```

Destructive operations (anything matching the patterns below) require either `--approve` + `execute` mode, or explicit `dangerous` mode. They are never run automatically.

## Blocked shell patterns

The following patterns are always blocked in `run_command`, regardless of safety mode:

```text
rm -rf /
sudo rm -rf
mkfs
dd if=
> /dev/sda
:(){ :|:& };:   (fork bomb)
```

## Safe tools (read-only whitelist)

The following tools are permitted in `read-only` mode:

```text
git_status    git_log       git_diff
git_branch    git_remote    repo_summary
list_files    read_file     find_files
which
```

Any tool not on this list is blocked in `read-only` mode.

## Destructive operation detection

Operations are flagged as destructive if their description contains any of:

```text
delete   remove   drop   force push
git push   publish   deploy   rm -rf   format
```

Flagged operations are skipped in `execute` mode unless `--approve` is passed.

## Secrets and environment

Never commit:

- `OPENAI_API_KEY` or any API key
- `.env` files
- Local credentials, tokens or certificates
- Machine-specific secrets

The `.gitignore` already excludes `.env`, `.env.local`, `*.key`, `*.pem`, `secrets.*`.

If you use a `.env` file locally, load it with `source .env` or `direnv`. Never commit it.

## Principle

> The agent should explain, plan and verify before it acts.

Every action goes through: Planner → Safety gate → Executor → Verifier. Nothing runs without passing all three.
