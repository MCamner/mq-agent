---
name: mq-secrets-public-safe
description: Scans MQ repos for secrets, private paths, unsafe generated context, and public-boundary leaks before commits, releases, or publishing. Use before public PRs, generated AGENTS/CLAUDE files, CI changes, or repo publication.
---

# MQ Secrets Public Safe

Use this skill before publishing, committing generated context, opening public PRs, or changing CI/CD.

## MQ principle

Public output must contain contracts and portable placeholders, not private machine state.

## Scan targets

Check:

- secrets
- tokens
- session cookies
- private absolute paths
- hostnames/usernames
- local-only config
- generated context surfaces
- CI/CD env usage

## Fast scan

```bash
git status --short
git diff --stat
git grep -n '/Users/' || true
git grep -niE '<your-username>|<your-hostname>|<location>' || true   # tune locally; do not commit real identifiers
git grep -n 'ghp_\|github_pat_\|sk-[A-Za-z0-9]\|xoxb-' || true
git grep -n 'JSESSIONID\|password\|passwd\|secret\|token\|api_key' || true
```

When a match is a safe example, mark it explicitly as example/test/docs.

## MQ generated-context rule

Allowed:

```text
$MQ_OBSIDIAN_DIR
<path-to-repo>
<set-via-env>
```

Not allowed in public committed files:

```text
/Users/<name>/...
C:\Users\<name>\...
real PAT/token/session/cookie values
machine-specific server names unless intentionally documented
```

## CI/CD rules

Check:

- secrets are referenced through GitHub Actions secrets or environment variables
- no secrets are echoed in logs
- no deploy IDs or tokens are hardcoded
- destructive workflows require branch/environment protection
- public-safe scan runs before publishing generated files

## Rotation response

If a real secret is found:

1. Do not print it.
2. Identify file and type only.
3. Recommend immediate rotation.
4. Recommend removal from Git history if committed.
5. Add prevention gate.

Output:

```md
## Secret/public-safe finding

- File: `path`
- Type: token/private-path/session-cookie/etc.
- Committed? yes/no/unknown
- Risk: low/medium/high
- Required action: rotate/remove/sanitize
```

## Final report

```md
## Public-safe summary

| Check | Result | Notes |
|---|---|---|
| Private paths | pass/fail | |
| Tokens/secrets | pass/fail | |
| Generated context | pass/fail | |
| CI/CD leakage | pass/fail | |

## Required fixes
- <fix>

## Safe to publish?
Yes/No
```

## Guardrails

Never:

- display full secret values
- commit cleanup without approval
- assume generated files are safe without scanning
- replace secrets with fake-looking real tokens; use placeholders only
