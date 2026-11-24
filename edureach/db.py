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


def _migrate(conn):
    """Add columns needed by the offline sync layer to databases created
    before it existed. Safe to run on every start."""
    for table in ("lessons", "quiz_results", "activity"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "client_uuid" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN client_uuid TEXT")
            print(f"[DB] Migrated {table}: added client_uuid")
    # A client_uuid may only ever land once, so replaying the outbox after a
    # failed or partial sync can never duplicate a record.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lessons_uuid ON lessons (client_uuid) WHERE client_uuid IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_results_uuid ON quiz_results (client_uuid) WHERE client_uuid IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_uuid ON activity (client_uuid) WHERE client_uuid IS NOT NULL")


def init_db(path, seed=True):
    """Create the schema, apply migrations, and — on a brand new hub — load the
    demo accounts so a fresh deployment can be signed into straight away."""
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        if seed and conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            _seed_demo_data(conn)
    conn.close()


def _seed_demo_data(conn):
    """Load the demo accounts and two sample lessons. Only ever called against
    an empty database, so any failure here is a real bug and should surface."""
    from werkzeug.security import generate_password_hash

    users = [
        ("admin", "admin123", "Hub Administrator", "admin", None, "en"),
        ("teacher", "teach123", "Mukamana Claudine", "teacher", None, "en"),
        ("student", "1234", "Ishimwe Eric", "student", "P6", "en"),
    ]

    lessons = [
        ("Fractions: adding and subtracting", "Mathematics", "P6",
         "A fraction shows part of a whole. The top number is the numerator and "
         "the bottom number is the denominator.\n\n"
         "To add fractions with the same denominator, add the numerators and keep "
         "the denominator:\n   2/7 + 3/7 = 5/7\n\n"
         "If the denominators are different, first find a common denominator:\n"
         "   1/2 + 1/3 = 3/6 + 2/6 = 5/6",
         [("What is 2/7 + 3/7?", "5/7", "5/14", "6/7", "1/7", "a"),
          ("Which number is the denominator in 3/8?", "3", "8", "11", "24", "b"),
          ("What is 1/2 + 1/4?", "2/6", "1/6", "3/4", "2/4", "c")]),
        ("The water cycle", "Science", "P6",
         "Water moves around the Earth in a cycle.\n\n"
         "1. Evaporation: the sun heats water in lakes and rivers, and it rises as vapour.\n"
         "2. Condensation: the vapour cools and forms clouds.\n"
         "3. Precipitation: water falls back as rain.\n"
         "4. Collection: rain gathers in rivers, lakes and underground, and the cycle starts again.\n\n"
         "Lake Kivu and the Nyabarongo river are both part of Rwanda's water cycle.",
         [("What makes water rise as vapour?", "Wind", "The sun's heat", "Cold air", "Rocks", "b"),
          ("What do we call water falling as rain?", "Evaporation", "Condensation", "Precipitation", "Collection", "c")]),
        ("Parts of speech: nouns and verbs", "English", "P5",
         "A noun is the name of a person, place or thing: teacher, Kigali, book.\n"
         "A verb is an action word: run, read, write.\n\n"
         "Example: 'The pupil reads a book.'  pupil and book are nouns; reads is a verb.",
         []),
        ("Physical features of Rwanda", "Social Studies", "P6",
         "Rwanda is called the land of a thousand hills because most of the country "
         "is made up of hills and valleys.\n\n"
         "Mountains: the Virunga range lies in the north west. Mount Karisimbi is the "
         "highest point in Rwanda at 4,507 metres. Bisoke, Sabyinyo and Muhabura are "
         "part of the same range.\n\n"
         "Lakes: Lake Kivu in the west is the largest lake in Rwanda. Others are "
         "Burera, Ruhondo, Muhazi and Ihema.\n\n"
         "Rivers: the Nyabarongo is the longest river inside Rwanda. It joins other "
         "rivers to form the Akagera, which flows east towards Lake Victoria.",
         [("Which is the highest mountain in Rwanda?",
           "Muhabura", "Karisimbi", "Bisoke", "Sabyinyo", "b"),
          ("Which is the largest lake in Rwanda?",
           "Lake Muhazi", "Lake Burera", "Lake Kivu", "Lake Ihema", "c"),
          ("Which is the longest river inside Rwanda?",
           "Akagera", "Nyabarongo", "Ruhondo", "Mukungwa", "b"),
          ("Why is Rwanda called the land of a thousand hills?",
           "It has many lakes", "It has many hills and valleys",
           "It has many forests", "It has many rivers", "b")]),
        ("Parts of a computer", "ICT", "P6",
         "A computer has parts that work together.\n\n"
         "Input devices put information into the computer. The keyboard lets you type "
         "letters and numbers. The mouse lets you point and click.\n\n"
         "The system unit holds the processor, often called the CPU. The CPU does the "
         "thinking and is sometimes called the brain of the computer.\n\n"
         "Output devices show you the result. The monitor displays what the computer "
         "is doing. A printer puts the work on paper. Speakers play sound.\n\n"
         "Storage keeps your work after the computer is switched off, for example a "
         "hard disk or a flash disk.",
         [("Which of these is an input device?",
           "Monitor", "Printer", "Keyboard", "Speaker", "c"),
          ("Which part is often called the brain of the computer?",
           "The monitor", "The CPU", "The keyboard", "The mouse", "b"),
          ("Which device shows you what the computer is doing?",
           "The monitor", "The mouse", "The CPU", "The keyboard", "a"),
          ("Where is your work kept after the computer is switched off?",
           "In the mouse", "On the monitor", "On a hard disk or flash disk",
           "In the keyboard", "c")]),
        ("Writing in the past tense", "English", "P6",
         "We use the past tense to talk about something that has already happened.\n\n"
         "Most verbs are regular. We add -ed to the end:\n"
         "   walk becomes walked\n"
         "   play becomes played\n"
         "   visit becomes visited\n\n"
         "Some verbs are irregular. They change their whole form and must be learned:\n"
         "   go becomes went\n"
         "   eat becomes ate\n"
         "   see becomes saw\n"
         "   write becomes wrote\n\n"
         "Example: Today I walk to school. Yesterday I walked to school.\n"
         "Example: Today I go to the market. Yesterday I went to the market.",
         [("What is the past tense of 'walk'?",
           "walking", "walked", "walks", "walk", "b"),
          ("What is the past tense of 'go'?",
           "goed", "gone", "went", "going", "c"),
          ("Which sentence is correct?",
           "Yesterday I eat rice.", "Yesterday I ate rice.",
           "Yesterday I eating rice.", "Yesterday I eats rice.", "b"),
          ("Which of these verbs is irregular?",
           "play", "visit", "write", "jump", "c")]),
    ]

    ids = {}
    for username, pw, name, role, grade, lang in users:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, grade, language, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, generate_password_hash(pw), name, role, grade, lang, now()),
        )
        ids[username] = cur.lastrowid

    for title, subject, grade, body, questions in lessons:
        ts = now()
        lesson_id = conn.execute(
            "INSERT INTO lessons (teacher_id, title, subject, grade, body, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ids["teacher"], title, subject, grade, body, ts, ts),
        ).lastrowid
        if not questions:
            continue
        quiz_id = conn.execute(
            "INSERT INTO quizzes (lesson_id, teacher_id, title, created_at) VALUES (?, ?, ?, ?)",
            (lesson_id, ids["teacher"], f"{title.split(':')[0]} quiz", ts),
        ).lastrowid
        for pos, (prompt, a, b, c, d, correct) in enumerate(questions, 1):
            conn.execute(
                "INSERT INTO questions (quiz_id, position, prompt, option_a, option_b, option_c, option_d, correct)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (quiz_id, pos, prompt, a, b, c, d, correct),
            )

    print(f"[DB] Seeded {len(users)} demo accounts and {len(lessons)} lessons")


def log_event(db, user_id, event, detail):
    db.execute(
        "INSERT INTO audit_log (user_id, event, detail, at) VALUES (?, ?, ?, ?)",
        (user_id, event, detail, now()),
    )
