from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS queries (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          conditions_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
          stage TEXT NOT NULL DEFAULT '等待查询', progress INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, completed_at TEXT, export_path TEXT, error TEXT
        );
        CREATE TABLE IF NOT EXISTS projects (
          id INTEGER PRIMARY KEY AUTOINCREMENT, query_id INTEGER NOT NULL,
          data_json TEXT NOT NULL, FOREIGN KEY(query_id) REFERENCES queries(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT, query_id INTEGER NOT NULL, project_id INTEGER,
          source_site TEXT NOT NULL, page_title TEXT NOT NULL, url TEXT NOT NULL,
          published_at TEXT, fetched_at TEXT NOT NULL, raw_text TEXT NOT NULL,
          category TEXT NOT NULL, grade TEXT NOT NULL,
          FOREIGN KEY(query_id) REFERENCES queries(id) ON DELETE CASCADE,
          FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS field_evidence (
          id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, source_id INTEGER NOT NULL,
          field_name TEXT NOT NULL, value TEXT NOT NULL, excerpt TEXT NOT NULL, grade TEXT NOT NULL,
          FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
          FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS query_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, query_id INTEGER NOT NULL,
          created_at TEXT NOT NULL, stage TEXT NOT NULL, target TEXT NOT NULL,
          status TEXT NOT NULL, message TEXT NOT NULL,
          FOREIGN KEY(query_id) REFERENCES queries(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_projects_query ON projects(query_id);
        CREATE INDEX IF NOT EXISTS idx_sources_query ON sources(query_id);
        CREATE INDEX IF NOT EXISTS idx_logs_query ON query_logs(query_id);
        """
        with self.connect() as conn:
            conn.executescript(schema)

    def create_query(self, conditions: dict[str, Any]) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO queries(conditions_json,status,stage,progress,created_at) VALUES(?,?,?,?,?)",
                (json.dumps(conditions, ensure_ascii=False), "queued", "等待查询", 0, now()),
            )
            return int(cur.lastrowid)

    def update_query(self, query_id: int, **values: Any) -> None:
        allowed = {"status", "stage", "progress", "completed_at", "export_path", "error"}
        items = [(key, value) for key, value in values.items() if key in allowed]
        if not items:
            return
        with self._lock, self.connect() as conn:
            conn.execute(f"UPDATE queries SET {', '.join(k + '=?' for k, _ in items)} WHERE id=?",
                         [value for _, value in items] + [query_id])

    def add_log(self, query_id: int, stage: str, target: str, status: str, message: str = "") -> None:
        with self._lock, self.connect() as conn:
            conn.execute("INSERT INTO query_logs(query_id,created_at,stage,target,status,message) VALUES(?,?,?,?,?,?)",
                         (query_id, now(), stage, target, status, message[:2000]))

    def save_project(self, query_id: int, data: dict[str, Any], sources: list[dict[str, Any]]) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute("INSERT INTO projects(query_id,data_json) VALUES(?,?)",
                               (query_id, json.dumps(data, ensure_ascii=False)))
            project_id = int(cur.lastrowid)
            for source in sources:
                cur = conn.execute(
                    """INSERT INTO sources(query_id,project_id,source_site,page_title,url,published_at,fetched_at,raw_text,category,grade)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (query_id, project_id, source["source_site"], source["page_title"], source["url"],
                     source.get("published_at", ""), source["fetched_at"], source["raw_text"],
                     source.get("category", "其他"), source.get("grade", "D")),
                )
                source_id = int(cur.lastrowid)
                for evidence in source.get("evidence", []):
                    conn.execute(
                        "INSERT INTO field_evidence(project_id,source_id,field_name,value,excerpt,grade) VALUES(?,?,?,?,?,?)",
                        (project_id, source_id, evidence["field_name"], evidence["value"],
                         evidence.get("excerpt", "")[:3000], evidence.get("grade", source.get("grade", "D"))),
                    )
            return project_id

    def query_detail(self, query_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM queries WHERE id=?", (query_id,)).fetchone()
            if not row:
                return None
            projects = [dict(item) for item in conn.execute("SELECT * FROM projects WHERE query_id=?", (query_id,))]
            sources = [dict(item) for item in conn.execute("SELECT * FROM sources WHERE query_id=? ORDER BY id", (query_id,))]
            evidence = [dict(item) for item in conn.execute(
                "SELECT e.* FROM field_evidence e JOIN projects p ON p.id=e.project_id WHERE p.query_id=? ORDER BY e.id", (query_id,))]
            logs = [dict(item) for item in conn.execute("SELECT * FROM query_logs WHERE query_id=? ORDER BY id", (query_id,))]
        result = dict(row)
        result["conditions"] = json.loads(result.pop("conditions_json"))
        result["projects"] = [{**p, "data": json.loads(p.pop("data_json"))} for p in projects]
        result["sources"] = sources
        result["evidence"] = evidence
        result["logs"] = logs
        return result

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM queries ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["conditions"] = json.loads(item.pop("conditions_json"))
            result.append(item)
        return result


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
