# Release checklist

Use this before tagging a release.

## Pre-release

- [ ] All tests pass: `pytest tests/ -v`
- [ ] Ruff clean: `ruff check mq_agent/`
- [ ] Type check passes: `mypy mq_agent/ --ignore-missing-imports`
- [ ] `mq-agent doctor` passes (OPENAI_API_KEY, git, uv, Python)
- [ ] `mq-agent release-check --json` returns `"ready": true`
- [ ] GitHub Actions CI is green on `main`

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
- [ ] Push: `git push origin main --tags`
- [ ] GitHub Release created with CHANGELOG excerpt as body

## Post-release

- [ ] Bump version in `pyproject.toml` to next dev version
- [ ] Add `## [Unreleased]` section to CHANGELOG
