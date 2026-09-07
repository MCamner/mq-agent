"""Pure deterministic selection; availability never follows from metadata alone."""

from graphlib import TopologicalSorter

from mq_agent.skills.profile import TaskProfile
from mq_agent.skills.vocabulary import reason


def select_skills(
    profile: TaskProfile, inventory: dict, vocabulary: dict
) -> tuple[dict, list[dict]]:
    requested = ["codex", "claude"] if profile.target == "both" else [profile.target]
    reasons = list(inventory["reasons"])
    missing, candidates, explanations = [], [], []
    for entry in inventory["entries"]:
        data = entry["profile"]
        name = data["skill"]
        matched = {
            key: sorted(set(data[key]) & set(getattr(profile, key)))
            for key in ("intents", "domains", "risks")
        }
        required = bool(set(profile.risks) & set(data["required_for"]))
        relevance = (
            sum(bool(values) for values in matched.values()),
            sum(map(len, matched.values())),
            "repo" in data["scope"],
        )
        why = "no matching facets"
        # An explicit opposing intent prevents broad domain-only false positives.
        relevant = required or (
            any(matched.values())
            and not (data["intents"] and profile.intents and not matched["intents"])
        )
        available = [
            t
            for t in requested
            if t in data["supported_targets"]
            and t in entry["discoverable_targets"]
            and data["status"] == "active"
        ]
        if relevant:
            for t in requested:
                if t not in data["supported_targets"]:
                    reasons.append(
                        reason(
                            "SKS009_TARGET_UNSUPPORTED",
                            "Skill does not support requested target.",
                            name,
                            t,
                        )
                    )
                elif t not in available:
                    reasons.append(
                        reason(
                            "SKS004_SKILL_NOT_DISCOVERABLE",
                            "Active source skill not observed for target.",
                            name,
                            t,
                        )
                    )
            absent = [t for t in requested if t not in available]
            if required and absent:
                missing.append({"skill": name, "targets": absent})
                for t in absent:
                    reasons.append(
                        reason(
                            "SKS005_REQUIRED_SKILL_UNAVAILABLE",
                            "Required skill unavailable for requested target.",
                            name,
                            t,
                        )
                    )
            why = "unavailable" if not available else "candidate"
            if available:
                candidates.append(
                    (
                        required,
                        relevance,
                        data,
                        {
                            "skill": name,
                            "requirement": "required" if required else "recommended",
                            "discoverable_targets": available,
                            "matched": matched,
                        },
                    )
                )
        elif any(matched.values()):
            why = "explicit task intent does not match skill intents"
        explanations.append({"skill": name, "decision": why, "matched": matched})
    candidates.sort(key=lambda c: (-int(c[0]), *(-int(x) for x in c[1]), c[2]["skill"]))
    # Process superseders before their targets, independent of alphabetic order.
    suppressors: dict[str, list[str]] = {c[2]["skill"]: [] for c in candidates}
    for _, relevance, data, _ in candidates:
        for other_required, other_relevance, other, _ in candidates:
            if (
                not other_required
                and other["skill"] in data["supersedes"]
                and relevance >= other_relevance
            ):
                suppressors[other["skill"]].append(data["skill"])
    suppressed = set()
    for name in TopologicalSorter(suppressors).static_order():
        active = [other for other in suppressors[name] if other not in suppressed]
        if active:
            suppressed.add(name)
            reasons.append(
                reason("SKS006_SKILL_SUPERSEDED", f"Superseded by {active[0]}.", name)
            )
    kept = [c for c in candidates if c[2]["skill"] not in suppressed]
    required_count = sum(c[0] for c in kept)
    budget = max(
        0,
        min(
            vocabulary["max_optional_skills"],
            vocabulary["max_selected_skills"] - required_count,
        ),
    )
    selected = [c[3] for c in kept if c[0]] + [c[3] for c in kept if not c[0]][:budget]
    if len(selected) < len(kept) or required_count > vocabulary["max_selected_skills"]:
        reasons.append(
            reason(
                "SKS007_SELECTION_BUDGET_APPLIED",
                "Optional selection bounded; all available required skills retained.",
            )
        )
    chosen = {item["skill"] for item in selected}
    for entry in explanations:
        if entry["skill"] in chosen:
            entry["decision"] = "selected"
        elif entry["skill"] in suppressed:
            entry["decision"] = "superseded"
        elif entry["decision"] == "candidate":
            entry["decision"] = "budget"
    state = (
        "invalid"
        if inventory["reasons"]
        else "partial"
        if missing
        else "complete"
        if selected
        else "empty"
    )
    if state == "empty":
        reasons.append(
            reason("SKS008_NO_MATCH", "No eligible skills matched the task.")
        )
    return dict(
        selected=selected,
        missing_required=missing,
        selection_state=state,
        reasons=reasons,
        candidate_count=inventory["candidate_count"],
    ), explanations
