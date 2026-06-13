# Repo Aware

Use the repository's `repo-aware` skill before answering or changing this
repository.

Primary skill file:

```text
skills/repo-aware/SKILL.md
```

Canonical Codex fallback:

```text
/Users/mansys/.codex/skills/repo-aware/SKILL.md
```

First read the primary skill completely. If it is missing, read the canonical
fallback completely. If both exist, use the local skill for repo-specific facts
and the canonical skill for the general repo-first workflow.

Default inspection pass:

```bash
git status --short
rg --files
sed -n '1,220p' README.md
```

If `repo-signal` is available and relevant, use it as context:

```bash
repo-signal doctor
repo-signal analyze
```

User request:

```text
$ARGUMENTS
```

After inspecting, do the smallest grounded action that helps the request.
Preserve user changes, update docs or smoke tests when command behavior changes,
and report what was changed and verified.
