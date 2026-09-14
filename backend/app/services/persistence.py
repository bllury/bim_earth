from __future__ import annotations

import json
import sqlite3
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersistenceStore:
    """Stores BIM metadata in SQLite and model assets in the data directory."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self.projects_root = data_root / "projects"
        self.temp_root = data_root / "temp"
        self.database_path = data_root / "bim.sqlite3"
        self.projects_root.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.database_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    current_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_revisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    tiles_path TEXT NOT NULL,
                    metadata_path TEXT NOT NULL,
                    model_id TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    longitude REAL NOT NULL DEFAULT 0,
                    latitude REAL NOT NULL DEFAULT 0,
                    height REAL NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE TABLE IF NOT EXISTS camera_states (
                    project_id TEXT PRIMARY KEY,
                    camera_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
                CREATE INDEX IF NOT EXISTS idx_revisions_updated
                    ON model_revisions(updated_at DESC);
                """
            )

            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(model_revisions)")
            }
            for name, definition in (
                ("longitude", "REAL NOT NULL DEFAULT 0"),
                ("latitude", "REAL NOT NULL DEFAULT 0"),
                ("height", "REAL NOT NULL DEFAULT 0"),
                ("deleted_at", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE model_revisions ADD COLUMN {name} {definition}"
                    )

    def create_revision(
        self,
        file_name: str,
        longitude: float = 0,
        latitude: float = 0,
    ) -> dict[str, str]:
        now = utc_now()
        project_id = uuid.uuid4().hex
        revision_id = uuid.uuid4().hex
        revision_root = self.projects_root / project_id / "revisions" / revision_id
        tiles_path = revision_root / "tiles"
        tiles_path.mkdir(parents=True, exist_ok=True)
        source_path = revision_root / "source.ifc"
        metadata_path = revision_root / "metadata.json"

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO projects(id, name, current_revision_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, Path(file_name).stem or "未命名项目", revision_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO model_revisions(
                    id, project_id, file_name, source_path, tiles_path, metadata_path,
                    model_id, status, error, longitude, latitude, height, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, NULL, 'processing', NULL, ?, ?, 0, ?, ?)
                """,
                (
                    revision_id,
                    project_id,
                    Path(file_name).name,
                    str(source_path),
                    str(tiles_path),
                    str(metadata_path),
                    longitude,
                    latitude,
                    now,
                    now,
                ),
            )

        return {
            "project_id": project_id,
            "revision_id": revision_id,
            "source_path": str(source_path),
            "tiles_path": str(tiles_path),
            "metadata_path": str(metadata_path),
        }

    def update_revision(
        self,
        revision_id: str,
        *,
        status: str,
        model_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE model_revisions
                SET status = ?, model_id = COALESCE(?, model_id), error = ?, updated_at = ?
                WHERE id = ? AND deleted_at IS NULL
                """,
                (status, model_id, error, utc_now(), revision_id),
            )

    def get_revision(self, revision_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, p.name AS project_name
                FROM model_revisions r
                JOIN projects p ON p.id = r.project_id
                WHERE r.id = ?
                """,
                (revision_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_recent_completed_revision(self) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, p.name AS project_name
                FROM model_revisions r
                JOIN projects p ON p.id = r.project_id
                WHERE r.status = 'completed'
                  AND r.deleted_at IS NULL
                ORDER BY r.updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def delete_revision(self, revision_id: str) -> Optional[dict[str, Any]]:
        revision = self.get_revision(revision_id)
        if not revision:
            return None
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM camera_states WHERE project_id = ?",
                (revision["project_id"],),
            )
            connection.execute(
                """
                UPDATE model_revisions
                SET deleted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (utc_now(), utc_now(), revision_id),
            )
        project_root = self.projects_root / revision["project_id"]
        if project_root.exists():
            shutil.rmtree(project_root)
        return revision

    def save_camera(self, project_id: str, camera: dict[str, Any]) -> None:
        payload = json.dumps(camera, ensure_ascii=False)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO camera_states(project_id, camera_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    camera_json = excluded.camera_json,
                    updated_at = excluded.updated_at
                """,
                (project_id, payload, utc_now()),
            )

    def get_camera(self, project_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT camera_json FROM camera_states WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["camera_json"])
        except json.JSONDecodeError:
            return None
