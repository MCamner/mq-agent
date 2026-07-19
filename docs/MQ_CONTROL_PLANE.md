# MQ Control Plane

`mq-agent` is the control plane for the local MQ ecosystem. It should
orchestrate the loop without absorbing the responsibilities of the other repos.

## Boundary

```text
mqlaunch → starts
mq-agent → orchestrates
repo-signal → measures
mq-mcp → reviews, learns, and retrieves memory
mqobsidian → remembers
ollama → reasons locally
mq-hal → presents operator state
```

The key rule is simple: `mq-agent` coordinates and gates work; it does not
reimplement repo analysis, review logic, memory retrieval, model inference, or
operator presentation.

## System Map

```mermaid
flowchart TD
    operator[Operator] --> launch[mqlaunch]
    launch --> agent[mq-agent]

    agent --> runtime[stack run]
    runtime --> signal[repo-signal]
    runtime --> mcp[mq-mcp]
    runtime --> truth[truth-export]
    runtime --> release[release gates]

    signal --> repoIntel[repo health and publish signals]
    mcp --> review[review]
    mcp --> learn[learn]
    mcp --> memory[semantic memory]
    truth --> obsidian[mqobsidian]
    release --> ci[GitHub Actions gates]

    obsidian --> decisions[decisions and durable truth]
    obsidian --> timeline[reviews, learn notes, releases]
    mcp --> ollama[Ollama local models]
    agent --> hal[mq-hal]
```

## Canonical Runtime

The current runtime entrypoints are:

```bash
mq-agent stack run
mq-agent run --stack
```

The stack runtime checks:

```text
repo-signal
mq-mcp
ollama
brain export
release
```

It is read-only by default. `--brain` writes the stack truth export only when
paired with `--approve`.

```bash
mq-agent stack run --dry-run
mq-agent stack run --json
mq-agent stack run --markdown
mq-agent stack run --brain --approve
mq-agent stack run --ci
```

## Canonical Pipeline

The v1.16 consolidation defines one operator flow. `stack run` includes this
pipeline in both JSON and Markdown output:

```text
discover
→ repo-signal
→ review
→ learn
→ truth-export
→ release
→ dashboard
```

Existing commands can remain as focused escape hatches, but the default
operator path should be the runtime pipeline.

## Memory Direction

The next leverage point is making `mqobsidian` more than an export target.

Planned memory surfaces:

```bash
mq-agent memory ingest
mq-agent memory query
mq-agent memory summarize
mq-agent memory timeline
```

Target vault shape:

```text
mqobsidian/
├── truth/
├── reviews/
├── learn/
├── releases/
├── architecture/
└── decisions/
```

This should allow old decisions, reviews, learned patterns, and release truth
to feed later reviews and stack runs.

## Model Direction

Ollama is becoming a first-class runtime dependency rather than an incidental
learn backend.

Model profiles:

```text
fast
review
planner
memory
```

Runtime roles:

```text
qwen3:4b-instruct → general fast, planner, and review work
mq-learn → structured pattern extraction
bakllava → vision only
llama3.2 → base/fallback model; no separate MQ profile
```

The current scope does not introduce a local vector store, embedding runtime,
embedding model, additional `llama3.2` profile, or `mq-learn-fast` /
`mq-learn-deep` variants.

Future gates:

* Consider a local vector store only after an isolated test with a dedicated
  embedding model and 20–50 real mqobsidian queries shows a measurable
  retrieval improvement.
* Consider a deep learn profile only when real reviews are truncated or
  regularly require more than 4096 context tokens.

Runtime surface:

```bash
mq-agent models list
mq-agent models current
mq-agent models doctor
mq-agent models switch qwen3:4b-instruct --profile review --approve
mq-agent models bench
mq-agent models bench mq-learn --json
```

The benchmark uses Ollama's local generate API and returns load/total duration,
prompt and output token counts, tokens per second, and JSON/schema validity.
Models are unloaded after the request by default; use `--keep-alive` to retain
them explicitly.

## Dashboard Direction

`mq-agent dashboard` should come before HAL owns a polished presentation layer.
The first dashboard should be a TUI over existing facts:

```text
Stack Health
Brain
Release
Contracts
Memory
Models
```

## Release Discipline

`mq-agent doctor` is already the environment check. The release-facing version
of this should verify:

```text
VERSION
CHANGELOG
README
ROADMAP
repo-contract
CI
tag state
```

## Current Priority

The next high-value sequence is:

```text
mq-agent
→ memory
→ mqobsidian
→ ollama
```

That keeps the control plane useful without making it too broad.
