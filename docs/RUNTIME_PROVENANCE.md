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

`commit` is a git object name, and the recorded system decides — never the
shape of the string. PEP 610 covers version control systems that number their
revisions, and `svn` revision `1234567` is seven characters that all happen to
be valid hex: indistinguishable from an abbreviated SHA to a pattern, and a
different thing entirely. A revision this contract cannot express is absent.

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

**A distribution name is not a subject.** `distribution("mq-agent")` finds a
distribution by name, and a virtualenv can hold one while the running code was
imported from somewhere else. Version, commit and install type all come from
the distribution shown to own the imported *file* — through its own `RECORD`,
or through the directory an editable install records. Sharing a site-packages
is proximity, not ownership.

Getting this wrong is not a cosmetic error. An editable stranger pointing at
another checkout hands over that checkout's HEAD, which reads as a mismatch
against this one, and nothing about the record looks wrong. Once a mismatch
gates anything, that stranger would refuse a legitimate run.

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

`installed` and `running` are answered by different parties. A runtime reads
its own distribution metadata; nothing reads another environment's. So
`installed` is null for any component this process did not install, and the
component itself is the only source for `running`.

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

## Asking a live component: three states, kept apart

`running: null` cannot say why. mq-agent is a CLI with no process of its own to
ask; mq-mcp may be installed and simply not started. Those are different facts,
so `running_probe` records whether anyone asked:

| `attempted` | `reachable` | Meaning | Finding |
| --- | --- | --- | --- |
| `false` | `null` | nobody asked — a CLI has no process | none |
| `true` | `false` | asked, and nothing answered | none |
| `true` | `true` | something answered | depends on what it said |

A component that is not running is not a fault and not an unknown identity:
there is no process, so there is nothing whose identity could be unknown. It
produces no reason code.

**A status code is an answer.** `reachable` is false only when the connection
was refused or the request itself failed. A component running a build from
before the route existed replies `404`, and calling that unreachable would make
a live process look exactly like a stopped one — the distinction this probe
exists to draw. It answered and could not be identified, which is `RTP008`.

Once something answers, what it said decides:

| Answer | Result |
| --- | --- |
| a valid record | `running` is that record |
| not `200` | `RTP008` — running, and unidentifiable |
| `200` with a record that fails validation | `RTP013` |
| `200` with something that is not a record | `RTP013` |
| a valid record whose `identity_quality` is `unknown` | `RTP008` |
| a valid record naming a different component | `RTP013` |

That last row is the producer's lesson applied to the consumer: the contract
accepts any component name, so a perfectly valid record can describe something
else. Filed under `mq-mcp`, it makes the provenance record contradict itself.
Both identity layers are checked this way.

**An identity that fails either check is not half of a comparison.** Naming the
contradiction is not enough: a rejected record still carries a commit, and using
it would report the component at a commit nobody ever saw it on — and tell an
operator to restart it on that basis. The comparison stays `null`, because
nothing was compared.

The schema closes the probe to exactly those three states: an unattempted probe
carries no endpoint and no reachability, an attempted one carries both, and a
reported identity requires `attempted` and `reachable` to be true. `attempted:
true` with `reachable: null` would claim a question was asked whose answer
nobody wrote down.

All of it is stated **per component** — an `if` over `items` holds only when
every component matches, so at the array level one component reporting an
identity would go unchecked whenever another reported none.

mq-agent produces no identity for another component. It asks, validates, and
compares; `installed` stays null for mq-mcp because this process can read its
own distribution metadata and not another environment's.

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

## Attribution on an execution record

An execution outcome can say which code produced it, as an optional
`runtime_fingerprint` on `mq.execution-outcome.v1` (mqobsidian DEC-006):

```json
{"component": "mq-agent", "version": "1.28.0", "commit": "1f7fdd7…", "identity_quality": "verified"}
```

Four fields, and a **projection** rather than an observation. `runtime_guard`
already observes and validates this runtime's identity before deciding the run
may write evidence; the fact then travels as data:

```text
guard observes and validates  →  the verdict carries it  →  projected  →  record
```

Observing it again in the writer would give the stack two producers of one
truth, free to disagree — and the second would read the checkout at write time,
attributing a run to whatever the tree had become by then. That is the drift
this release exists to expose, produced by the field meant to expose it.

Everything else `mq.runtime-identity.v1` carries — install type, start time,
executable, module and source paths — stays out. It answers how a runtime was
installed and where it lives, and a shared evidence store is not the place for
one operator's disk layout.

The field is absent when no identity was established, which is a fact about the
observation rather than about the runtime. That happens when the evidence
stores are redirected: the guard does not run, so nothing established what to
attribute. Absence keeps its usual meaning — not observed.

## Why the guard does not gate on RTP007

The obvious use of `installed_matches_checkout` is to refuse a run whose
installed code is not the checkout's. `runtime_guard` deliberately does not,
because for mq-agent that state is not reachable:

| Runtime | Why it cannot differ |
| --- | --- |
| editable | its commit is read from the tree the imported file lives in |
| wheel | no checkout layer; `repository_root()` is null and the guard allows |
| a distribution sharing the name | bound to the imported file, so it supplies nothing |

The third row used to be the exception, and it was false every time. Binding
installation metadata to the imported code closed it — and closed the only
route to the signal with it.

Written down because the next person will otherwise implement the same dead
gate. What the guard does ask is narrower and does happen: *can this process
express an internally valid identity?* An observation that raises, or a record
that contradicts its own contract, refuses. `unknown` and `partial` do not —
absence of knowledge is allowed, contradiction is not.

The reachable drift is `running` against `checkout`: a live process from one
commit while its checkout moved to another, demonstrated for mq-mcp in Phase 4.
That signal is real. The next section is about where it may be used.

## Why the guard does not gate on RTP010 either

RTP010 is the reachable finding RTP007 was not: a live component running code
its checkout has left behind. The tempting next step is to refuse execution
while any component in the stack reports it.

> **A provenance mismatch becomes an execution policy input only when the
> mismatched component participates in that execution. Presence in the stack is
> not dependency.**

That rule was applied to mq-agent by measurement rather than argument. Of the
nine entrypoints that establish a recordable runtime before executing, exactly
one touches mq-mcp at all:

| | |
| --- | --- |
| guarded execution paths | 9 |
| paths that reach mq-mcp | 1 — `signal` |

And the single contact is outside the execution it appears to belong to. In
`signal`, the execution record opens and closes around the agent run; the MCP
call happens afterwards, under `if brain and not dry_run`, and it *writes* a
review rather than supplying an input the result depends on:

```text
_require_recordable_runtime()      the identity is established
with _execution_outcome(...)       the run happens and is recorded
...                                the record is closed
if brain and not dry_run:          MultiMCPBridge() — a write, 48 lines later
```

So the dependency cone of mq-agent's guarded executions is empty. A stale
mq-mcp cannot make an mq-agent execution unattributable, because no mq-agent
execution consumes mq-mcp. A stack-wide RTP010 gate would refuse nothing —
the same shape as the RTP007 gate above, found the same way.

RTP010 therefore stays where it is useful and true:

* **provenance and dashboard** — reported as `WARN` with its restart action;
* **the release gate** — a release claims something about the whole stack, so
  stack-level staleness is legitimately its business;
* **an operation that consumes the component** — dependency-specific policy,
  decided per operation.

The remaining edge is `signal --brain`, which writes into a possibly stale
mq-mcp. That is an ingress question — whether mq-mcp should accept evidence
under a runtime identity it knows is behind its checkout — and it belongs to
mq-mcp, not to this guard.

The rule to apply before building any future gate:

```text
operation depends on component X          not:   stack contains RTP010
        + X has RTP010                                    ↓
              ↓                                    block mq-agent
    operation-specific policy
```

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
