"""Human rendering for the read-only execution efficiency report."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table


def render_efficiency(data: dict[str, Any], console: Console) -> None:
    def cell(value: Any) -> str:
        return "unknown" if value is None else str(value)

    execution = data["execution"]
    quality = execution["quality"]
    console.print(f"Execution efficiency: {data['status']}")
    console.print(
        f"Quality: {quality['complete_successes']} complete successful executions / "
        f"{quality['completeness_measured']} with measured coverage; "
        f"{quality['completeness_missing']} missing completeness measurements."
    )
    table = Table(title="Quality cohorts")
    for title in ("Task", "Runtime", "Model", "Commit", "Scope", "Runs", "Complete OK"):
        table.add_column(title)
    for group in execution["cohorts"]:
        table.add_row(group["task_class"], group["runtime"], cell(group["model"]),
                      (group["producer_commit"] or "unknown")[:12], group["metric_scope"],
                      str(group["outcomes"]), str(group["quality"]["complete_successes"]))
    console.print(table)
    table = Table(title="Resources (measured populations)")
    for title in ("Metric", "Measured", "Missing", "Subtotal", "Full total", "Median", "P90"):
        table.add_column(title)
    for name, metric in execution["resources"].items():
        table.add_row(name, str(metric["measured"]), str(metric["missing"]),
                      cell(metric["measured_total"]), cell(metric["total"]),
                      cell(metric["median"]), cell(metric["p90"]))
    console.print(table)
    routing = data["routing"]
    console.print(
        f"Routing (independent population): {routing['escalated']} escalations / "
        f"{routing['observations']} observations; {routing['linked_selected_executions']} "
        "observations explicitly linked to selected executions."
    )
    console.print("Rework: unknown; retries are not rework. Cost uses recorded producer units.")
    console.print("Mixed token/tool scopes have no combined totals; inspect JSON cohorts.")
    console.print("Runtime coverage does not establish model-answer quality. No policy change is authorized.")
    for issue in data["issues"]:
        console.print(f"Issue: {issue}")
