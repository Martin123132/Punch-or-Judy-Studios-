from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_CHARACTERS, DEFAULT_SCENES
from .models import Character, Performance, PerformanceLine, Scene, ShowProject
from .paths import db_path


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or db_path()), factory=ClosingConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    ensure_schema(con)
    return con


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scenes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS performances (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            scene_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audio_tracks (
            id TEXT PRIMARY KEY,
            performance_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(performance_id) REFERENCES performances(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS render_jobs (
            id TEXT PRIMARY KEY,
            performance_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(performance_id) REFERENCES performances(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            performance_id UNINDEXED,
            character_name,
            content
        );
        """
    )
    seed_defaults(con)
    con.commit()


def _upsert_payload(con: sqlite3.Connection, table: str, item_id: str, name: str, payload: dict[str, Any]) -> None:
    now = utc_now()
    con.execute(
        f"""
        INSERT INTO {table}(id, name, payload_json, created_at, updated_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        """,
        (item_id, name, json.dumps(payload), now, now),
    )


def seed_defaults(con: sqlite3.Connection) -> None:
    if con.execute("SELECT COUNT(*) FROM characters").fetchone()[0] == 0:
        for character in DEFAULT_CHARACTERS:
            _upsert_payload(con, "characters", character.id, character.name, character.to_dict())
    if con.execute("SELECT COUNT(*) FROM scenes").fetchone()[0] == 0:
        for scene in DEFAULT_SCENES:
            _upsert_payload(con, "scenes", scene.id, scene.name, scene.to_dict())
    if con.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
        project = ShowProject(
            id="first-show",
            name="First Puppet Show",
            description="A starter local-first show project.",
            created_at=utc_now(),
        )
        con.execute(
            "INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)",
            (project.id, project.name, project.description, project.created_at),
        )


def get_setting(con: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = con.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    return json.loads(row["value_json"])


def set_setting(con: sqlite3.Connection, key: str, value: Any) -> None:
    con.execute(
        """
        INSERT INTO settings(key, value_json, updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
        """,
        (key, json.dumps(value), utc_now()),
    )
    con.commit()


def list_settings(con: sqlite3.Connection) -> dict[str, Any]:
    rows = con.execute("SELECT key, value_json FROM settings ORDER BY key").fetchall()
    return {row["key"]: json.loads(row["value_json"]) for row in rows}


def list_projects(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def list_characters(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("SELECT payload_json FROM characters ORDER BY name COLLATE NOCASE").fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def get_character(con: sqlite3.Connection, character_id: str) -> dict[str, Any] | None:
    row = con.execute("SELECT payload_json FROM characters WHERE id=?", (character_id,)).fetchone()
    return json.loads(row["payload_json"]) if row else None


def save_character(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    _upsert_payload(con, "characters", payload["id"], payload["name"], payload)
    con.commit()
    return payload


def list_scenes(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("SELECT payload_json FROM scenes ORDER BY name COLLATE NOCASE").fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def get_scene(con: sqlite3.Connection, scene_id: str) -> dict[str, Any] | None:
    row = con.execute("SELECT payload_json FROM scenes WHERE id=?", (scene_id,)).fetchone()
    return json.loads(row["payload_json"]) if row else None


def save_scene(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    _upsert_payload(con, "scenes", payload["id"], payload["name"], payload)
    con.commit()
    return payload


def save_performance(con: sqlite3.Connection, performance: Performance) -> dict[str, Any]:
    payload = performance.to_dict()
    con.execute(
        """
        INSERT INTO performances(id, title, scene_id, prompt, provider, model, payload_json, created_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            scene_id=excluded.scene_id,
            prompt=excluded.prompt,
            provider=excluded.provider,
            model=excluded.model,
            payload_json=excluded.payload_json
        """,
        (
            performance.id,
            performance.title,
            performance.scene_id,
            performance.prompt,
            performance.provider,
            performance.model,
            json.dumps(payload),
            performance.created_at,
        ),
    )
    con.execute("DELETE FROM memory_fts WHERE performance_id=?", (performance.id,))
    for line in performance.lines:
        con.execute(
            "INSERT INTO memory_fts(performance_id, character_name, content) VALUES(?,?,?)",
            (performance.id, line.character_name, line.text),
        )
    con.commit()
    return payload


def list_performances(con: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT payload_json FROM performances ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def get_performance(con: sqlite3.Connection, performance_id: str) -> dict[str, Any] | None:
    row = con.execute("SELECT payload_json FROM performances WHERE id=?", (performance_id,)).fetchone()
    return json.loads(row["payload_json"]) if row else None


def save_audio_track(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    con.execute(
        """
        INSERT INTO audio_tracks(id, performance_id, payload_json, created_at)
        VALUES(?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json
        """,
        (payload["id"], payload["performance_id"], json.dumps(payload), utc_now()),
    )
    con.commit()
    return payload


def list_audio_tracks(con: sqlite3.Connection, performance_id: str) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT payload_json FROM audio_tracks WHERE performance_id=? ORDER BY created_at DESC",
        (performance_id,),
    ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def save_render_job(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    con.execute(
        """
        INSERT INTO render_jobs(id, performance_id, status, payload_json, created_at, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            status=excluded.status,
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        """,
        (payload["id"], payload["performance_id"], payload["status"], json.dumps(payload), now, now),
    )
    con.commit()
    return payload


def list_render_jobs(con: sqlite3.Connection, performance_id: str | None = None) -> list[dict[str, Any]]:
    if performance_id:
        rows = con.execute(
            "SELECT payload_json FROM render_jobs WHERE performance_id=? ORDER BY updated_at DESC",
            (performance_id,),
        ).fetchall()
    else:
        rows = con.execute("SELECT payload_json FROM render_jobs ORDER BY updated_at DESC LIMIT 50").fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def search_memory(con: sqlite3.Connection, query: str, limit: int = 10) -> list[dict[str, Any]]:
    terms = re.findall(r"[A-Za-z0-9_]{2,}", query)
    if not terms:
        return []
    fts_query = " OR ".join(f'"{term}"' for term in terms[:8])
    rows = con.execute(
        """
        SELECT performance_id, character_name, snippet(memory_fts, 2, '[', ']', '...', 10) AS snippet
        FROM memory_fts
        WHERE memory_fts MATCH ?
        LIMIT ?
        """,
        (fts_query, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def performance_from_payload(payload: dict[str, Any]) -> Performance:
    return Performance(
        id=payload["id"],
        title=payload["title"],
        scene_id=payload["scene_id"],
        prompt=payload["prompt"],
        lines=[PerformanceLine(**line) for line in payload["lines"]],
        created_at=payload["created_at"],
        provider=payload.get("provider", "local"),
        model=payload.get("model", "local-scriptwright"),
    )
