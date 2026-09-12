from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
DATABASE_PATH = ROOT / "waypoint.db"
LEGACY_MEMORY_PATH = ROOT / "memory.json"
DEFAULT_STRATEGY = "Start with the relevant campus section."


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_history (
                id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                answer TEXT NOT NULL,
                pages_json TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                adapted INTEGER NOT NULL DEFAULT 0,
                recovery_attempts INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        if not connection.execute("SELECT 1 FROM strategies LIMIT 1").fetchone():
            connection.execute(
                "INSERT INTO strategies (value, created_at) VALUES (?, ?)",
                (DEFAULT_STRATEGY, now_iso()),
            )
    migrate_legacy_memory()


def migrate_legacy_memory() -> None:
    if not LEGACY_MEMORY_PATH.exists():
        return
    try:
        legacy = json.loads(LEGACY_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    with connect() as connection:
        if connection.execute("SELECT 1 FROM task_history LIMIT 1").fetchone():
            return
        timestamp = now_iso()
        for value in legacy.get("preferences", []):
            connection.execute(
                "INSERT OR IGNORE INTO preferences (value, created_at) VALUES (?, ?)",
                (str(value), timestamp),
            )
        for value in legacy.get("strategies", []):
            connection.execute(
                "INSERT OR IGNORE INTO strategies (value, created_at) VALUES (?, ?)",
                (str(value), timestamp),
            )
        for task in legacy.get("history", []):
            insert_task(connection, task)


def insert_task(connection: sqlite3.Connection, task: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO task_history
        (id, command, answer, pages_json, actions_json, adapted, recovery_attempts, duration_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(task.get("id", "legacy-task")),
            str(task.get("command", "")),
            str(task.get("answer", "")),
            json.dumps(task.get("pages", [])),
            json.dumps(task.get("actions", [])),
            int(bool(task.get("adapted", False))),
            int(task.get("recovery_attempts", 0)),
            int(task.get("duration_ms", 0)),
            str(task.get("created_at", now_iso())),
        ),
    )


def load_memory() -> dict[str, Any]:
    initialize_database()
    with connect() as connection:
        preferences = [row["value"] for row in connection.execute("SELECT value FROM preferences ORDER BY id DESC")]
        strategies = [row["value"] for row in connection.execute("SELECT value FROM strategies ORDER BY id DESC")]
        history = []
        for row in connection.execute("SELECT * FROM task_history ORDER BY created_at DESC LIMIT 12"):
            history.append({
                "id": row["id"],
                "command": row["command"],
                "answer": row["answer"],
                "pages": json.loads(row["pages_json"]),
                "actions": json.loads(row["actions_json"]),
                "adapted": bool(row["adapted"]),
                "recovery_attempts": row["recovery_attempts"],
                "duration_ms": row["duration_ms"],
                "created_at": row["created_at"],
            })
    return {"preferences": preferences, "strategies": strategies, "history": history}


def save_memory(memory: dict[str, Any]) -> None:
    initialize_database()
    with connect() as connection:
        connection.execute("DELETE FROM preferences")
        connection.execute("DELETE FROM strategies")
        connection.execute("DELETE FROM task_history")
        timestamp = now_iso()
        for value in memory.get("preferences", []):
            connection.execute("INSERT OR IGNORE INTO preferences (value, created_at) VALUES (?, ?)", (str(value), timestamp))
        for value in memory.get("strategies", []) or [DEFAULT_STRATEGY]:
            connection.execute("INSERT OR IGNORE INTO strategies (value, created_at) VALUES (?, ?)", (str(value), timestamp))
        for task in memory.get("history", [])[:12]:
            insert_task(connection, task)


initialize_database()
