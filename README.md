# Agent Sync

An agentic reconciliation tool that harvests AI interaction data to build, verify, and maintain a high-fidelity digital twin of the user's landscape (**CLAUDE.md**) and the agent's behavioral essence (**SOUL.md**).

## Quick Start

```bash
pip install textual requests openai python-dotenv
python3 agent_sync.py
```

## The Two Pillars of Sync

The system manages two distinct documents at Global (User) or Local (Project) level:

| Document | Focus | Global Level Content | Project Level Content |
|----------|-------|---------------------|----------------------|
| **CLAUDE.md** | The User | [User context, general tech stack] | Specific repo goals, local dependencies, project-specific task history |
| **SOUL.md** | The Persona | General communication style, core values (wit, brevity), broad engagement rules | Domain-specific "vibe" (e.g., more academic for OMSCS, more pragmatic for home DIY) |

## The Sync Lifecycle

### Step 0: Gather (The Ingestion)

The tool acts as a "data harvester" for your Claude export files.

- **Input**: `users.json`, `memories.json`, `projects.json`, and `conversations.json`
- **Analysis**: An LLM-backed parser scans for Identity Markers (facts for CLAUDE.md) and Behavioral Markers (patterns for SOUL.md)
- **Conflict Detection**: Identifying when a new conversation contradicts a stored memory

### Step 1: Extract & Review

The "Founding" phase where the user establishes the baseline.

- **Fact Extraction**: `extract_facts.py` processes ingested sources via a pluggable backend (z.ai or Claude Code CLI) and produces a categorized list of discrete facts for `CLAUDE.md` and `SOUL.md`
- **Fact Review**: Edit `facts_review.md` — delete, reword, or keep each fact before generating output files
- **mem9 Upload**: Push approved facts to cloud memory with `--upload` (after extraction) or `--from-review` (from a pre-edited review file)
- **Persona Calibration**: Generates a draft SOUL.md based on past interaction patterns *(write step — coming soon)*

### Step 2: Regular Review (The Pulse)

A recurring maintenance loop to keep the files current.

- **Delta Detection**: Highlights only what has changed since last export
- **Context Decay**: Flags stale facts for archival
- **Learning Extraction**: Updates SOUL.md based on correction patterns

## Fact Extraction (Step 1)

`extract_facts.py` processes the Claude export and Code insights report through GLM-4.7 on z.ai to produce reviewable, structured facts.

### Setup

Add z.ai credentials to `.env`:

```env
Z_AI_API_KEY=your-key-here
Z_AI_BASE_URL=https://api.z.ai/api/coding/paas/v4/
Z_AI_MODEL=GLM-4.7
```

> **Note:** Use the `/coding/paas/v4/` endpoint if you have the GLM Coding Plan subscription.

### Usage

```bash
# Extract facts and write review file
python3 extract_facts.py \
  --export-dir /path/to/data-xxxx-batch-0000 \
  --report ~/.claude/usage-data/report.html \
  --out onboarding/facts_review.md \
  --json-out onboarding/facts.json

# Extract and immediately upload to mem9
python3 extract_facts.py \
  --export-dir /path/to/data-xxxx-batch-0000 \
  --report ~/.claude/usage-data/report.html \
  --out onboarding/facts_review.md \
  --json-out onboarding/facts.json \
  --upload
```

Each fact is tagged in mem9 with `claude-md` or `soul-md`, its category, source file, and confidence level.

---

## mem9 Cloud Memory

Agent Sync integrates with [mem9](https://mem9.ai) for persistent cloud memory that survives across sessions, machines, and tools.

### Setup

1. **Configure your API key** — copy `.env.example` to `.env` and add your key:

   ```bash
   cp .env.example .env
   ```

   ```env
   MEM9_API_KEY=your-api-key-here
   MEM9_API_URL=https://api.mem9.ai
   MEM9_AGENT_ID=agent-sync
   ```

   If you need a new key, provision one:

   ```bash
   curl -sX POST https://api.mem9.ai/v1alpha1/mem9s
   # → {"id":"<your-new-api-key>"}
   ```

2. **Install dependencies**:

   ```bash
   pip install requests
   ```

### Syncing Memories to mem9

#### Via the TUI

Run `python3 agent_sync.py`, navigate through the wizard to the Ingest screen, and click **"Sync to mem9 ☁"**. Progress updates display inline.

#### Via CLI

```bash
# Dry run — see what would be uploaded
python3 mem9_sync.py /path/to/data-xxxx-batch-0000 --dry-run

# Upload for real
python3 mem9_sync.py /path/to/data-xxxx-batch-0000
```

The sync expands each Claude export entry into individual memories:
- 1 **global memory** (your `conversations_memory`)
- N **project memories** (one per project from `project_memories`)

Each memory is tagged (`claude-export`, `global-memory` or `project-memory`, `project:<uuid>`) with metadata for traceability.

### Using the Python Client Directly

```python
from mem9_client import Mem9Client

client = Mem9Client()  # reads MEM9_API_KEY from .env

# Store a memory
client.store_memory("User prefers dark mode", tags=["preference"])

# Search (hybrid keyword + semantic)
results = client.search_memories("dark mode", limit=5)

# List all memories
all_mems = client.list_memories(limit=20)

# Update
client.update_memory(memory_id, content="Updated content")

# Delete
client.delete_memory(memory_id)
```

### mem9 Dashboard

View, manage, analyze, and export your memories at [mem9.ai/your-memory](https://mem9.ai/your-memory/). Sign in with the same API key.

### API Key Safety

Your `MEM9_API_KEY` is the only way to reconnect to your memory space. Store it in a password manager. The `.env` file is gitignored by default.

## Architecture

| File | Purpose |
|------|---------|
| `agent_sync.py` | Textual TUI — wizard-style screen flow for ingestion |
| `extract_facts.py` | LLM-backed fact extractor (z.ai / GLM-4.7) → `facts_review.md` + mem9 |
| `mem9_client.py` | REST client for the mem9 v1alpha2 API |
| `mem9_sync.py` | Transforms Claude exports into mem9 memories |

**Screen flow:**

```
WelcomeScreen → PlatformScreen → ExportScreen → IngestScreen (+ mem9 sync)
                     └→ UnsupportedScreen
```

## What's Not Yet Built

- Step 1 Review: interactive TUI/web UI for per-fact accept/edit/skip/flag with session persistence
- Step 1 Write: generate `CLAUDE.md` and `SOUL.md` from reviewed facts (global vs. project-level, diff before overwrite)
- Step 2: delta detection, context decay flagging, and learning extraction for regular sync
- Full memory browser/review screen in the TUI
- Automatic conflict detection between local and cloud memories