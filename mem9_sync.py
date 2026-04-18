"""Sync Claude export memories to mem9 cloud storage.

Reads memories.json from a Claude data export, transforms each entry,
and uploads to the mem9 hosted API.

Usage:
    python3 mem9_sync.py /path/to/data-xxxx-batch-0000/

Or programmatically:
    from mem9_sync import sync_memories
    results = sync_memories(Path("./onboarding/knowledge/data-xxxx-batch-0000"))
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mem9_client import Mem9Client, Mem9Error


@dataclass
class SyncResult:
    """Summary of a sync run."""

    total: int = 0
    uploaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> str:
        if self.total == 0:
            return "N/A"
        return f"{self.uploaded / self.total:.0%}"


def _load_memories(data_dir: Path) -> list[dict]:
    """Load memories.json from a Claude export directory."""
    memories_path = data_dir / "memories.json"
    if not memories_path.exists():
        # Try to find it in a subdirectory (parent export folder)
        for sub in sorted(data_dir.iterdir()):
            if sub.is_dir() and (sub / "memories.json").exists():
                memories_path = sub / "memories.json"
                break
    if not memories_path.exists():
        raise FileNotFoundError(f"memories.json not found in {data_dir}")
    return json.loads(memories_path.read_text())


def _expand_claude_export(raw: dict) -> list[dict]:
    """Expand a Claude export entry into multiple mem9 memory items.

    Claude exports have a specific structure:
      - conversations_memory: str — the global aggregated memory
      - project_memories: dict[uuid, str] — per-project memories
      - account_uuid: str — user account id

    We split these into individual mem9 entries for better search
    and management granularity.
    """
    items: list[dict] = []
    account_uuid = raw.get("account_uuid", "unknown")

    # 1. Global conversations memory
    global_mem = raw.get("conversations_memory", "")
    if global_mem and global_mem.strip():
        items.append({
            "content": global_mem.strip(),
            "tags": ["claude-export", "global-memory"],
            "metadata": {
                "import_source": "agent-sync-claude-export",
                "claude_account_uuid": account_uuid,
                "memory_scope": "global",
            },
        })

    # 2. Each project memory gets its own entry
    project_mems = raw.get("project_memories", {})
    if isinstance(project_mems, dict):
        for project_uuid, project_mem in project_mems.items():
            if not project_mem or not str(project_mem).strip():
                continue
            items.append({
                "content": str(project_mem).strip(),
                "tags": ["claude-export", "project-memory", f"project:{project_uuid}"],
                "metadata": {
                    "import_source": "agent-sync-claude-export",
                    "claude_account_uuid": account_uuid,
                    "claude_project_uuid": project_uuid,
                    "memory_scope": "project",
                },
            })

    # 3. Fallback: if neither field was present, try generic extraction
    if not items:
        content = (
            raw.get("content")
            or raw.get("memory")
            or raw.get("text")
            or raw.get("value")
            or json.dumps(raw)
        )
        if isinstance(content, dict):
            content = json.dumps(content)
        items.append({
            "content": str(content).strip(),
            "tags": ["claude-export"],
            "metadata": {
                "import_source": "agent-sync-claude-export",
            },
        })

    return items


def sync_memories(
    data_dir: Path,
    *,
    client: Mem9Client | None = None,
    dry_run: bool = False,
    on_progress: callable | None = None,
) -> SyncResult:
    """Upload Claude export memories to mem9.

    Args:
        data_dir: path to the extracted Claude export directory.
        client: optional pre-configured Mem9Client.
        dry_run: if True, only transform and report — don't upload.
        on_progress: callback(current, total, status_msg) for UI updates.

    Returns:
        SyncResult with counts and any errors.
    """
    raw_memories = _load_memories(data_dir)

    # Expand Claude export entries into individual mem9 items
    all_items: list[dict] = []
    for raw in raw_memories:
        all_items.extend(_expand_claude_export(raw))

    result = SyncResult(total=len(all_items))

    if not client and not dry_run:
        client = Mem9Client()

    for i, item in enumerate(all_items):
        try:
            # Skip empty content
            if not item["content"] or item["content"] == "{}":
                result.skipped += 1
                if on_progress:
                    on_progress(i + 1, result.total, f"Skipped empty memory #{i + 1}")
                continue

            if dry_run:
                result.uploaded += 1
                if on_progress:
                    on_progress(i + 1, result.total, f"[dry-run] #{i + 1}: {item['content'][:60]}…")
                continue

            client.store_memory(
                item["content"],
                tags=item["tags"],
                metadata=item["metadata"],
            )
            result.uploaded += 1

            if on_progress:
                on_progress(i + 1, result.total, f"Uploaded #{i + 1}: {item['content'][:60]}…")

        except Mem9Error as e:
            result.failed += 1
            result.errors.append(f"Memory #{i + 1}: {e}")
            if on_progress:
                on_progress(i + 1, result.total, f"Failed #{i + 1}: {e}")
        except Exception as e:
            result.failed += 1
            result.errors.append(f"Memory #{i + 1}: {e}")
            if on_progress:
                on_progress(i + 1, result.total, f"Error #{i + 1}: {e}")

    return result


# ── CLI entry point ───────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 mem9_sync.py <export-dir> [--dry-run]")
        sys.exit(1)

    data_dir = Path(sys.argv[1]).expanduser().resolve()
    dry_run = "--dry-run" in sys.argv

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist")
        sys.exit(1)

    def _print_progress(current: int, total: int, msg: str) -> None:
        print(f"  [{current}/{total}] {msg}")

    print(f"{'[DRY RUN] ' if dry_run else ''}Syncing memories from {data_dir} to mem9…")
    result = sync_memories(data_dir, dry_run=dry_run, on_progress=_print_progress)

    print(f"\nDone! {result.uploaded} uploaded, {result.skipped} skipped, "
          f"{result.failed} failed out of {result.total} total ({result.success_rate})")

    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  ⚠ {err}")


if __name__ == "__main__":
    main()
