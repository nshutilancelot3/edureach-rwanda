"""SQLite storage for the Local Hub.

Power-loss safety (NFR 6): every connection runs in WAL mode with
synchronous=FULL, so a committed transaction survives a sudden power cut
and a half-finished one is rolled back cleanly on the next start.
"""
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'teacher', 'student')),
    grade         TEXT,
    language      TEXT    NOT NULL DEFAULT 'en',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id          INTEGER PRIMARY KEY,
    teacher_id  INTEGER NOT NULL REFERENCES users(id),
    title       TEXT    NOT NULL,
    subject     TEXT    NOT NULL,
    grade       TEXT    NOT NULL,
    body        TEXT    NOT NULL DEFAULT '',
    file_name   TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    sync_status TEXT    NOT NULL DEFAULT 'PENDING' CHECK (sync_status IN ('PENDING', 'SYNCED'))
);

CREATE TABLE IF NOT EXISTS quizzes (
    id          INTEGER PRIMARY KEY,
    lesson_id   INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    teacher_id  INTEGER NOT NULL REFERENCES users(id),
    title       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    sync_status TEXT    NOT NULL DEFAULT 'PENDING' CHECK (sync_status IN ('PENDING', 'SYNCED'))
);

CREATE TABLE IF NOT EXISTS questions (
    id            INTEGER PRIMARY KEY,
    quiz_id       INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    prompt        TEXT    NOT NULL,
    option_a      TEXT    NOT NULL,
    option_b      TEXT    NOT NULL,
    option_c      TEXT,
    option_d      TEXT,
    correct       TEXT    NOT NULL CHECK (correct IN ('a', 'b', 'c', 'd'))
);

-- One locked result per student per quiz (business rule: results can't be edited).
CREATE TABLE IF NOT EXISTS quiz_results (
    id           INTEGER PRIMARY KEY,
    quiz_id      INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    student_id   INTEGER NOT NULL REFERENCES users(id),
    score        INTEGER NOT NULL,
    total        INTEGER NOT NULL,
    answers      TEXT    NOT NULL,
    submitted_at TEXT    NOT NULL,
    sync_status  TEXT    NOT NULL DEFAULT 'PENDING' CHECK (sync_status IN ('PENDING', 'SYNCED')),
    UNIQUE (quiz_id, student_id)
);

CREATE TABLE IF NOT EXISTS activity (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES users(id),
    kind        TEXT    NOT NULL CHECK (kind IN ('view_lesson', 'submit_quiz')),
    lesson_id   INTEGER REFERENCES lessons(id) ON DELETE SET NULL,
    quiz_id     INTEGER REFERENCES quizzes(id) ON DELETE SET NULL,
    at          TEXT    NOT NULL,
    sync_status TEXT    NOT NULL DEFAULT 'PENDING' CHECK (sync_status IN ('PENDING', 'SYNCED'))
);

-- NFR 9: log of uploads (and, later, sync events) for administrators.
CREATE TABLE IF NOT EXISTS audit_log (
    id      INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event   TEXT    NOT NULL,
    detail  TEXT    NOT NULL,
    at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lessons_subject_grade ON lessons (subject, grade);
CREATE INDEX IF NOT EXISTS idx_results_student ON quiz_results (student_id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path):
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA)
    conn.close()


def log_event(db, user_id, event, detail):
    db.execute(
        "INSERT INTO audit_log (user_id, event, detail, at) VALUES (?, ?, ?, ?)",
        (user_id, event, detail, now()),
    )
