"""Plain, bounded human output; codes stay independent of prose."""


def render_route(route: dict, explanations: list | None = None) -> str:
    lines = [
        "SKILL SELECTION",
        f"Task: {route['task']}",
        f"Repo: {route['repo']}",
        f"Target: {route['target']}",
        "",
    ]
    for key, values in route["profile"].items():
        lines.append(f"{key}: {', '.join(values) or 'none'}")
    lines.extend(["", render_pack_section(route)])
    lines.append(
        f"{len(route['selected'])} skills selected from {route['candidate_count']} candidates"
    )
    if explanations is not None:
        lines.append("\nExplain")
        for entry in explanations:
            matches = ", ".join(
                value for values in entry["matched"].values() for value in values
            )
            lines.append(
                f"{entry['skill']}: {entry['decision']} ({matches or 'no facets'})"
            )
    return "\n".join(lines)


def render_pack_section(route: dict) -> str:
    lines = [
        "## Selected skills",
        "",
        f"Selection: {route['selection_state']} ({route['target']})",
        "",
    ]
    for item in route["selected"]:
        matches = ", ".join(
            value for values in item["matched"].values() for value in values
        )
        lines.append(
            f"* `{item['skill']}` — {item['requirement']}; {', '.join(item['discoverable_targets'])}; {matches or 'required risk'}"
        )
    for item in route["reasons"]:
        lines.append(
            f"* {item['code']}: {item['skill'] or 'selection'}{(' / ' + item['target']) if item['target'] else ''} — {item['message']}"
        )
    return "\n".join(lines) + "\n"
