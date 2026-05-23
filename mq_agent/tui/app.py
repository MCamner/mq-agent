"""Textual TUI for mq-agent — HAL-style dashboard."""
from __future__ import annotations

import os
from typing import ClassVar

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

COMMANDS = [
    ("audit .", "audit"),
    ("release-plan", "release-plan"),
    ("release-check", "release-check"),
    ("repo-summary .", "repo-summary"),
    ("fix-ci", "fix-ci"),
    ("doctor", "doctor"),
    ("tools", "tools"),
]

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


class MQAgentApp(App):
    """mq-agent TUI — HAL-style AI orchestrator dashboard."""

    CSS = CSS

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("enter", "run_selected", "Run"),
        Binding("c", "clear_log", "Clear"),
    ]

    selected_command: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label(" mq-agent v0.1.0", id="sidebar-title")
                yield ListView(
                    *[ListItem(Label(label), id=f"cmd-{cmd}") for label, cmd in COMMANDS]
                )
            with ScrollableContainer(id="output"):
                yield Log(id="log", highlight=True)
        yield Static(self._status_text(), id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(Log)
        log.write_line("[bold cyan]mq-agent[/bold cyan] ready.")
        log.write_line(f"OPENAI_API_KEY: {'set ✓' if os.environ.get('OPENAI_API_KEY') else 'NOT SET ✗'}")
        log.write_line("Select a command from the sidebar and press [bold]Enter[/bold].")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("cmd-"):
            self.selected_command = item_id[4:]
            self._update_status()

    def action_run_selected(self) -> None:
        if not self.selected_command:
            return
        log = self.query_one(Log)
        log.write_line(f"\n[bold cyan]▶ mq-agent {self.selected_command}[/bold cyan]")
        self._run_command(self.selected_command, log)

    def action_clear_log(self) -> None:
        self.query_one(Log).clear()

    def _run_command(self, cmd: str, log: Log) -> None:
        import shlex
        import subprocess

        try:
            parts = shlex.split(f"mq-agent {cmd}")
            result = subprocess.run(
                parts,
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ},
            )
            output = result.stdout or result.stderr or "(no output)"
            for line in output.splitlines():
                log.write_line(line)
        except subprocess.TimeoutExpired:
            log.write_line("[red]Command timed out[/red]")
        except FileNotFoundError:
            log.write_line("[red]mq-agent CLI not found — install with: uv pip install -e .[/red]")
        except Exception as exc:
            log.write_line(f"[red]Error: {exc}[/red]")

    def _status_text(self) -> str:
        key = "✓" if os.environ.get("OPENAI_API_KEY") else "✗ NO KEY"
        return f" OPENAI {key}  |  q=quit  enter=run  c=clear"

    def _update_status(self) -> None:
        try:
            bar = self.query_one("#status-bar", Static)
            bar.update(f" Selected: mq-agent {self.selected_command}  |  q=quit  enter=run  c=clear")
        except Exception:
            pass
