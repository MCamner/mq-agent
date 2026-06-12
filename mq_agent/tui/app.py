"""Textual TUI for mq-agent — HAL-style dashboard."""
from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Log,
    Static,
)

from mq_agent import __version__

COMMANDS = [
    ("audit .", "audit ."),
    ("score .", "score ."),
    ("signal .", "signal ."),
    ("docs-audit .", "docs-audit ."),
    ("release-plan", "release-plan"),
    ("release-check", "release-check"),
    ("fix-ci", "fix-ci"),
    ("repo-summary .", "repo-summary ."),
    ("doctor", "doctor"),
    ("tools", "tools"),
    ("mcp status", "mcp status"),
    ("mcp tools", "mcp tools"),
    ("dashboard", "dashboard"),
    ("stack cockpit", "stack cockpit"),
    ("stack run", "stack run"),
    ("models current", "models current"),
    ("memory summarize", "memory summarize"),
]


def command_for_item_id(item_id: str | None) -> str | None:
    """Return the CLI command represented by a sidebar ListItem id."""
    if not item_id or not item_id.startswith("cmd-"):
        return None
    try:
        idx = int(item_id[4:])
    except ValueError:
        return None
    if idx < 0 or idx >= len(COMMANDS):
        return None
    return COMMANDS[idx][1]


CSS = """
Screen {
    background: $surface;
}

#sidebar {
    width: 28;
    border-right: solid $primary-darken-2;
    padding: 0 1;
}

#sidebar-title {
    text-align: center;
    text-style: bold;
    color: $primary;
    padding: 1 0;
}

#output {
    padding: 1 2;
}

#dashboard {
    height: auto;
    margin-bottom: 1;
}

.panel {
    width: 1fr;
    min-height: 5;
    border: round $primary-darken-2;
    padding: 0 1;
    margin-right: 1;
}

.panel-title {
    text-style: bold;
    color: $primary;
}

#log {
    height: 8;
    min-height: 8;
}

ListView {
    border: none;
    background: transparent;
}

ListItem {
    padding: 0 1;
}

ListItem:hover {
    background: $primary-darken-3;
}

ListItem.--highlight {
    background: $primary-darken-2;
}

#status-bar {
    height: 1;
    background: $primary-darken-3;
    color: $text-muted;
    padding: 0 2;
}
"""


class CommandListView(ListView):
    """Sidebar list that treats activation as running the highlighted command."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("enter", "run_selected", "Run", show=False),
        Binding("space", "run_selected", "Run", show=False),
        Binding("x", "run_selected", "Run", show=False),
        Binding("up", "cursor_up", "Cursor up", show=False),
        Binding("down", "cursor_down", "Cursor down", show=False),
    ]

    async def action_run_selected(self) -> None:
        await self.app.action_run_selected()  # type: ignore[attr-defined]

    async def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space", "x"}:
            event.prevent_default()
            event.stop()
            await self.action_run_selected()


class MQAgentApp(App):
    """mq-agent TUI — HAL-style AI orchestrator dashboard."""

    CSS = CSS

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("enter", "run_selected", "Run"),
        Binding("x", "run_selected", "Run"),
        Binding("c", "clear_log", "Clear"),
        Binding("r", "refresh_dashboard", "Refresh"),
    ]

    selected_command: reactive[str] = reactive("")

    def __init__(self) -> None:
        super().__init__()
        self._command_tasks: set[asyncio.Task[None]] = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label(f" mq-agent v{__version__}", id="sidebar-title")
                yield CommandListView(
                    *[ListItem(Label(label), id=f"cmd-{i}") for i, (label, _) in enumerate(COMMANDS)]
                )
            with ScrollableContainer(id="output"):
                yield Log(id="log", highlight=True)
                with Vertical(id="dashboard"):
                    with Horizontal():
                        yield Static("", id="panel-stack", classes="panel")
                        yield Static("", id="panel-brain", classes="panel")
                    with Horizontal():
                        yield Static("", id="panel-ollama", classes="panel")
                        yield Static("", id="panel-next", classes="panel")
        yield Static(self._status_text(), id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(Log)
        list_view = self.query_one(ListView)
        list_view.focus()
        list_view.index = 0
        self.selected_command = COMMANDS[0][1]
        self._update_status()
        log.write_line("[bold cyan]mq-agent[/bold cyan] ready.")
        log.write_line(f"OPENAI_API_KEY: {'set ✓' if os.environ.get('OPENAI_API_KEY') else 'NOT SET ✗'}")
        self._refresh_dashboard(log=log)
        log.write_line("Select a command from the sidebar and press [bold]Enter[/bold].")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        command = command_for_item_id(event.item.id)
        if command:
            self.selected_command = command
            self._update_status()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        command = command_for_item_id(event.item.id)
        if command:
            self.selected_command = command
            self._update_status()
            await self.action_run_selected()

    async def action_run_selected(self) -> None:
        log = self.query_one(Log)
        if not self.selected_command:
            log.write_line("[yellow]No command selected. Move with ↑/↓ and press Enter, Space or x.[/yellow]")
            return
        log.write_line(f"\n[bold cyan]▶ mq-agent {self.selected_command}[/bold cyan]")
        task = asyncio.create_task(self._run_command(self.selected_command, log))
        self._command_tasks.add(task)
        task.add_done_callback(self._command_tasks.discard)

    def action_clear_log(self) -> None:
        self.query_one(Log).clear()

    def action_refresh_dashboard(self) -> None:
        self._refresh_dashboard(log=self.query_one(Log))

    async def _run_command(self, cmd: str, log: Log) -> None:
        parts = shlex.split(f"mq-agent {cmd}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ},
            )
            assert proc.stdout is not None
            async for line in proc.stdout:
                log.write_line(line.decode(errors="replace").rstrip())
            await proc.wait()
            if proc.returncode == 0:
                log.write_line("[green]✓ exit 0[/green]")
            else:
                log.write_line(f"[yellow]exit {proc.returncode}[/yellow]")
        except FileNotFoundError:
            log.write_line("[red]mq-agent CLI not found — install with: uv pip install -e .[/red]")
        except Exception as exc:
            log.write_line(f"[red]Error: {exc}[/red]")

    def _status_text(self) -> str:
        key = "✓" if os.environ.get("OPENAI_API_KEY") else "✗ NO KEY"
        return f" OPENAI {key}  |  q=quit  enter/space/x=run  r=refresh  c=clear"

    def _update_status(self) -> None:
        try:
            bar = self.query_one("#status-bar", Static)
            bar.update(
                f" Selected: mq-agent {self.selected_command}  |  q=quit  enter/space/x=run  r=refresh  c=clear"
            )
        except Exception:
            pass

    def _refresh_dashboard(self, log: Log | None = None) -> None:
        try:
            from mq_agent.tools.operator_dashboard import operator_dashboard

            data = json.loads(operator_dashboard())
        except Exception as exc:
            if log is not None:
                log.write_line(f"[yellow]dashboard unavailable:[/yellow] {exc}")
            return

        panels = dashboard_panel_text(data)
        for panel_id, text in panels.items():
            self.query_one(f"#{panel_id}", Static).update(text)
        if log is not None:
            log.write_line(f"[dim]dashboard refreshed: {data.get('checked_at', '')}[/dim]")

    def _write_dashboard_snapshot(self, log: Log) -> None:
        """Compatibility wrapper for tests and older TUI callers."""
        self._refresh_dashboard(log=log)


def dashboard_panel_text(data: dict[str, object]) -> dict[str, str]:
    """Format operator dashboard data for compact TUI panels."""
    stack = data["stack"]
    brain = data["brain"]
    ollama = data["ollama"]

    assert isinstance(stack, dict)
    assert isinstance(brain, dict)
    assert isinstance(ollama, dict)

    contracts = data.get("contracts", {})
    contract_text = (
        ", ".join(f"{key}={value}" for key, value in sorted(contracts.items()))
        if isinstance(contracts, dict)
        else "unknown"
    )
    brain_path = str(brain.get("path") or "no stack-truth note")
    if len(brain_path) > 54:
        brain_path = "..." + brain_path[-51:]

    return {
        "panel-stack": (
            "[b]Stack[/b]\n"
            f"Gate: {stack.get('gate')} | Contract: {stack.get('contract')}\n"
            f"Repos: {stack.get('repo_count')} | Actions: {stack.get('actionable_count')} | Dirty: {stack.get('dirty_count')}\n"
            f"Contracts: {contract_text}"
        ),
        "panel-brain": (
            "[b]Brain[/b]\n"
            f"Truth: {brain.get('status', 'unknown')} | Age: {brain.get('age_days', '-')}\n"
            f"{brain_path}"
        ),
        "panel-ollama": (
            "[b]Ollama[/b]\n"
            f"Status: {'OK' if ollama.get('ok') else 'CHECK'}\n"
            f"Profile: {ollama.get('profile')} -> {ollama.get('model')}\n"
            f"Models: {len(ollama.get('models', []))}"
        ),
        "panel-next": (
            "[b]Next[/b]\n"
            f"Overall: {data.get('overall')}\n"
            f"{data.get('next_action')}"
        ),
    }
