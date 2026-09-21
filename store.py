from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS reel_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  video_url TEXT NOT NULL,
  caption TEXT NOT NULL,
  is_ai_generated INTEGER NOT NULL DEFAULT 0,
  container_id TEXT,
  container_status TEXT,
  approved_at TEXT,
  media_id TEXT,
  permalink TEXT,
  api_response_json TEXT
)
"""


class JobStore:
    def __init__(self, path: str = "instagram_mvp.db"):
        self.path = Path(path)
        with self._connect() as con:
            con.execute(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create(self, video_url: str, caption: str, is_ai_generated: bool) -> int:
        now = self._now()
        with self._connect() as con:
            cursor = con.execute(
                """INSERT INTO reel_jobs
                (created_at, updated_at, video_url, caption, is_ai_generated)
                VALUES (?, ?, ?, ?, ?)""",
                (now, now, video_url, caption, int(is_ai_generated)),
            )
            return int(cursor.lastrowid)

    def get(self, job_id: int) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM reel_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Job {job_id} not found")
        return dict(row)

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM reel_jobs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update(self, job_id: int, **fields: Any) -> None:
        allowed = {
            "container_id", "container_status", "approved_at", "media_id",
            "permalink", "api_response_json"
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported fields: {sorted(unknown)}")
        values = dict(fields)
        if "api_response_json" in values and not isinstance(values["api_response_json"], str):
            values["api_response_json"] = json.dumps(values["api_response_json"], ensure_ascii=False)
        values["updated_at"] = self._now()
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as con:
            con.execute(
                f"UPDATE reel_jobs SET {assignments} WHERE id = ?",
                (*values.values(), job_id),
            )
