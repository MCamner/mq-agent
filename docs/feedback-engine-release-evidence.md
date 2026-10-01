# Feedback Engine v1.30 release evidence

Recorded from PR #324's `feedback-real-run` CI job on 2026-10-01.

The job used the production Feedback Engine code against two real MQ Git
repositories. It used a generated public-safe context vault so release CI does
not depend on an operator's private memory.

## Real shadow runs

| Repository | Snapshot | Verdict | Context bytes delta | Latency delta | Source count delta |
| --- | --- | --- | ---: | ---: | ---: |
| `MCamner/mq-agent` | `e73107e110610229363fafc798c54a12bfa859f4` | `INSUFFICIENT_EVIDENCE` | +617 | -0.045 ms | 0 |
| `MCamner/mq-mcp` | `84c23324d0da0a3f568b8cc10de1cbdd6f332539` | `INSUFFICIENT_EVIDENCE` | +615 | -0.059 ms | 0 |

## What was observed

- Both active and shadow collections completed on clean pinned Git snapshots.
- The shadow strategy added CodeGraph guidance, increasing context by roughly
  0.6 KiB in both repositories.
- Source identity count did not change.
- The measured latency deltas were below 0.1 ms and far below the Feedback
  Engine's material latency threshold.
- Token count remained `unavailable` because F2 does not call a tokenizer.
- No external API calls or model preference were needed for the operational
  comparison.

## Gains

No material quality gain is claimed from these runs.

The only lower-is-better movement was a sub-millisecond latency difference,
which is below the materiality threshold and should be treated as measurement
noise rather than a release claim.

## Limitations

- No explicit relevance fixture was supplied, so a quality verdict is
  intentionally impossible.
- The CI vault contains public-safe release cards, not an operator's private
  mqobsidian context.
- CodeGraph is represented as bounded context-selection guidance here; the run
  does not claim that a live CodeGraph query improved retrieval.
- Context tokens are not measured.
- Evidence from two repositories does not generalize to every MQ task class.

## Release interpretation

These runs prove the F2 machinery can compare active and shadow context on real
MQ repositories without changing production behavior.

They do **not** justify activation. Any future activation gate remains
post-v1.30 and requires task-class-specific evidence plus human approval.
