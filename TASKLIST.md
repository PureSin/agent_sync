# Agent Sync — Task List

## ✅ Step 0: Gather
Ingest Claude export data and Claude Code insights.

- [x] TUI wizard: confirm Claude usage, guide through data export at `claude.ai/settings/data-privacy-controls`
- [x] Accept extracted folder path, validate four required JSONs (`users`, `memories`, `projects`, `conversations`)
- [x] Detect Claude Code CLI (`shutil.which`), run `claude -p "/insights"`, open `~/.claude/usage-data/report.html`

---

## 🔲 Step 1: Extract
Run an LLM-backed parser over all ingested sources to produce discrete, atomic facts.

**Inputs:**
- `users.json`, `memories.json`, `projects.json`, `conversations.json` from Claude export
- `~/.claude/usage-data/report.html` from Claude Code insights

**Output:** Structured list of facts, each with:
- Fact text (editable)
- Suggested category (`memories.json` / `CLAUDE.md` / `SOUL.md`)
- Source reference (which file / conversation it came from)

---

## 🔲 Step 1: Review
Present extracted facts to the user for sorting into three destinations.

**Categories:**
| Destination | What goes here |
|---|---|
| `memories.json` | Personal user facts — who the user is, their context, background |
| `CLAUDE.md` | Technical instructions for AI agents — project rules, coding standards, workflows |
| `SOUL.md` | Agent personality — tone, core values, communication style, behavioral boundaries |

**Required interactions per fact:**
- Assign to a category
- Edit the fact text
- Skip / discard
- Flag for later

Progress should be persisted so the review can be resumed across sessions.

> **Open question:** TUI (existing textual app) or web UI? A web UI would allow richer interactions (drag-and-drop sorting, side-by-side diff view, bulk edits). TUI is simpler to ship and keeps the tool self-contained.

---

## 🔲 Step 1: Write
Generate the three output files from reviewed and categorized facts.

- Write `memories.json`, `CLAUDE.md`, `SOUL.md`
- Handle global vs. project-level hierarchy:
  - `~/.claude/CLAUDE.md` (global) vs. `<project>/.claude/CLAUDE.md` (local)
  - Same for `SOUL.md`
- Show a diff if files already exist — user confirms before overwrite
