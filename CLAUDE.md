# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the TUI

```bash
python3 agent_sync.py
```

Install the only dependency if needed:

```bash
pip install textual
```

## Project Purpose

Agent Sync is an agentic reconciliation tool that ingests Claude AI export data to build and maintain two documents:

- **CLAUDE.md** — user context (role, tech stack, projects)
- **SOUL.md** — agent persona (tone, communication style, values)

## Architecture

Everything lives in a single file: `agent_sync.py`.

**Screen flow (wizard-style, stack-based via `push_screen` / `pop_screen`):**

```
WelcomeScreen → PlatformScreen → ExportScreen → IngestScreen
                      └→ UnsupportedScreen (dead-end for non-Claude users)
```

**`ExportScreen`** is the core of Step 0 — Gather. It has two sections:
1. Claude data export: guides the user to `https://claude.ai/settings/data-privacy-controls`, accepts a path to the extracted zip folder, validates it contains the four required JSON files.
2. Claude Code insights: detects the `claude` CLI via `shutil.which`, then runs `claude -p "/insights"` asynchronously via `@work` + `asyncio.create_subprocess_exec`. The resulting report lands at `~/.claude/usage-data/report.html`.

**Key helpers** (all pure functions at module level):
- `_check_claude_code()` — `shutil.which("claude")`
- `_get_report_path()` — `Path.home() / ".claude" / "usage-data" / "report.html"`
- `_resolve_data_dir(path)` — handles both a direct `data-xxxx/` dir and a parent folder containing it
- `_validate_export(path)` — checks for the four required JSON files; supports dirs and `.zip`
- `_build_summary(path)` — parses all four JSONs and returns a Rich-markup summary string

**Claude export format** (`data-xxxx-batch-0000/`):
- `users.json` — array with `full_name`, `email_address`
- `memories.json` — array of conversation memory blocks
- `projects.json` — array of Claude projects
- `conversations.json` — array of conversation objects

## What's Not Yet Built

Steps 1+ (fact review, CLAUDE.md/SOUL.md generation) are stubbed — the "Continue →" button on `IngestScreen` shows a "Step 1 coming soon!" notification.
