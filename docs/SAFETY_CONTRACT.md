# Safety Contract

mq-agent is built around explicit, gated execution. The model never runs unsupervised.

## What the agent may always do

These operations are allowed in all modes without approval:

- Read files and directories
- Run `git status`, `git log`, `git diff`, `git branch`, `git remote`
- Run `repo-signal` analysis tools
- Run `repo_summary`, `list_files`, `find_files`
- Call `mq-mcp` for tool routing (if available)

## What requires approval

These operations require either `--approve` or `execute` mode:

- Running shell commands via `run_command`
- Writing files
- Running `git commit`, `git push`, `git tag`
- Any command that modifies state

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

## Audit trail

Every step is tracked in `AgentState.plan` with:

- description
- tool called
- status (pending / success / failed / skipped)
- result output
- error message if failed
- verification note from the Verifier

The full state is available via `--json` on any command.
