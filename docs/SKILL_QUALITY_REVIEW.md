# Skill Quality Review

MQ Skill System v2.0 scores stable skills on five release-readiness criteria.
The check is deterministic and runs through `scripts/check-skill-quality.sh`.

| Criterion | Requirement |
| --------- | ----------- |
| Trigger clarity | `When to use` and should-trigger evals exist |
| Responsibility boundary | `When not to use` plus boundary/workflow/never rules exist |
| Output format | repo-local `SKILLS.md` declares `Outputs:` |
| Verification | skill doc includes inspection, checks or verification guidance |
| Overlap risk | should-not-trigger evals route near misses to the right owner |

## Current Scores

| Skill | Score | Status |
| ----- | ----: | ------ |
| `ci-diagnosis` | 5/5 | PASS |
| `mq-mcp-review-orchestration` | 5/5 | PASS |
| `release-readiness` | 5/5 | PASS |
| `repo-audit` | 5/5 | PASS |
| `signal-assessment` | 5/5 | PASS |
| `visual-analysis` | 5/5 | PASS |

Minimum passing score: `4/5`.

## Release Check

```bash
bash scripts/check-skill-quality.sh
```

`release-check.sh` runs this after skill contract validation.
