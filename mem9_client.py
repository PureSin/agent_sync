"""mem9 REST API client for the hosted mem9.ai service.

Wraps the v1alpha2 API for memory CRUD, search, imports, and health checks.
Auth: X-API-Key header.  Agent identity: X-Mnemo-Agent-Id header.

Usage:
    from mem9_client import Mem9Client

    client = Mem9Client()                    # reads MEM9_API_KEY from env
    client.store_memory("User prefers dark mode", tags=["preference"])
    results = client.search_memories("dark mode")
"""

from __future__ import annotations

import os
from typing import Any

import requests


class Mem9Error(Exception):
    """Raised when the mem9 API returns an unexpected status."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"mem9 API error {status_code}: {detail}")


class Mem9Client:
    """Thin wrapper around the hosted mem9 v1alpha2 REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        api_url: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("MEM9_API_KEY", "")
        self.api_url = (api_url or os.getenv("MEM9_API_URL", "https://api.mem9.ai")).rstrip("/")
        self.agent_id = agent_id or os.getenv("MEM9_AGENT_ID", "agent-sync")

        if not self.api_key:
            raise Mem9Error(0, "MEM9_API_KEY is required. Set it in .env or pass api_key=")

        self._base = f"{self.api_url}/v1alpha2/mem9s"
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-API-Key": self.api_key,
                "X-Mnemo-Agent-Id": self.agent_id,
                "Content-Type": "application/json",
            }
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text
            raise Mem9Error(resp.status_code, str(detail))

    # ── health ─────────────────────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """GET /healthz — liveness probe."""
        resp = self._session.get(f"{self.api_url}/healthz")
        self._raise_for_status(resp)
        return resp.json()

    # ── memories CRUD ──────────────────────────────────────────────────────

    def store_memory(
        self,
        content: str,
        *,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /memories — create a memory."""
        body: dict[str, Any] = {"content": content}
        if tags:
            body["tags"] = tags
        if metadata:
            body["metadata"] = metadata
        resp = self._session.post(self._url("/memories"), json=body)
        self._raise_for_status(resp)
        return resp.json()

    def search_memories(
        self,
        query: str,
        *,
        limit: int = 10,
        tags: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """GET /memories?q=… — hybrid keyword + semantic search."""
        params: dict[str, Any] = {"q": query, "limit": limit}
        if tags:
            params["tags"] = tags
        if source:
            params["source"] = source
        resp = self._session.get(self._url("/memories"), params=params)
        self._raise_for_status(resp)
        return resp.json()

    def list_memories(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        tags: str | None = None,
        memory_type: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        """GET /memories — list / filter memories (no search query)."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if tags:
            params["tags"] = tags
        if memory_type:
            params["memory_type"] = memory_type
        if state:
            params["state"] = state
        resp = self._session.get(self._url("/memories"), params=params)
        self._raise_for_status(resp)
        return resp.json()

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        """GET /memories/{id} — read one memory."""
        resp = self._session.get(self._url(f"/memories/{memory_id}"))
        self._raise_for_status(resp)
        return resp.json()

    def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        version: int | None = None,
    ) -> dict[str, Any]:
        """PUT /memories/{id} — update a memory."""
        body: dict[str, Any] = {}
        if content is not None:
            body["content"] = content
        if tags is not None:
            body["tags"] = tags
        if metadata is not None:
            body["metadata"] = metadata
        headers = {}
        if version is not None:
            headers["If-Match"] = str(version)
        resp = self._session.put(
            self._url(f"/memories/{memory_id}"), json=body, headers=headers
        )
        self._raise_for_status(resp)
        return resp.json()

    def delete_memory(self, memory_id: str) -> None:
        """DELETE /memories/{id} — delete one memory."""
        resp = self._session.delete(self._url(f"/memories/{memory_id}"))
        self._raise_for_status(resp)

    # ── imports ────────────────────────────────────────────────────────────

    def import_file(
        self,
        filepath: str,
        file_type: str = "memory",
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """POST /imports — upload a file for async import.

        Args:
            filepath: path to the file to upload.
            file_type: 'memory' or 'session'.
            agent_id: override the default agent id for this import.
            session_id: required when file_type is 'session'.
        """
        data: dict[str, str] = {"file_type": file_type}
        if agent_id:
            data["agent_id"] = agent_id
        if session_id:
            data["session_id"] = session_id
        with open(filepath, "rb") as f:
            # multipart/form-data — remove the default JSON content type
            resp = self._session.post(
                self._url("/imports"),
                data=data,
                files={"file": (os.path.basename(filepath), f)},
                headers={"Content-Type": None},  # let requests set multipart boundary
            )
        self._raise_for_status(resp)
        return resp.json()

    def list_imports(self) -> dict[str, Any]:
        """GET /imports — list all import tasks."""
        resp = self._session.get(self._url("/imports"))
        self._raise_for_status(resp)
        return resp.json()

    def get_import(self, task_id: str) -> dict[str, Any]:
        """GET /imports/{id} — poll one import task."""
        resp = self._session.get(self._url(f"/imports/{task_id}"))
        self._raise_for_status(resp)
        return resp.json()
