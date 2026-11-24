"""Teachers writing, editing and removing lessons with no connection.

Kept apart from test_app.py so feature branches adding tests do not all collide
on the end of one file. Fixtures and helpers come from test_app.
"""
from edureach import db as store
from test_app import app, client, csrf, login, make_lesson, make_quiz, post  # noqa: F401


def sync(client, items):
    return client.post("/api/sync", json={"items": items},
                       headers={"X-EduReach-Sync": "1"}).get_json()["results"]


def test_a_lesson_written_offline_reaches_the_hub(client, app):
    login(client, "t1")
    item = {"uuid": "lesson-1", "entity": "lesson", "op": "create",
            "payload": {"client_uuid": "lesson-1", "title": "Soil erosion",
                        "subject": "Science", "grade": "P6",
                        "body": "Terracing slows water running down a hill.",
                        "updated_at": "2026-11-20T08:00:00+00:00"}}
    assert sync(client, [item])[0]["status"] == "applied"

    with app.app_context():
        row = store.get_db().execute("SELECT * FROM lessons WHERE client_uuid='lesson-1'").fetchone()
        assert row["title"] == "Soil erosion"
        assert row["teacher_id"] == 2          # attributed to the signed-in teacher
        assert row["sync_status"] == "PENDING"


def test_replaying_a_lesson_never_creates_a_second_copy(client, app):
    login(client, "t1")
    item = {"uuid": "lesson-2", "entity": "lesson", "op": "create",
            "payload": {"client_uuid": "lesson-2", "title": "Soil erosion",
                        "subject": "Science", "grade": "P6", "body": "Notes."}}
    assert sync(client, [item])[0]["status"] == "applied"
    assert sync(client, [item])[0]["status"] == "duplicate"
    with app.app_context():
        assert store.get_db().execute("SELECT COUNT(*) FROM lessons").fetchone()[0] == 1


def test_an_offline_edit_and_delete_are_applied(client, app):
    login(client, "t1")
    make_lesson(client)
    assert sync(client, [{"uuid": "e1", "entity": "lesson", "op": "update",
                          "payload": {"id": 1, "title": "Fractions revised",
                                      "subject": "Mathematics", "grade": "P5",
                                      "body": "Updated notes."}}])[0]["status"] == "applied"
    with app.app_context():
        row = store.get_db().execute("SELECT * FROM lessons WHERE id=1").fetchone()
        assert row["title"] == "Fractions revised" and row["grade"] == "P5"

    assert sync(client, [{"uuid": "d1", "entity": "lesson", "op": "delete",
                          "payload": {"id": 1}}])[0]["status"] == "applied"
    with app.app_context():
        assert store.get_db().execute("SELECT COUNT(*) FROM lessons").fetchone()[0] == 0


def test_a_teacher_cannot_sync_an_edit_to_someone_elses_lesson(client, app):
    login(client, "t1")
    make_lesson(client)
    client.get("/logout")

    login(client, "t2")
    result = sync(client, [{"uuid": "e2", "entity": "lesson", "op": "update",
                            "payload": {"id": 1, "title": "Hijacked",
                                        "subject": "Science", "grade": "P6", "body": "x"}}])
    assert result[0]["status"] == "failed"
    with app.app_context():
        assert store.get_db().execute("SELECT title FROM lessons WHERE id=1").fetchone()[0] == "Fractions"


def test_deleting_a_lesson_the_hub_already_lost_is_not_an_error(client):
    """Two devices removing the same lesson must not leave one stuck retrying."""
    login(client, "t1")
    make_lesson(client)
    assert sync(client, [{"uuid": "d2", "entity": "lesson", "op": "delete",
                          "payload": {"id": 1}}])[0]["status"] == "applied"
    assert sync(client, [{"uuid": "d3", "entity": "lesson", "op": "delete",
                          "payload": {"id": 1}}])[0]["status"] == "duplicate"


def test_a_student_cannot_sync_lessons(client):
    login(client, "s1")
    result = sync(client, [{"uuid": "x1", "entity": "lesson", "op": "create",
                            "payload": {"client_uuid": "x1", "title": "Nope",
                                        "subject": "Science", "grade": "P6", "body": "x"}}])
    assert result[0]["status"] == "failed"
    assert "teachers" in result[0]["error"]


def test_an_offline_lesson_is_rejected_without_notes(client):
    login(client, "t1")
    result = sync(client, [{"uuid": "x2", "entity": "lesson", "op": "create",
                            "payload": {"client_uuid": "x2", "title": "Empty",
                                        "subject": "Science", "grade": "P6", "body": ""}}])
    assert result[0]["status"] == "failed"


def test_offline_lessons_are_written_to_the_audit_log(client, app):
    login(client, "t1")
    sync(client, [{"uuid": "lesson-3", "entity": "lesson", "op": "create",
                   "payload": {"client_uuid": "lesson-3", "title": "Soil erosion",
                               "subject": "Science", "grade": "P6", "body": "Notes."}}])
    with app.app_context():
        row = store.get_db().execute(
            "SELECT detail FROM audit_log WHERE event='upload_lesson'").fetchone()
        assert "offline" in row["detail"]
