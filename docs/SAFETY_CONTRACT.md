# Safety Contract

mq-agent is built around explicit, gated execution. The model never runs unsupervised.

## What the agent may always do

These operations are allowed in all modes without approval:

- Read files and directories
- Run `git status`, `git log`, `git diff`, `git branch`, `git remote`
- Run `repo-signal` analysis tools
- Run `repo_summary`, `list_files`, `find_files`
- Call mq-mcp **Class A or B** tools without confirmation (read-only, no writes,
  no subprocess — e.g. `read_repo_file`, `git_status`, `repo_signal_analyze`)

## What requires approval

These operations require either `--approve` or `execute` mode:

- Running shell commands via `run_command`
- Writing files
- Running `git commit`, `git push`, `git tag`
- Any command that modifies state
- Calling mq-mcp **Class C** tools (write files — e.g. `update_repo_file`,
  `record_architecture_decision`, `extract_coding_conventions`)
- Calling mq-mcp **Class D** tools (subprocess/open apps — e.g. `run_tests`,
  `open_in_app`, `validate_project`) — must also show command intent to user

## What is always blocked

These patterns are blocked regardless of mode:

```text
rm -rf
sudo
chmod 777
curl | bash
wget | sh
> /dev/sda
mkfs
dd if=
:(){ :|:& };:
```

The shell tool maintains a hard-coded block list that cannot be overridden by the model.

## Safety modes in detail

### read-only (default for audit, signal)

- Only safe tools are callable
- Executor continues past step failures instead of stopping
- No shell execution

### suggest (default for plan, release-check, fix-ci)

- Full planning pass runs
- No steps are executed
- Plan is shown for human review

### execute (requires --approve)

- Steps run after safety gate check
- Blocked patterns still enforced
- Stops on first failure

### dangerous (explicit only)

- No tool restrictions
- No pattern blocking
- Requires explicit `SafetyMode.DANGEROUS` in code — not accessible from CLI by default

## Examples

```bash
# Always safe — read-only
mq-agent audit .
mq-agent score .
mq-agent doctor

# Suggest mode — plans shown, nothing runs
mq-agent release-check
mq-agent fix-ci

# Execute mode — requires --approve
mq-agent release-check --approve
mq-agent run "pytest" --approve

# Blocked at any mode
mq-agent run "rm -rf ."           # blocked pattern
mq-agent run "sudo apt install"   # blocked pattern
```

## mq-mcp tool class gate

mq-mcp exposes 66 tools across four safety classes. mq-agent maps these to its
own safety gates as follows:

| mq-mcp class | Allowed without approval | Requires `--approve` |
|---|---|---|
| A — read-only repo | Yes | No |
| B — read-only external | Yes | No |
| C — write files | No | Yes |
| D — subprocess / open apps | No | Yes + show intent |
| Unknown | No | Blocked unless `--dangerous` |

mq-agent must never bypass this mapping. The formal contract is defined in
[mq-mcp/docs/ORCHESTRATION_CONTRACT.md](https://github.com/MCamner/mq-mcp/blob/main/docs/ORCHESTRATION_CONTRACT.md).

Verify the current contract is satisfied:

```bash
mq-agent run-tool validate_orchestration_contract
```

## Audit trail

Every step is tracked in `AgentState.plan` with:

- description
- tool called
- status (pending / success / failed / skipped)
- result output
- error message if failed
- verification note from the Verifier

The full state is available via `--json` on any command.
