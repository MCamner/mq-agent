# Queue handoff acceptance evidence

Recorded from an operator-run acceptance test of `mq-agent queue`, released in
v1.37.0 (#445). Claude ran its half on 2026-11-14 and Codex its half on
2026-11-15. The fixture repository was local, had no remote and is not
published; this document records its public-safe identifiers and the measured
outcomes. The queue's state file remains authoritative for the task record;
this document does not reconstruct or strengthen it.

## Scope

One task, two owners, two separate worktrees:

```text
queue add -> claim (claude) -> commit -> verify-changes -> handoff (claude -> codex)
          -> claim (codex)  -> commit -> verify-changes -> complete
```

Constraints for the run: no merge, push, release or change to a production
repository; nobody approves a handoff on the receiving agent's behalf; no
worktree or branch is deleted without a separate check.

## Task

```text
task:         task-b852a661aabb419d9a108c7defe337e4
base commit:  d7d551bc7af0504f7732dfcd80269777b9a781e7
final status: completed
final owner:  codex
```

## Claude half

| Fact | Value |
| --- | --- |
| Worktree branch | `mq-task/task-b852a661aabb419d9a108c7defe337e4/claude` |
| Commit | `86774d3b1ecfe89871b5a83faaf9e9da78501a1b` |
| Verification | `PASS`, receipt `a5d61c7f7836bb087ea1b8f6eacbf623c1e132b30c64b823d1fa42a9834e767e` |
| Handoff diff | `NOTES.md`, 4 insertions, `diff_sha256` `b4cfedbcf36417b6422217d669cae2a0f1e8aaf1a03abf008e70fafe0bc96906` |
| Handoff approval | `not_granted` |

Three reservation checks were each refused, with exit 1:

| Attempt | Refusal |
| --- | --- |
| Another owner claims the active task | `Task is active; it cannot be claimed` |
| An owner not named in the handoff accepts it | `Only the receiving owner can accept this handoff` |
| Another task requests the same worktree | `Worktree is reserved by task-b852…` |

The third check needed a second task, `task-d46c61e2…`. It was cancelled
afterwards and never had a worktree or branch.

The handoff record has no handoff id of its own; it is identified by its
`diff_sha256` and its timestamp, `2026-11-14T23:17:12Z`.

## Codex half

| Fact | Value |
| --- | --- |
| Worktree branch | `mq-task/task-b852a661aabb419d9a108c7defe337e4/codex` |
| Commit | `d7d19b7543cc6889db26cedc48ddd5bc805c44ec`, child of `86774d3` |
| Verification | `PASS`, receipt `7caf5289fc53366fab183cbe881bed01ea3fb2f1e77db170860f1fa44623b874`, head `d7d19b7`, base `d7d551b` |
| Diff against base | `NOTES.md`, 9 insertions: Claude's 4 lines and Codex's 5 |

## Independent checks

Run by Claude after Codex reported completion, 2026-11-15:

- `queue show` reports `completed`, owner `codex`, and the verification above.
- `git merge-base --is-ancestor 86774d3 d7d19b7` succeeds: Claude's commit is
  preserved in Codex's history.
- The fixture's own check script exits 0 in the Codex worktree.
- The handoff record still carries `approval_status: not_granted`.
- The fixture repository's `main` is still at the base commit `d7d551b`, and it
  has no remote: nothing was merged or pushed.

## Result

`PASS` for the shared task queue and the Claude-to-Codex handoff, end to end.

## Known limitation

Ownership is declared, not proven. The queue records `codex` because the
command was run with `--owner codex`, and both agents commit under the same Git
identity, so neither the queue nor Git can show which agent ran a step. This is
acceptable for the cooperative queue as designed. Per-agent identity, such as
signed handoffs or a distinct commit author per agent, is a possible later
hardening and is not a requirement of this result.
