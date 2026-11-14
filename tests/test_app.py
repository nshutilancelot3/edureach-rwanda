import io
import re

import pytest
from werkzeug.security import generate_password_hash

from edureach import create_app
from edureach import db as store


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.db"),
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
    })
    with app.app_context():
        db = store.get_db()
        with db:
            for u, role, grade in [("admin", "admin", None), ("t1", "teacher", None),
                                   ("t2", "teacher", None), ("s1", "student", "P6"), ("s2", "student", "P6")]:
                db.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, grade, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (u, generate_password_hash("pass1234"), u.upper() + " Person", role, grade, store.now()),
                )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, url="/login"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def login(client, username, password="pass1234"):
    token = csrf(client)
    return client.post("/login", data={"username": username, "password": password, "csrf": token})


def post(client, url, data, form_url=None, **kw):
    data = dict(data, csrf=csrf(client, form_url or url))
    return client.post(url, data=data, **kw)


def make_lesson(client, title="Fractions", body="Notes about fractions"):
    return post(client, "/teacher/lessons/new",
                {"title": title, "subject": "Mathematics", "grade": "P6", "body": body})


def make_quiz(client, lesson_id=1):
    return post(client, f"/teacher/lessons/{lesson_id}/quiz", {
        "title": "Fractions quiz",
        "q1_prompt": "1/2 + 1/2 = ?", "q1_a": "1", "q1_b": "2", "q1_correct": "a",
        "q2_prompt": "Denominator of 3/8?", "q2_a": "3", "q2_b": "8", "q2_correct": "b",
    })


# ---------------------------------------------------------------- FR 1

def test_app_starts_without_configured_secret(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "x.db"), "UPLOAD_FOLDER": str(tmp_path / "u")})
    assert app.config["SECRET_KEY"]
    assert app.test_client().get("/login").status_code == 200


def test_login_success_and_failure(client):
    bad = login(client, "s1", "wrong")
    assert bad.status_code == 200 and b"Wrong username or password" in bad.data
    resp = login(client, "s1")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")


def test_post_without_csrf_is_rejected(client):
    assert client.post("/login", data={"username": "s1", "password": "pass1234"}).status_code == 400


def test_roles_are_enforced(client):
    login(client, "s1")
    assert client.get("/teacher").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_admin_creates_account_and_new_user_can_log_in(client):
    login(client, "admin")
    resp = post(client, "/admin/users", {"full_name": "New Kid", "username": "newkid",
                                         "password": "4321", "role": "student", "grade": "P5", "language": "rw"})
    assert resp.status_code == 302
    client.post("/logout", data={"csrf": csrf(client, "/admin/users")})
    assert login(client, "newkid", "4321").status_code == 302


def test_duplicate_username_rejected(client):
    login(client, "admin")
    resp = post(client, "/admin/users", {"full_name": "X", "username": "s1", "password": "4321",
                                         "role": "student", "grade": "P6"})
    assert b"already taken" in resp.data


def test_deactivated_account_cannot_log_in(client, app):
    login(client, "admin")
    with app.app_context():
        sid = store.get_db().execute("SELECT id FROM users WHERE username='s2'").fetchone()[0]
    post(client, f"/admin/users/{sid}/toggle", {}, form_url="/admin/users")
    client.post("/logout", data={"csrf": csrf(client, "/admin/users")})
    resp = login(client, "s2")
    assert resp.status_code == 200 and b"switched off" in resp.data


# ---------------------------------------------------------------- FR 2

def test_teacher_uploads_lesson_with_file(client, app):
    login(client, "t1")
    resp = post(client, "/teacher/lessons/new",
                {"title": "Water cycle", "subject": "Science", "grade": "P6", "body": "",
                 "file": (io.BytesIO(b"%PDF-1.4 test"), "water.pdf")},
                form_url="/teacher/lessons/new", content_type="multipart/form-data")
    assert resp.status_code == 302
    with app.app_context():
        row = store.get_db().execute("SELECT * FROM lessons").fetchone()
        assert row["file_name"].endswith("water.pdf") and row["sync_status"] == "PENDING"
        log = store.get_db().execute("SELECT event FROM audit_log").fetchall()
        assert ("upload_lesson",) in [tuple(r) for r in log]


def test_disallowed_file_type(client):
    login(client, "t1")
    resp = post(client, "/teacher/lessons/new",
                {"title": "Bad", "subject": "Science", "grade": "P6", "body": "x",
                 "file": (io.BytesIO(b"MZ"), "virus.exe")},
                form_url="/teacher/lessons/new", content_type="multipart/form-data")
    assert b"not allowed" in resp.data


def test_lesson_needs_notes_or_file(client):
    login(client, "t1")
    resp = make_lesson(client, body="")
    assert b"Add lesson notes or attach a file" in resp.data


def test_teacher_cannot_touch_another_teachers_lesson(client):
    login(client, "t1")
    make_lesson(client)
    client.post("/logout", data={"csrf": csrf(client, "/teacher")})
    login(client, "t2")
    assert client.get("/teacher/lessons/1/edit").status_code == 403
    assert post(client, "/teacher/lessons/1/delete", {}, form_url="/teacher").status_code == 403


def test_quiz_requires_answer_key(client):
    login(client, "t1")
    make_lesson(client)
    resp = post(client, "/teacher/lessons/1/quiz",
                {"q1_prompt": "Q?", "q1_a": "x", "q1_b": "y"})
    assert b"pick which filled-in option is correct" in resp.data


# ---------------------------------------------------------- FR 3 / FR 4

def setup_content(client):
    login(client, "t1")
    make_lesson(client)
    make_lesson(client, title="Water cycle", body="Evaporation and rain")
    make_quiz(client)
    client.post("/logout", data={"csrf": csrf(client, "/teacher")})


def test_student_browse_and_search(client):
    setup_content(client)
    login(client, "s1")
    html = client.get("/student").get_data(as_text=True)
    assert "Fractions" in html and "Water cycle" in html
    html = client.get("/student?q=rain").get_data(as_text=True)
    assert "Water cycle" in html and "Fractions" not in html
    html = client.get("/student?grade=S1").get_data(as_text=True)
    assert "No lessons found" in html


def test_viewing_lesson_records_activity(client, app):
    setup_content(client)
    login(client, "s1")
    assert b"Notes about fractions" in client.get("/lessons/1").data
    with app.app_context():
        assert store.get_db().execute("SELECT COUNT(*) FROM activity WHERE kind='view_lesson'").fetchone()[0] == 1


def test_quiz_auto_marks_and_locks_result(client, app):
    setup_content(client)
    login(client, "s1")
    url = "/quizzes/1"
    resp = post(client, url, {"q1": "a", "q2": "a"})  # one right, one wrong
    assert b"1 / 2" in resp.data
    # resubmitting can't change the locked result
    resp = post(client, url, {"q1": "a", "q2": "b"})
    assert b"1 / 2" in resp.data and b"already took this quiz" in resp.data
    with app.app_context():
        row = store.get_db().execute("SELECT score, sync_status FROM quiz_results").fetchone()
        assert tuple(row) == (1, "PENDING")


def test_quiz_must_answer_every_question(client):
    setup_content(client)
    login(client, "s1")
    resp = post(client, "/quizzes/1", {"q1": "a"})
    assert b"answer every question" in resp.data


def test_student_and_teacher_progress(client):
    setup_content(client)
    login(client, "s1")
    client.get("/lessons/1")
    post(client, "/quizzes/1", {"q1": "a", "q2": "b"})
    html = client.get("/student/progress").get_data(as_text=True)
    assert "2/2" in html and "100%" in html
    client.post("/logout", data={"csrf": csrf(client, "/student")})
    login(client, "t1")
    html = client.get("/teacher/progress").get_data(as_text=True)
    assert "S1 Person" in html and "100%" in html


def test_kinyarwanda_toggle(client):
    client.get("/lang/rw")
    assert "Injira" in client.get("/login").get_data(as_text=True)


# ------------------------------------------------------------- NFR 6

def test_database_uses_power_safe_settings(app):
    with app.app_context():
        db = store.get_db()
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL


def test_failed_write_leaves_no_partial_result(app):
    """If something fails mid-transaction (like a power cut), nothing half-saved remains."""
    with app.app_context():
        db = store.get_db()
        with pytest.raises(RuntimeError):
            with db:
                db.execute("INSERT INTO activity (student_id, kind, at) VALUES (4, 'view_lesson', 'x')")
                raise RuntimeError("power cut")
        assert db.execute("SELECT COUNT(*) FROM activity").fetchone()[0] == 0
