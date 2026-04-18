#!/usr/bin/env python3
"""Agent Sync — Step 0: Gather Claude export data."""

from __future__ import annotations

import asyncio
import json
import shutil
import webbrowser
import zipfile
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Center, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Rule, Static

CLAUDE_EXPORT_URL = "https://claude.ai/settings/data-privacy-controls"
REQUIRED_FILES = {"users.json", "memories.json", "projects.json", "conversations.json"}


# ── Screens ───────────────────────────────────────────────────────────────────

class WelcomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Center(
            Vertical(
                Static(BANNER, id="banner"),
                Static(
                    "Build a high-fidelity digital twin of your context.",
                    classes="muted",
                ),
                Rule(),
                Static("Step 0  ·  Gather", classes="step-label"),
                Static(
                    "Import your AI export to bootstrap [bold]CLAUDE.md[/bold] "
                    "and [bold]SOUL.md[/bold].",
                ),
                Horizontal(
                    Button("Get Started →", variant="primary", id="btn-start"),
                    Button("Quit", id="btn-quit"),
                    classes="btn-row",
                ),
                id="card",
            )
        )
        yield Footer()

    @on(Button.Pressed, "#btn-start")
    def start(self) -> None:
        self.app.push_screen(PlatformScreen())

    @on(Button.Pressed, "#btn-quit")
    def quit_app(self) -> None:
        self.app.exit()


class PlatformScreen(Screen):
    """Confirm the user uses Claude."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Center(
            Vertical(
                Static("Which AI assistant do you use?", classes="heading"),
                Static(
                    "Agent Sync currently supports [bold]Claude[/bold] (Anthropic).",
                    classes="muted",
                ),
                Horizontal(
                    Button("Claude  ✓", variant="primary", id="btn-claude"),
                    Button("Other", id="btn-other"),
                    classes="btn-row",
                ),
                id="card",
            )
        )
        yield Footer()

    @on(Button.Pressed, "#btn-claude")
    def chose_claude(self) -> None:
        self.app.push_screen(ExportScreen())

    @on(Button.Pressed, "#btn-other")
    def chose_other(self) -> None:
        self.app.push_screen(UnsupportedScreen())


class UnsupportedScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Center(
            Vertical(
                Static("Not yet supported", classes="heading"),
                Static(
                    "Agent Sync currently only ingests Claude exports.\n"
                    "ChatGPT and Gemini support is on the roadmap.",
                    classes="muted",
                ),
                Button("← Back", id="btn-back"),
                id="card",
            )
        )
        yield Footer()

    @on(Button.Pressed, "#btn-back")
    def go_back(self) -> None:
        self.app.pop_screen()


class ExportScreen(Screen):
    """Guide the user through Claude data export."""

    def __init__(self) -> None:
        super().__init__()
        self._cc_path = _check_claude_code()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Center(
            Vertical(
                # ── Claude export section ─────────────────────────────────
                Static("Export your Claude data", classes="heading"),
                Static(
                    "We need your Claude export zip to read:\n"
                    "users · memories · projects · conversations",
                    classes="muted",
                ),
                Rule(),
                Static(
                    " 1.  Click [bold]Open Export Page[/bold] below\n"
                    " 2.  Under [italic]Export Data[/italic], click [bold]Export[/bold]\n"
                    " 3.  Download the email link and extract the zip\n"
                    " 4.  Paste the path to the [bold]extracted folder[/bold] below",
                    id="steps",
                ),
                Button("Open Export Page  ↗", variant="primary", id="btn-browser"),
                Rule(),
                Static("Path to extracted export folder:", classes="label"),
                Input(
                    placeholder="~/Downloads/data-xxxx-batch-0000/",
                    id="path-input",
                ),
                # ── Claude Code insights section ──────────────────────────
                Rule(),
                Static("Claude Code Insights", classes="heading"),
                *(
                    [
                        Static(
                            f"✓  claude detected at [dim]{self._cc_path}[/dim]",
                            classes="success",
                        ),
                        Horizontal(
                            Button(
                                "Generate Insights →",
                                variant="primary",
                                id="btn-insights",
                            ),
                            Button(
                                "Open Report  ↗",
                                id="btn-open-report",
                                classes="hidden",
                            ),
                            classes="btn-row",
                        ),
                        Static("", id="insights-status", classes="muted"),
                    ]
                    if self._cc_path
                    else [
                        Static(
                            "✗  Claude Code CLI not found.",
                            classes="muted",
                        ),
                        Static(
                            "Install from [link=https://claude.ai/code]claude.ai/code[/link]"
                            " to unlock Code insights.",
                            classes="muted small",
                        ),
                    ]
                ),
                # ── bottom nav ────────────────────────────────────────────
                Rule(),
                Horizontal(
                    Button("Ingest →", variant="success", id="btn-ingest"),
                    Button("← Back", id="btn-back"),
                    classes="btn-row",
                ),
                id="card",
            )
        )
        yield Footer()

    @on(Button.Pressed, "#btn-browser")
    def open_browser(self) -> None:
        webbrowser.open(CLAUDE_EXPORT_URL)
        btn = self.query_one("#btn-browser", Button)
        btn.label = "Opened ✓"
        btn.variant = "default"

    @on(Button.Pressed, "#btn-insights")
    def start_insights(self) -> None:
        self.query_one("#btn-insights", Button).disabled = True
        self.query_one("#insights-status", Static).update("Running…")
        self._run_insights()

    @work(exclusive=True)
    async def _run_insights(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "/insights",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _out, err = await proc.communicate()
        if proc.returncode != 0:
            msg = err.decode().strip() or "insights command failed"
            self.query_one("#insights-status", Static).update(f"[red]Error:[/red] {msg}")
            self.query_one("#btn-insights", Button).disabled = False
        else:
            report = _get_report_path()
            self.query_one("#insights-status", Static).update(
                f"Done ✓  [dim]{report}[/dim]"
            )
            self.query_one("#btn-open-report", Button).remove_class("hidden")

    @on(Button.Pressed, "#btn-open-report")
    def open_report(self) -> None:
        webbrowser.open(_get_report_path().as_uri())

    @on(Button.Pressed, "#btn-ingest")
    def ingest(self) -> None:
        raw = self.query_one("#path-input", Input).value.strip()
        if not raw:
            self.notify("Enter a path first.", severity="warning")
            return
        path = Path(raw).expanduser().resolve()
        err = _validate_export(path)
        if err:
            self.notify(err, severity="error")
            return
        self.app.push_screen(IngestScreen(path))

    @on(Button.Pressed, "#btn-back")
    def go_back(self) -> None:
        self.app.pop_screen()


class IngestScreen(Screen):
    """Display a summary of the ingested export."""

    def __init__(self, export_path: Path) -> None:
        super().__init__()
        self._path = export_path

    def compose(self) -> ComposeResult:
        summary, data_dir = _build_summary(self._path)
        yield Header(show_clock=False)
        yield Center(
            Vertical(
                Static("Export ingested  ✓", classes="heading success"),
                Static(f"Source: {data_dir}", classes="muted small"),
                Rule(),
                Static(summary, id="summary-box"),
                Rule(),
                Static(
                    "Next: [bold]Step 1[/bold] — Review proposed CLAUDE.md facts.",
                    classes="muted",
                ),
                Horizontal(
                    Button("Continue →", variant="primary", id="btn-continue"),
                    Button("← Back", id="btn-back"),
                    classes="btn-row",
                ),
                id="card",
            )
        )
        yield Footer()

    @on(Button.Pressed, "#btn-continue")
    def continue_flow(self) -> None:
        self.notify("Step 1 coming soon!", severity="information")

    @on(Button.Pressed, "#btn-back")
    def go_back(self) -> None:
        self.app.pop_screen()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check_claude_code() -> str | None:
    """Return the claude binary path if installed, else None."""
    return shutil.which("claude")


def _get_report_path() -> Path:
    return Path.home() / ".claude" / "usage-data" / "report.html"


def _resolve_data_dir(path: Path) -> Path:
    """Given an export root or data-xxxx subdir, return the dir with JSONs."""
    if (path / "users.json").exists():
        return path
    for sub in sorted(path.iterdir()):
        if sub.is_dir() and (sub / "users.json").exists():
            return sub
    return path


def _validate_export(path: Path) -> str | None:
    if not path.exists():
        return f"Path not found: {path}"
    if path.is_file():
        if path.suffix != ".zip":
            return "Provide a directory or a .zip file."
        with zipfile.ZipFile(path) as zf:
            present = {Path(n).name for n in zf.namelist()}
    elif path.is_dir():
        data_dir = _resolve_data_dir(path)
        present = {f.name for f in data_dir.iterdir() if f.is_file()}
    else:
        return "Path is neither a file nor a directory."
    missing = REQUIRED_FILES - present
    if missing:
        return f"Missing: {', '.join(sorted(missing))}"
    return None


def _build_summary(path: Path) -> tuple[str, Path]:
    data_dir = _resolve_data_dir(path)
    lines: list[str] = []

    def _load(name: str):
        return json.loads((data_dir / name).read_text())

    try:
        users = _load("users.json")
        u = users[0] if users else {}
        lines.append(f"[bold]User[/bold]          {u.get('full_name', '?')}  ·  {u.get('email_address', '?')}")
    except Exception:
        lines.append("[bold]User[/bold]          (parse error)")

    try:
        memories = _load("memories.json")
        lines.append(f"[bold]Memories[/bold]      {len(memories)} block(s)")
    except Exception:
        lines.append("[bold]Memories[/bold]      (parse error)")

    try:
        projects = _load("projects.json")
        lines.append(f"[bold]Projects[/bold]      {len(projects)}")
    except Exception:
        lines.append("[bold]Projects[/bold]      (parse error)")

    try:
        convos = _load("conversations.json")
        lines.append(f"[bold]Conversations[/bold] {len(convos)}")
    except Exception:
        lines.append("[bold]Conversations[/bold] (parse error)")

    return "\n".join(lines), data_dir


# ── Banner ─────────────────────────────────────────────────────────────────────

BANNER = """\
 █████╗  ██████╗ ███████╗███╗  ██╗████████╗    ███████╗██╗   ██╗███╗  ██╗ ██████╗
██╔══██╗██╔════╝ ██╔════╝████╗ ██║╚══██╔══╝    ██╔════╝╚██╗ ██╔╝████╗ ██║██╔════╝
███████║██║  ██╗ █████╗  ██╔██╗██║   ██║       ███████╗ ╚████╔╝ ██╔██╗██║██║
██╔══██║██║  ╚██╗██╔══╝  ██║╚████║   ██║       ╚════██║  ╚██╔╝  ██║╚████║██║
██║  ██║╚██████╔╝███████╗██║ ╚███║   ██║       ███████║   ██║   ██║ ╚███║╚██████╗
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚══╝  ╚═╝       ╚══════╝   ╚═╝   ╚═╝  ╚══╝ ╚═════╝"""


# ── CSS ────────────────────────────────────────────────────────────────────────

CSS = """
Screen { align: center middle; }

#card {
    width: 80;
    max-height: 90vh;
    padding: 2 3;
    border: round $primary;
    background: $surface;
    overflow-y: auto;
}

.hidden { display: none; }

#banner {
    color: $accent;
    text-style: bold;
    margin-bottom: 1;
}

.heading {
    text-style: bold;
    margin-bottom: 1;
}

.success { color: $success; }

.muted { color: $text-muted; }

.small { margin-bottom: 1; }

.step-label {
    text-style: bold;
    color: $warning;
    margin-bottom: 1;
}

.label { margin-top: 1; }

#steps {
    margin: 1 0;
    padding: 1 2;
    border: solid $primary-darken-2;
    background: $surface-darken-1;
}

#summary-box {
    padding: 1 2;
    border: solid $success-darken-2;
    background: $surface-darken-1;
    margin: 1 0;
}

.btn-row {
    margin-top: 1;
    height: auto;
}

Button { margin-right: 1; }

Input { margin-top: 1; }

Rule { margin: 1 0; }
"""


# ── App ────────────────────────────────────────────────────────────────────────

class AgentSyncApp(App):
    TITLE = "Agent Sync"
    CSS = CSS

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())


def main() -> None:
    AgentSyncApp().run()


if __name__ == "__main__":
    main()
