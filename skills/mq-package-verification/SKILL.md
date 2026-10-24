---
name: mq-package-verification
description: Verify MQ Python distributions from built artifacts in an isolated installation when packaging, entrypoints, dependencies, or bundled schemas and assets change. Use for "works in checkout but fails after install", "test the wheel", or "verify packaged resources".
---

# MQ Package Verification

Verify the artifact users install, separately from checkout tests. Apply to the
requested Python repo; do not assume mq-agent's build backend or commands apply
to every MQ package. Ordinary code edits without packaging impact do not need
this workflow.

## Discover the existing path

Read `pyproject.toml`, packaging tests and CI build/install jobs in the target
repo. Reuse their build backend, dependency extras and smoke commands.
In mq-agent, `tests/test_packaging.py` already builds a wheel, checks declared
resources against its contents and parses packaged schemas. Run that coverage;
do not introduce another resource inventory. It does not by itself prove a
clean installed entrypoint works.

## Verify the installation

1. Record the source revision and dirty state. Build into a temporary directory
   with the repository's supported build command; retain the exact artifact path.
2. Create a fresh virtual environment and install that artifact, not an editable
   checkout. Install only the dependencies/extras required for the requested flow.
3. Run from an empty directory outside the source tree, without `PYTHONPATH`
   or another checkout injected into imports. Confirm the imported module path
   and distribution version belong to this environment.
4. Invoke the installed executable by its environment path. Check help/version
   plus a bounded command that actually loads the changed schema, template or
   asset. Inspect its output and exit status. Stub external services only when
   explicitly reporting the result as a stubbed check.
5. Check required resources in the built artifact against runtime loaders and
   existing tests. Report missing dependencies or skipped builds as unverified.

Keep build caches, outputs and telemetry in scratch locations. Do not publish,
replace the user's installed runtime, fetch model weights or use production
stores as part of this check. Dependency downloads remain subject to the
current environment's permissions.

## Report

State artifact identity, install type, imported path, commands run, resource
coverage, failures and skipped checks. A passing checkout suite is separate
evidence from a passing installed-package smoke test. Return to the target
repo's release skill for the remaining release gates.

## Routing examples

- "Test the wheel after adding a schema" → use this skill.
- "The installed CLI cannot find a template" → use this skill.
- "Change a help sentence" → use the repo's CLI/docs workflow.
- "Publish the release" → use release-readiness; this skill grants no publication authority.
