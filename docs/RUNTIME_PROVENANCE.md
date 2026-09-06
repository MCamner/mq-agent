# Runtime provenance

Phase 0 of v1.28: the contracts and their semantics, frozen before anything
produces them.

Runtime provenance answers one question:

> Are the source checkout, the installed runtime, the running runtime and the
> release identity the same code — and if not, which two layers differ, and
> what is the next action?

It is not another health check. It is identity, provenance, comparison and
drift detection, and it is read-only by default.

## Why one boolean is not enough

`mq-agent` already has several identity surfaces that can each be individually
correct and jointly contradictory: the checkout, the installed package, a
running process, `VERSION`, `pyproject.toml`, the repo contract, the latest tag,
the GitHub release, and the commit each of those points at.

The v1.27.0 release produced a live example. The repo contract carried:

```json
"version": "1.27.0",
"next_focus": "v1.27.0 — MCP tool contract checking"
```

Both fields were syntactically valid. Together they said the release was the
thing that came after it. Nothing compared them, so nothing noticed.

`runtime_guard.py` states the other half of the gap in its own docstring: it
sees the working tree, not the interpreter, so *a checkout that is clean and
integrated can still be running an editable install of something else*. That is
the case provenance exists to make visible.

## The two contracts

### `mq.runtime-identity.v1`

What one runtime is. Identity is **component + version + commit** — two builds
can carry the same semver, so a version alone does not identify a runtime.

The canonical human form is a fingerprint:

```text
mq-agent@1.27.0+abc1234
```

Not a hash of the environment, the dependencies, the working tree, the host or
the user. Those are not needed to answer the question.

`identity_quality` says how complete the identity is, and the schema constrains
it so a record cannot claim more than it carries:

| Quality | Meaning |
| --- | --- |
| `verified` | component, version and commit are all present |
| `partial` | a version, but the build carries no commit |
| `unknown` | the runtime could not be identified at all |

A missing commit is a **weaker identity, never a missing one to be filled in**.
It is never taken from the latest tag, a sibling checkout, or the working
directory.

All three quality levels are constrained by the schema, not just described:
`verified` without a commit is invalid, `partial` claiming a commit is invalid,
and `unknown` carrying a version or a commit is invalid. A record cannot claim
more or less than it carries.

`install_type` is deliberately outside that constraint. Knowing *how* something
was installed is a different question from knowing *what* it is: a pipx install
can be entirely unidentifiable and still known to be pipx.

`install_type` is one of `editable`, `wheel`, `pipx`, `uv-tool`, `pip`, or
`unknown`. When it cannot be proven it is `unknown` — never inferred from a
path that merely looks like a checkout.

### `mq.stack-provenance.v1`

What was observed across the layers, how the identities relate, and what to do
about it. This is what `mq-agent stack provenance --json` will return.

The name deliberately differs from the existing `mq_stack_runtime.v1`, which is
the `stack run` pipeline result. Two contracts whose names differ only in
punctuation, describing different things, would be exactly the confusion this
feature exists to detect.

The `installed` and `running` layers are `mq.runtime-identity.v1` records
**by reference**, not by description. There is one definition of what a runtime
is, and a layer that does not satisfy it fails validation rather than being
waved through as "an object" — which is what `RTP013_RUNTIME_IDENTITY_INVALID`
exists to name.

### Validating it

The reference is relative, so it resolves from the two schema files on disk and
never from the network. A validator built without both schemas registered will
raise `Unresolvable` rather than fetch anything — fail-closed, which is right,
but it means every consumer must supply the registry:

```python
registry = Registry().with_resources(
    [(s["$id"], Resource.from_contents(s)) for s in (identity, provenance)]
)
Draft202012Validator(provenance, registry=registry).validate(record)
```

Phase 0 keeps that helper in the contract tests, because nothing in `mq_agent`
produces a provenance record yet. Phase 1 moves it into module code alongside
the first producer.

## The five layers, kept apart

```text
             release
                │
                ▼
checkout ──→ installed ──→ running
```

Each edge answers a different question, so each is reported separately:

| Comparison | Question |
| --- | --- |
| `installed_matches_checkout` | Is the installed code the code in the checkout? |
| `running_matches_installed` | Is the running process the installed code? |
| `running_matches_checkout` | Is the running process the checkout's code? |
| `release_matches_checkout` | Does the release identity name the checkout? |
| `release_matches_installed` | Does the release identity name what is installed? |

There is no generic `synced`, `healthy`, `current` or `aligned` boolean, and
the schema tests forbid one. A single green flag over five different questions
answers none of them.

## `null` is not `false`

| Value | Meaning |
| --- | --- |
| `true` | checked, and the two identities match |
| `false` | checked, and they differ |
| `null` | not observed, or not applicable |

A CLI has no long-lived process, so `running_matches_installed` is `null` — not
`false`. Reporting `false` would invent a mismatch that nobody observed.

This is enforced by the schema, not left to discipline. When a layer is `null`,
every comparison against it must be `null` too:

| Layer absent | Comparisons forced to `null` |
| --- | --- |
| `running` | `running_matches_installed`, `running_matches_checkout` |
| `checkout` | `installed_matches_checkout`, `running_matches_checkout`, `release_matches_checkout` |
| `installed` | `installed_matches_checkout`, `running_matches_installed`, `release_matches_installed` |
| `release` | `release_matches_checkout`, `release_matches_installed` |

Every layer is required as a key. An observation that was not made is reported
as `null`, never omitted — a missing key and an unobserved layer would be
indistinguishable.

## Remote verification: three states, kept apart

`verified: false` alone cannot say whether anyone asked, so whether the run
asked is recorded separately:

| `verification_attempted` | `verified` | Meaning | Status |
| --- | --- | --- | --- |
| `false` | `false` | nobody asked — the default | `PASS` |
| `true` | `false` | asked, and the remote could not be reached | `UNAVAILABLE` |
| `true` | `true` | confirmed, with the SHA and the time | `PASS` |

The middle row is the one worth stating plainly. A remote that could not be
reached is an observation nobody could make. It is not `false`, not stale, and
never a comparison someone invents to fill the gap.

A component whose `remote.verified` is `true` must say what it saw and when:
`remote_origin_main`, `verified_at` and `verification_attempted` are all
required there, enforced by the schema. And a component cannot have been
verified in a run that contacted no remote — if the top-level `remote_verified`
is `false`, no component may claim otherwise.

The converse does not hold and is not enforced: `--refresh` may reach the
network and still fail for one repository.

A confirmed remote is one half of the comparison. The other half is a ref this
machine has, and a checkout without `refs/remotes/origin/main` — what
`actions/checkout` produces — never observed it. `RTP005` needs both halves:
a SHA differing from `null` is an absence, not a disagreement.

`--refresh` uses `git ls-remote`, never `fetch`. A query does not change the
checkout being observed; a fetch would write refs into it, and an observation
must not alter its subject.

**`--refresh` changes freshness, not semantics.** A finding means the same
thing whether `origin/main` came from disk or was confirmed against the
remote, and a dirty worktree is a dirty worktree either way.

## Status

| Status | Meaning |
| --- | --- |
| `PASS` | every identity that was available and relevant agrees |
| `WARN` | a real difference exists, and the command is still safe to run |
| `UNAVAILABLE` | an identity could not be observed |
| `FAIL` | identity data is malformed or self-contradictory, so the result is unusable |

An ordinary mismatch is `WARN`. `FAIL` is rare in a read-only surface, and
unknown is never automatically failure.

## Reason codes

The code is the API; the rendered text is the interface. A code is never
renumbered or reused once published.

| Code | Meaning |
| --- | --- |
| `RTP001_DIRTY_WORKTREE` | the checkout has uncommitted changes |
| `RTP002_HEAD_NOT_INTEGRATED` | HEAD is not reachable from the canonical ref |
| `RTP003_LOCAL_MAIN_STALE` | the locally known main is behind what is known of the remote |
| `RTP004_REMOTE_NOT_VERIFIED` | no remote was contacted; the default, not a problem |
| `RTP005_CHECKOUT_BEHIND_REMOTE` | a verified remote main is not the ref this checkout has |
| `RTP006_INSTALLED_IDENTITY_UNKNOWN` | the installed runtime could not be identified |
| `RTP007_INSTALLED_CHECKOUT_MISMATCH` | the installed code is not the checkout's code |
| `RTP008_RUNNING_IDENTITY_UNKNOWN` | the running process could not be identified |
| `RTP009_RUNNING_INSTALLED_MISMATCH` | the running process is not the installed code |
| `RTP010_RUNNING_CHECKOUT_MISMATCH` | the running process is not the checkout's code |
| `RTP011_RELEASE_VERSION_MISMATCH` | the declared version disagrees with the latest tag |
| `RTP012_RELEASE_COMMIT_MISMATCH` | the tag points at a commit that is not the one in question |
| `RTP013_RUNTIME_IDENTITY_INVALID` | a runtime reported an identity that fails its contract |
| `RTP014_REMOTE_UNAVAILABLE` | verification was requested and the remote could not be reached |
| `RTP015_GIT_PROBE_FAILED` | a git probe failed or timed out |
| `RTP016_CHECKOUT_HEAD_MISSING` | the checkout has no HEAD commit |
| `RTP017_CANONICAL_REF_MISSING` | the checkout has no canonical ref to compare against |

`RTP016` and `RTP017` are not in the original sketch. They were added because
`runtime_guard.check()` already reaches both states (`no-head`,
`no-canonical-ref`), and a code list that cannot name a state the system
already observes is incomplete on arrival.

## Next action

Exactly one, or none. The order is by dependency, not by severity:

1. an invalid or unidentifiable runtime
2. `installed` ↔ `checkout` mismatch
3. `running` ↔ `installed` mismatch
4. release commit mismatch
5. checkout behind a verified main
6. remote not verified

Reinstalling comes before restarting for a concrete reason. Given:

```text
checkout   new
installed  old
running    old
```

the next action is **not** "restart the process" — that starts the same stale
installation again. It is "reinstall from the current checkout"; only then does
a restart change anything.

## Provenance reports facts, not policy

Three separate layers:

```text
fact       running_matches_installed = false
status     WARN
policy     owned by whoever acts on the signal
```

The contract carries no `blocked`, `blocks_release`, or `may_write_evidence`
field, and the schema tests forbid them. Blocking decisions belong to the
operation:

* the **release cockpit** continues to own release blocking;
* **`runtime_guard`** continues to own whether a run may write production
  evidence, and may later consume `identity_quality`;
* an ordinary audit may proceed on `WARN`.

`mq-agent stack provenance` blocks nothing.

## Ownership

| Repo | Owns |
| --- | --- |
| `mq-agent` | identity primitives, aggregation, comparison semantics, status and reason codes, the JSON contract, the CLI |
| `mq-mcp` | its own live runtime identity, self-reported |
| `mq-hal` | presentation only — no provenance engine of its own |
| `mqobsidian` | the contract, ownership and decision record as durable memory, never live truth |

## Two rules

> **Never infer identity when the producer can report it.**

A live process reports which commit it is running. `mq-agent` does not guess
that from the working directory, a PID's path, the repo path, or the most
recently installed package.

> **Never collapse multiple identity questions into one green boolean.**

## Scope of Phase 0

Delivered: the two contracts, status semantics, the reason-code registry, null
semantics, next-action precedence, ownership, blocker policy, and the tests
that hold them.

Not delivered, and deliberately: any implementation. No runtime is instrumented,
no CLI command exists yet, `mq.execution-outcome.v1` is untouched, and no
historical evidence record is rewritten or backfilled. Runtime provenance
applies to new evidence from its introduction forward.
