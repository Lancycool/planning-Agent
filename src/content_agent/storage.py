"""SQLite business persistence. Every saved plan and task snapshot commit together."""

import json
import sqlite3
from pathlib import Path
from typing import Any


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                request_id TEXT PRIMARY KEY REFERENCES tasks(request_id),
                plan_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL
            );
        """)

    def get(self, request_id: str) -> dict | None:
        row = self.db.execute("SELECT fingerprint, snapshot FROM tasks WHERE request_id=?", (request_id,)).fetchone()
        return {"fingerprint": row[0], "state": json.loads(row[1])} if row else None

    def write(self, state: dict, plan: dict | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?) ON CONFLICT(request_id) DO UPDATE SET snapshot=excluded.snapshot",
                (state["request"]["request_id"], state["fingerprint"], dumps(state)),
            )
            if plan is not None:
                self.db.execute("INSERT INTO plans VALUES (?, ?, ?)",
                                (state["request"]["request_id"], plan["plan_id"], dumps(plan)))

    def read_plan(self, request_id: str) -> dict | None:
        row = self.db.execute("SELECT body FROM plans WHERE request_id=?", (request_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def count_plans(self) -> int:
        return self.db.execute("SELECT count(*) FROM plans").fetchone()[0]

    def close(self) -> None:
        self.db.close()
