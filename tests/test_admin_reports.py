"""FR 6.2 and 6.3 — administrator reports and hub status.

Kept apart from test_app.py so feature branches adding tests do not all collide
on the end of one file. Fixtures and helpers come from test_app.
"""
from edureach import db as store
from test_app import app, client, csrf, login, make_lesson, make_quiz, post, setup_content  # noqa: F401


def test_reports_are_admin_only(client):
    login(client, "t1")
    assert client.get("/admin/reports").status_code == 403
    client.get("/logout")
    login(client, "s1")
    assert client.get("/admin/reports").status_code == 403


def test_reports_summarise_accounts_lessons_and_quizzes(client):
    setup_content(client)
    login(client, "s1")
    client.get("/lessons/1")
    post(client, "/quizzes/1", {"q1": "a", "q2": "b"})
    client.get("/logout")

    login(client, "admin")
    html = client.get("/admin/reports").get_data(as_text=True)
    assert "Hub status" in html
    assert "Mathematics" in html          # lessons by subject
    assert "Fractions quiz" in html       # quiz participation
    assert "Most opened lessons" in html


def test_hub_status_counts_records_still_waiting_to_sync(client, app):
    setup_content(client)
    login(client, "admin")
    html = client.get("/admin/reports").get_data(as_text=True)
    with app.app_context():
        pending = store.get_db().execute(
            "SELECT COUNT(*) FROM lessons WHERE sync_status = 'PENDING'"
        ).fetchone()[0]
    assert pending == 2                   # both seeded lessons are unsynced
    assert "Waiting to sync" in html


def test_switched_off_accounts_are_reported_separately(client, app):
    login(client, "admin")
    with app.app_context():
        sid = store.get_db().execute("SELECT id FROM users WHERE username='s2'").fetchone()[0]
    post(client, f"/admin/users/{sid}/toggle", {}, form_url="/admin/users")
    html = client.get("/admin/reports").get_data(as_text=True)
    assert "Switched off" in html


def test_human_size_reads_sensibly():
    from edureach import human_size
    assert human_size(0) == "0 B"
    assert human_size(900) == "900 B"
    assert human_size(2048) == "2.0 KB"
    assert human_size(5 * 1024 * 1024) == "5.0 MB"
