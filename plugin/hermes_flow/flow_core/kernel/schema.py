"""SQLite 建表 DDL。

六张核心表：goal / todo / gate / evidence / checkpoint / experience。
- JSON 列表字段（scope/dependencies/artifacts/state）存 TEXT，store 层序列化。
- 时间戳统一用 Unix 秒（REAL）。
"""
from __future__ import annotations

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS goal (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    scope         TEXT NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL DEFAULT 'planning',
    workflow_id   TEXT NOT NULL DEFAULT '',
    quota_total   INTEGER NOT NULL DEFAULT 0,
    quota_used    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS todo (
    id               TEXT PRIMARY KEY,
    goal_id          TEXT NOT NULL REFERENCES goal(id) ON DELETE CASCADE,
    file_path        TEXT NOT NULL,
    phase            TEXT NOT NULL DEFAULT 'analyze',
    dependencies     TEXT NOT NULL DEFAULT '[]',
    owner_agent      TEXT,
    status           TEXT NOT NULL DEFAULT 'ready',
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    score            REAL,
    error            TEXT,
    lease_expires_at REAL,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_todo_goal ON todo(goal_id);
CREATE INDEX IF NOT EXISTS idx_todo_status ON todo(goal_id, status);

CREATE TABLE IF NOT EXISTS gate (
    id        TEXT PRIMARY KEY,
    goal_id   TEXT NOT NULL REFERENCES goal(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL,
    question  TEXT NOT NULL DEFAULT '',
    threshold REAL,
    status    TEXT NOT NULL DEFAULT 'open'
);
CREATE INDEX IF NOT EXISTS idx_gate_goal ON gate(goal_id);

CREATE TABLE IF NOT EXISTS evidence (
    id        TEXT PRIMARY KEY,
    todo_id   TEXT NOT NULL REFERENCES todo(id) ON DELETE CASCADE,
    agent_id  TEXT,
    score     REAL,
    artifacts TEXT NOT NULL DEFAULT '[]',
    notes     TEXT NOT NULL DEFAULT '',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_todo ON evidence(todo_id);

CREATE TABLE IF NOT EXISTS checkpoint (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id   TEXT NOT NULL REFERENCES goal(id) ON DELETE CASCADE,
    todo_id   TEXT,
    state     TEXT NOT NULL DEFAULT '{}',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_goal ON checkpoint(goal_id, id DESC);

CREATE TABLE IF NOT EXISTS experience (
    id         TEXT PRIMARY KEY,
    category   TEXT NOT NULL,
    trigger    TEXT NOT NULL,
    solution   TEXT NOT NULL,
    versions   TEXT,
    times_hit  INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experience_category ON experience(category);
"""
