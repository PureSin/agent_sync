#!/usr/bin/env python3
"""
extract_facts.py — Step 1: Extract reviewable facts from Claude export + Code insights.

Usage:
    python3 extract_facts.py --export-dir <path> --report <path-to-report.html>
    python3 extract_facts.py --export-dir <path>          # report is optional
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import os

from dotenv import load_dotenv
from openai import OpenAI

from mem9_client import Mem9Client, Mem9Error

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# ── HTML text extractor ───────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False
        self._skip_depth = 0
        self._depth = 0
        self._SKIP_TAGS = {"script", "style"}

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP_TAGS and not self._skip:
            self._skip = True
            self._skip_depth = self._depth
        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        self._depth -= 1
        if self._skip and self._depth == self._skip_depth:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _extract_html_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = parser.get_text()
    return re.sub(r"\s+", " ", text).strip()


# ── Data loaders ──────────────────────────────────────────────────────────────

def _resolve_data_dir(path: Path) -> Path:
    if (path / "users.json").exists():
        return path
    for sub in sorted(path.iterdir()):
        if sub.is_dir() and (sub / "users.json").exists():
            return sub
    return path


def load_export(export_dir: Path) -> dict:
    data_dir = _resolve_data_dir(export_dir)

    def _load(name: str):
        return json.loads((data_dir / name).read_text())

    users = _load("users.json")
    memories = _load("memories.json")
    projects = _load("projects.json")
    conversations = _load("conversations.json")

    user = users[0] if users else {}
    memory_text = "\n\n".join(
        m.get("conversations_memory", "") for m in memories if m.get("conversations_memory")
    )
    project_list = [
        f"- {p['name']}: {p.get('description', '').strip()[:120]}"
        for p in projects
        if not p.get("is_starter_project")
    ]
    convo_titles = [c["name"] for c in conversations if c.get("name")]
    convo_summaries = [
        f"[{c['name']}] {c.get('summary', '').strip()[:300]}"
        for c in conversations
        if c.get("summary") and c.get("name")
    ][:30]  # cap at 30 most-recent

    return {
        "user": user,
        "memory": memory_text,
        "projects": project_list,
        "convo_titles": convo_titles,
        "convo_summaries": convo_summaries,
    }


def load_report(report_path: Path) -> str:
    html = report_path.read_text()
    return _extract_html_text(html)


# ── Prompt builder ────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a precise fact-extractor building two configuration files for a developer:

• CLAUDE.md  — persistent instructions Claude Code reads at session start.
  Best for: role, tech stack, current projects, tooling preferences, workflow rules,
  coding style, communication expectations. Keep entries concrete and actionable.
  Target: ≤ 200 lines total, so be selective.

• SOUL.md — the user's persona as an AI collaborator.
  Best for: communication style, values, decision-making patterns, what they find
  annoying, how they like to be challenged, energy and tone, recurring mindset.

Extract facts strictly from the provided sources. Do NOT invent anything.
Output ONLY valid JSON matching this schema — no markdown fences, no prose:

{
  "claude_md": [
    {
      "category": "<one of: identity | technical | projects | workflow | preferences>",
      "fact": "<concise, actionable statement — max 120 chars>",
      "source": "<one of: memory | projects | conversations | report>",
      "confidence": "<high | medium | low>"
    }
  ],
  "soul_md": [
    {
      "category": "<one of: communication | values | collaboration | style | mindset>",
      "fact": "<concise statement about persona/behaviour — max 120 chars>",
      "source": "<one of: memory | projects | conversations | report>",
      "confidence": "<high | medium | low>"
    }
  ]
}

Rules:
- Deduplicate: if two sources say the same thing, emit one fact (highest confidence).
- Omit trivially obvious things ("user uses Claude").
- For SOUL.md, prefer behavioural observations over self-reported traits.
- claude_md facts should read like instructions to an AI assistant.
- soul_md facts should read like observations about a person.
"""


def _build_user_prompt(data: dict, report_text: str | None) -> str:
    parts: list[str] = []

    u = data["user"]
    parts.append(
        f"=== USER ===\nName: {u.get('full_name', '?')}\nEmail: {u.get('email_address', '?')}"
    )

    parts.append(f"=== CLAUDE AI MEMORY ===\n{data['memory']}")

    if data["projects"]:
        parts.append("=== CLAUDE PROJECTS ===\n" + "\n".join(data["projects"]))

    if data["convo_titles"]:
        parts.append(
            "=== CONVERSATION TOPICS (titles only) ===\n"
            + "\n".join(f"- {t}" for t in data["convo_titles"])
        )

    if data["convo_summaries"]:
        parts.append(
            "=== CONVERSATION SUMMARIES (sample) ===\n"
            + "\n\n".join(data["convo_summaries"])
        )

    if report_text:
        # Truncate to avoid overwhelming the prompt; the glance + patterns are most useful
        parts.append(f"=== CLAUDE CODE INSIGHTS REPORT ===\n{report_text[:8000]}")

    return "\n\n".join(parts)


# ── Claude API call ───────────────────────────────────────────────────────────

def extract_facts(export_data: dict, report_text: str | None) -> dict:
    api_key = os.environ.get("Z_AI_API_KEY")
    base_url = os.environ.get("Z_AI_BASE_URL", "https://api.z.ai/api/paas/v4/")
    model = os.environ.get("Z_AI_MODEL", "glm-5.1")

    if not api_key:
        raise RuntimeError("Z_AI_API_KEY not set — add it to your .env file.")

    client = OpenAI(api_key=api_key, base_url=base_url)
    user_content = _build_user_prompt(export_data, report_text)

    print(f"Calling z.ai ({model}) to extract facts…", flush=True)
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_content},
        ],
    )

    raw = response.choices[0].message.content.strip()
    # Strip accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ── Markdown renderer ─────────────────────────────────────────────────────────

_CONFIDENCE_BADGE = {"high": "🟢", "medium": "🟡", "low": "🔴"}

def render_review_markdown(facts: dict, export_dir: Path, report_path: Path | None) -> str:
    lines: list[str] = [
        "# Agent Sync — Fact Review",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"Export: `{export_dir}`  ",
        f"Report: `{report_path or 'not provided'}`",
        "",
        "Review each fact below. Delete lines you disagree with, edit text as needed.",
        "When done, run `step2_generate.py` (coming soon) to build CLAUDE.md + SOUL.md.",
        "",
        "**Legend:** 🟢 high confidence · 🟡 medium · 🔴 low",
        "",
    ]

    # ── CLAUDE.md section ──
    lines += ["---", "", "## CLAUDE.md Facts", ""]
    by_cat: dict[str, list] = {}
    for f in facts.get("claude_md", []):
        by_cat.setdefault(f["category"], []).append(f)

    for cat in ["identity", "technical", "projects", "workflow", "preferences"]:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"### {cat.capitalize()}")
        lines.append("")
        for item in sorted(items, key=lambda x: x["confidence"]):
            badge = _CONFIDENCE_BADGE.get(item["confidence"], "")
            src = f"_{item['source']}_"
            lines.append(f"- {badge} {item['fact']}  {src}")
        lines.append("")

    # ── SOUL.md section ──
    lines += ["---", "", "## SOUL.md Facts", ""]
    by_cat = {}
    for f in facts.get("soul_md", []):
        by_cat.setdefault(f["category"], []).append(f)

    for cat in ["communication", "values", "collaboration", "style", "mindset"]:
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines.append(f"### {cat.capitalize()}")
        lines.append("")
        for item in sorted(items, key=lambda x: x["confidence"]):
            badge = _CONFIDENCE_BADGE.get(item["confidence"], "")
            src = f"_{item['source']}_"
            lines.append(f"- {badge} {item['fact']}  {src}")
        lines.append("")

    return "\n".join(lines)


# ── mem9 upload ───────────────────────────────────────────────────────────────

def upload_to_mem9(facts: dict) -> None:
    client = Mem9Client()
    all_facts = [
        (f, "claude-md") for f in facts.get("claude_md", [])
    ] + [
        (f, "soul-md") for f in facts.get("soul_md", [])
    ]
    print(f"Uploading {len(all_facts)} facts to mem9…")
    ok = fail = 0
    for fact, doc_type in all_facts:
        tags = [doc_type, fact["category"], f"source:{fact['source']}", f"confidence:{fact['confidence']}"]
        try:
            client.store_memory(
                fact["fact"],
                tags=tags,
                metadata={"doc_type": doc_type, "category": fact["category"], "source": fact["source"]},
            )
            print(f"  ✓ [{doc_type}/{fact['category']}] {fact['fact'][:70]}")
            ok += 1
        except Mem9Error as e:
            print(f"  ✗ [{doc_type}/{fact['category']}] {e}", file=sys.stderr)
            fail += 1
    print(f"mem9: {ok} uploaded, {fail} failed.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract facts from Claude export for review.")
    parser.add_argument("--export-dir", required=True, help="Path to extracted Claude export folder")
    parser.add_argument("--report", default=None, help="Path to Claude Code insights report.html")
    parser.add_argument("--out", default="facts_review.md", help="Output markdown file (default: facts_review.md)")
    parser.add_argument("--json-out", default=None, help="Also save raw JSON to this path")
    parser.add_argument("--upload", action="store_true", help="Upload facts to mem9 after extraction")
    args = parser.parse_args()

    export_dir = Path(args.export_dir).expanduser().resolve()
    if not export_dir.exists():
        print(f"Error: export dir not found: {export_dir}", file=sys.stderr)
        sys.exit(1)

    report_path: Path | None = None
    report_text: str | None = None
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        if not report_path.exists():
            print(f"Warning: report not found at {report_path}, skipping.", file=sys.stderr)
            report_path = None
        else:
            report_text = load_report(report_path)

    print(f"Loading export from {export_dir} …")
    export_data = load_export(export_dir)
    print(
        f"  {len(export_data['convo_titles'])} conversations · "
        f"{len(export_data['projects'])} projects · "
        f"memory: {'yes' if export_data['memory'] else 'no'}"
    )

    facts = extract_facts(export_data, report_text)
    n_claude = len(facts.get("claude_md", []))
    n_soul = len(facts.get("soul_md", []))
    print(f"Extracted {n_claude} CLAUDE.md facts + {n_soul} SOUL.md facts.")

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.write_text(json.dumps(facts, indent=2))
        print(f"JSON saved → {json_path}")

    md = render_review_markdown(facts, export_dir, report_path)
    out_path = Path(args.out)
    out_path.write_text(md)
    print(f"Review file saved → {out_path}")

    if args.upload:
        upload_to_mem9(facts)


if __name__ == "__main__":
    main()
