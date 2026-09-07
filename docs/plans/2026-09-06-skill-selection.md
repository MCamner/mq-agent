# Skill Selection Implementation Plan

## Goal

Select task-relevant skills deterministically from local metadata and observed discovery.

## Owner repo

mq-agent

## Secondary repos

mqobsidian

## Architecture boundary

mqobsidian owns vocabulary and the three JSON schemas. Source repos own profiles.
mq-agent owns inventory, profiling, selection and rendering. No selector in other repos.

## Non-goals

Learning, embeddings, remote calls, ecosystem audit CLI changes, and context-pack.v2.

## Approval gates

- File writes: authorized by the implementation request.
- Commit/push/merge: outside this implementation request.
- Deletion/settings: not needed.

## Test gates

Use the existing environment's Python with `-m pytest tests/test_skill_selection.py tests/test_context_pack_cmd.py -q`.
Run `-m mq_agent.main skills route` with the contract worktree as `--vault`.
Run schema validation in mqobsidian, then `git diff --check` in both repos.

## Rollback

Revert only this feature's files/patches; isolated worktrees preserve original branches.

## Tasks

1. Add `.mq/skill-selection-vocabulary.json`, three `schemas/*skill*.v1.json`
   contracts, and `docs/skill-selection.md` in mqobsidian.
2. Add `tests/test_skill_selection.py` before the implementation.
3. Add `mq_agent/skills/{vocabulary,inventory,profile,selector,route,render,cli}.py`.
   Profile eight existing skills beside their owned SKILL.md files; validate copies.
4. Register CLI in `mq_agent/main.py`; integrate Markdown in
   `mq_agent/tools/context_pack.py` without changing context-pack.v1 JSON fields.
5. Document commands in `docs/SKILL_SELECTION.md`, README and CHANGELOG;
   validate deterministic output, missing contracts, discovery, budgets and supersession.

## Decisions

- Optional candidates with explicit, disjoint task intents are ineligible. This
  prevents repo-audit being recommended for implementation solely through `repo`.
- Unprofiled skills remain visible in inventory but are not routing candidates.
- Contradictory copies are invalid metadata; readable discovery alone is not identity.
- Target `both`: optional skills may serve one target; required skills need both.
- Context pack shows routing failures explicitly in Markdown; the standalone route
  remains the machine contract, with no new context-pack.v1 fields.
