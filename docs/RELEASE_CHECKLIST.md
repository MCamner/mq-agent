# Release checklist

Use this before tagging a release.

## Pre-release

- [ ] Create a release-prep branch: `git switch -c chore/release-vX.Y.Z`
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Ruff clean: `ruff check mq_agent/`
- [ ] Type check passes: `mypy mq_agent/ --ignore-missing-imports`
- [ ] `mq-agent doctor` passes (OPENAI_API_KEY, git, uv, Python)
- [ ] `mq-agent release-check --json` returns `"ready": true`
- [ ] Push branch: `git push -u origin chore/release-vX.Y.Z`
- [ ] Open PR: `gh pr create --base main --head chore/release-vX.Y.Z`
- [ ] GitHub Actions CI is green on the PR

## Documentation

- [ ] `CHANGELOG.md` updated with release date and all changes
- [ ] `README.md` reflects current feature set
- [ ] Version in `pyproject.toml` updated
- [ ] `docs/ROADMAP.md` updated

## Safety

- [ ] No secrets, API keys or `.env` files in commits
- [ ] No hardcoded paths or machine-specific config
- [ ] `.gitignore` covers all sensitive file patterns

## Release

- [ ] Commit: `git commit -m "chore: release vX.Y.Z"`
- [ ] Tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`
- [ ] Merge the release PR into protected `main`
- [ ] Pull the merged `main`: `git switch main && git pull --ff-only`
- [ ] Push tag from merged `main`: `git push origin vX.Y.Z`
- [ ] GitHub Release created with CHANGELOG excerpt as body

## Post-release

- [ ] Bump version in `pyproject.toml` to next dev version
- [ ] Add `## [Unreleased]` section to CHANGELOG
- [ ] Publish the command reference to the wiki:
      `bash scripts/publish-wiki-command-ref.sh` (warn-only — a publishing
      failure never invalidates the release)
