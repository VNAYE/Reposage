"""Embedded PostgreSQL for deployments that have no database service (HF Spaces).

Uses ``pgserver``, a pip-installable PostgreSQL 16 build that bundles the
``pgvector`` extension, so the whole stack stays a single Python process tree
and works without root.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class EmbeddedPostgres:
    """Start a local Postgres server and expose its DSN."""

    _server: Any = None

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else self._default_data_dir()

    @staticmethod
    def _default_data_dir() -> Path:
        configured = os.getenv("PGDATA")
        if configured:
            return Path(configured)
        data_root = Path("/data")
        if data_root.is_dir() and os.access(data_root, os.W_OK):
            return data_root / "pgdata"
        return Path.home() / ".reposage" / "pgdata"

    def start(self) -> str:
        import pgserver

        self._data_dir.parent.mkdir(parents=True, exist_ok=True)
        log.info("starting embedded postgres at %s", self._data_dir)
        EmbeddedPostgres._server = pgserver.get_server(self._data_dir, cleanup_mode="stop")
        EmbeddedPostgres._server.ensure_postgres_running()
        return EmbeddedPostgres._server.get_uri()

    @classmethod
    def stop(cls) -> None:
        if cls._server is not None:
            cls._server.cleanup()
            cls._server = None
