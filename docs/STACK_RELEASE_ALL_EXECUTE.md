# Stack Release — Multi-Repo Execute (Design)

Design for `mq-agent stack release --all --execute`: releasing several stack
repos in one run over the existing single-repo primitive.

**Status:** DRAFT — direction approved, decisions locked (see below). No
execute code exists yet. This document is the specification the first code
slice must satisfy.

Related: [Stack Release](STACK_RELEASE.md) (single-repo pipeline),
[Stack Contract Gate](STACK_CONTRACT_GATE.md).

---

## Ground rule

**Fail-fast before execute.** If *any* repo is blocked, the whole multi-repo
run stops **before anything is mutated**. Multi-repo execute is *not* atomic
across repos — git has no distributed transaction — so the design leans on a
hard preflight gate to make mid-flight failure rare, and handles the remainder
with explicit, non-destructive partial-failure semantics.

---

## Locked decisions

These are settled and must hold in the implementation:

1. **Failing-tests primitive** is a **repo-local release/preflight test target**
   as a hard blocker. Every repo owns its own "am I releasable?" check.
   `mq-mcp-review` may aggregate or supplement, but must not replace the
   repo-local test.
2. **Dependency order** is **explicit in `MQ_STACK_REPOS`** for the first
   version. A derived dependency graph may come later, but not in the first
   `--all --execute`.
3. **Unpushed commits** are a **hard blocker**. A multi-repo release must not
   build on local-only drift.
4. **Version mismatch** (`VERSION` vs `.mq/repo-contract.json` vs
   changelog/release surface) is a **hard blocker**.
5. **Push/tag semantics:** no remote tag deletion as rollback, ever. On partial
   commit/tag/push failure the system reports the exact state and stops.
   Repair is **fix-forward**, never history rewriting.
6. **Test requirements** below (see [Test requirements](#test-requirements))
   must exist before any execute code is built.

---

## Core shape — two phases, one gate between

```text
PREFLIGHT (read-only, all repos)  ──►  GATE  ──►  EXECUTE (mutating, one repo at a time)
       ↑ fail-fast here                all clear?         ↑ #144 shape guard per repo
       any blocking state stops         no → abort,
       the whole run                    zero mutations
```

---

## 1. Per-repo preflight

Preflight runs the existing read-only `plan_stack_release(repo)` for every repo
in `MQ_STACK_REPOS`, plus the hardened checks in
[Blocking states](#6-blocking-states). No mutation. Each repo is categorized:

| Category | Meaning | Proceeds to execute? |
| --- | --- | --- |
| `READY` | Plan GO, every preflight check passes | Yes |
| `UP-TO-DATE` | No unreleased commits since the last tag | No (skipped, not an error) |
| `BLOCKED` | At least one blocking state | No — **stops the whole run** |

This reuses `plan_stack_release_all`'s existing ready/blocked/up-to-date
trichotomy (schema `mq_stack_release_all.v1`) and adds the preflight hardening
and the gate on top — not a new plan engine.

**Order:** repos are preflighted in the explicit `MQ_STACK_REPOS` order
(locked decision 2). Preflight is order-independent (everything is read);
execute is not (see [Partial failure](#3-partial-failure)).

---

## 2. Abort semantics

Two kinds of abort, with different consequences.

**A. Preflight abort (fail-fast — the normal protection):**

* Triggered by: at least one repo in `BLOCKED`.
* Consequence: the run ends **before the execute phase**. Zero repos touched.
  Exit 1.
* Report: full preflight table with each blocked repo's reason. Nothing is
  marked `SKIPPED`/`FAILED` — nothing started.

**B. Execute abort (mid-flight — the exception):**

* Triggered by: a repo that was `READY` in preflight fails during its own
  execute (push rejected, network, unexpected dirty).
* Consequence: **stop-on-first-failure**. The failing repo self-rolls-back its
  own pre-commit edits (existing `execute_stack_release` behavior). Remaining,
  not-yet-started repos are marked `SKIPPED` and left untouched.
* **Already-released repos are NOT rolled back** — that would require tag
  deletion / force-push, which is destructive and out of scope (locked
  decision 5). They are reported `RELEASED`; resolving the partially-released
  stack is a deliberate fix-forward step, never history rewriting.

Each repo additionally re-verifies on-main + clean-tree immediately before its
mutation via `_verify_release_shape` (shipped in #144), so even if the world
changes between preflight and that repo's turn, that repo refuses before
creating anything.

---

## 3. Partial failure

Concrete scenario, dependency order `[A, B, C, D, E]`, all `READY` in preflight:

```text
A  RELEASED   commit, tag, push, truth-export done
B  FAILED     push rejected (remote moved first)
              → B self-rolls-back its uncommitted edits
              → if B had committed but failed on push:
                the commit stays local, NO tag/push happened
C  SKIPPED    never started
D  SKIPPED
E  SKIPPED
```

Rules:

* **Stop-on-first-failure.** No "continue past the failure" mode — it would
  spread inconsistency.
* **A stays released.** No automatic un-release. The report states plainly that
  the stack is partially released.
* **B's state is reported exactly** by where in the step chain it broke
  (pre-commit → fully clean; post-commit/pre-tag → a dangling local commit,
  which #143 already guards against on re-run; never a half-pushed tag).
* **C/D/E untouched.** A re-run after repair picks them up — and because A is
  now `UP-TO-DATE` and B may carry a local commit, the #143/#144 guards catch
  every dangerous re-run state.

Explicit `MQ_STACK_REPOS` order makes this safe: if A is a contract producer and
B a consumer, and B fails, no *later* consumers (C–E) have been released against
a half-finished stack.

---

## 4. Dry-run vs execute

| Invocation | Behavior | Mutates? |
| --- | --- | --- |
| `stack release --all` | Preflight report (today's behavior). Exit 1 if any `BLOCKED`. | No |
| `stack release --all --execute --approve` | Preflight → fail-fast gate → execute in order. | Yes |
| `stack release --all --execute` *without* `--approve` | Refused. Prints preflight + what *would* be released. Exit 1. | No |

* `--execute` alone is not enough: the stack convention is that write flows
  require an explicit `--approve`. Multi-repo release is the highest-consequence
  write flow — double confirmation.
* `--all --execute` is currently hard-rejected (`test_all_execute_is_rejected`).
  That guard stays until this design is implemented and tested.
* Dry-run is always the default and always side-effect free.

---

## 5. Report format

New schema `mq_stack_release_all_execute.v1` (parallel to the existing
`mq_stack_release_all.v1`), rendered both as a human table and as `--json`:

```text
repo   preflight   execute    version         detail
A      READY       RELEASED   1.4.0 → 1.4.1    tag v1.4.1 pushed
B      READY       FAILED     1.2.0 → 1.2.1    push rejected (non-fast-forward)
C      READY       SKIPPED    1.0.0 → 1.0.1    not attempted (run aborted at B)
D      UP-TO-DATE  —          1.1.0            no unreleased commits
E      BLOCKED     —          0.9.0            dirty tree (preflight)
```

State taxonomy:

* **Preflight column:** `READY` | `UP-TO-DATE` | `BLOCKED`
* **Execute column:** `RELEASED` | `FAILED` | `SKIPPED` | `—` (not applicable)
* A `BLOCKED` in preflight means the execute column is never filled (the gate
  stopped everything). A `FAILED`/`SKIPPED` can only arise in the execute phase,
  which by definition means preflight was fully clean.

JSON per repo: `repo, preflight_state, execute_state, current_version,
new_version, tag, blockers[], evidence{}`. Top level: `schema, planned_at,
executed_at, approved, aborted_phase (preflight|execute|none), released_count,
failed_count, skipped_count`.

---

## 6. Blocking states

Multi-repo execute is **strict** — several of the single-repo plan's *warnings*
become *hard blockers* here, because a partially-released stack costs more than
a stopped run.

| State | Today in `plan_stack_release` | Multi-repo preflight | Source |
| --- | --- | --- | --- |
| dirty tree | blocker | **BLOCKED** | `gate.dirty` |
| off-main | blocker | **BLOCKED** | `gate.on_main` |
| target tag exists | blocker | **BLOCKED** | `_tag_exists` (#143) |
| unpushed commits | warning | **BLOCKED** (locked 3) | `gate.unpushed` |
| version mismatch | separate gate | **BLOCKED** (locked 4) | `stack_contract_check` |
| failing repo test | not checked | **BLOCKED** (locked 1) | repo-local test target |
| no VERSION / no README | blocker | BLOCKED | `gate.blockers` |
| no unreleased commits | blocker (→ up-to-date in `--all`) | UP-TO-DATE | `notes.has_changes` |

The failing-repo-test blocker (locked decision 1) is the only one without a
ready read-only primitive today: it requires preflight to run each repo's own
release/preflight test target. `mq-mcp-review` may aggregate or supplement the
result, but the authoritative check is the repo-local one — each repo owns its
own releasability.

---

## 7. Push / tag semantics

Stated explicitly so no implementation can drift from it:

* **No remote tag deletion as rollback. Ever.** Not on failure, not on abort,
  not as cleanup.
* **No destructive rollback across repos.** An already-pushed release stays
  pushed.
* On partial commit/tag/push failure, the system reports the exact state
  reached and **stops** (stop-on-first-failure).
* Repair is always **fix-forward**: re-run after fixing the cause, releasing a
  new patch, or reconciling by hand — never `git tag -d` on a remote, never a
  force-push over published history.
* The #143 guard (target tag already exists) and the #144 guard (on-main +
  clean tree at execute) are the two mechanisms that make a fix-forward re-run
  safe rather than dangerous.

---

## Test requirements

Locked decision 6 — these must exist before any execute code is built. Each is
a preflight/refusal behavior, verifiable without performing a real release:

* dirty tree blocks
* off-main blocks
* unpushed commits block
* target tag already exists blocks
* version mismatch (`VERSION` vs contract vs release surface) blocks
* failing repo-local test blocks
* repo 2 of 5 fails → repos 3–5 become `SKIPPED`
* an already-released repo is not rolled back

---

## Scope boundaries (this document)

* No code change — specification only.
* No execute logic built.
* No tag deletion — the drifted tags (`v1.0.1` / `v2.0.1` / `v1.4.1`) are not
  touched; that is a separate operator decision.
* No pushes or releases performed.

---

## Next step

Implement in slices, preflight first:

1. **Preflight hook** — the read-only aggregate with the hardened blocking
   states and the fail-fast gate, reported via `mq_stack_release_all_execute.v1`
   but with the execute column always `—`. Ships the whole refusal surface and
   its tests without any mutation.
2. **Execute** — only after the preflight hook and its tests are in place: wire
   the gate to the existing per-repo `execute_stack_release`, in explicit
   `MQ_STACK_REPOS` order, behind `--execute --approve`, with stop-on-first-
   failure and the exact report.
