"""EduReach Rwanda — Local Hub web app (v1.0, first increment)."""
import json
import os
import secrets
from functools import wraps

from flask import (
    Flask, abort, flash, g, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from . import db as store
from .i18n import SUPPORTED, translate

ALLOWED_FILES = {"pdf", "png", "jpg", "jpeg", "mp4", "pptx", "txt"}
SUBJECTS = ["Mathematics", "English", "Kinyarwanda", "Science", "Social Studies", "ICT"]
GRADES = ["P4", "P5", "P6", "S1", "S2", "S3"]
OPTION_KEYS = ("a", "b", "c", "d")
MAX_QUESTIONS = 5


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        DATABASE=os.path.join(app.instance_path, "edureach.db"),
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ.get("EDUREACH_SECRET_KEY") or _load_secret(app.instance_path)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    store.init_db(app.config["DATABASE"])
    app.teardown_appcontext(store.close_db)

    # Auto-seed demo data if database is empty
    with app.app_context():
        db = store.get_db()
        try:
            user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if user_count == 0:
                _load_demo_data(db)
        except Exception:
            pass

    _register_helpers(app)
    _register_routes(app)
    return app


def _load_demo_data(db):
    """Load demo accounts and lessons on first startup."""
    try:
        USERS = [
            ("admin", "admin123", "Hub Administrator", "admin", None, "en"),
            ("teacher", "teach123", "Mukamana Claudine", "teacher", None, "en"),
            ("student", "1234", "Ishimwe Eric", "student", "P6", "en"),
        ]

        LESSONS = [
            ("Fractions: adding and subtracting", "Mathematics", "P6",
             "A fraction shows part of a whole. The top number is the numerator and the bottom number is the denominator.\n\n"
             "To add fractions with the same denominator, add the numerators and keep the denominator:\n"
             "   2/7 + 3/7 = 5/7",
             [("What is 2/7 + 3/7?", "5/7", "5/14", "6/7", "1/7", "a"),
              ("Which number is the denominator in 3/8?", "3", "8", "11", "24", "b"),
              ("What is 1/2 + 1/4?", "2/6", "1/6", "3/4", "2/4", "c")]),
            ("The water cycle", "Science", "P6",
             "Water moves around the Earth in a cycle.\n\n"
             "1. Evaporation: the sun heats water in lakes and rivers, and it rises as vapour.\n"
             "2. Condensation: the vapour cools and forms clouds.\n"
             "3. Precipitation: water falls back as rain.\n"
             "4. Collection: rain gathers in rivers, lakes and underground, and the cycle starts again.",
             [("What makes water rise as vapour?", "Wind", "The sun's heat", "Cold air", "Rocks", "b"),
              ("What do we call water falling as rain?", "Evaporation", "Condensation", "Precipitation", "Collection", "c")]),
        ]

        ids = {}
        with db:
            for username, pw, name, role, grade, lang in USERS:
                cur = db.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, grade, language, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (username, generate_password_hash(pw), name, role, grade, lang, store.now()),
                )
                ids[username] = cur.lastrowid

            for title, subject, grade, body, questions in LESSONS:
                ts = store.now()
                lesson_id = db.execute(
                    "INSERT INTO lessons (teacher_id, title, subject, grade, body, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)", (ids["teacher"], title, subject, grade, body, ts, ts),
                ).lastrowid
                if questions:
                    quiz_id = db.execute(
                        "INSERT INTO quizzes (lesson_id, teacher_id, title, created_at) VALUES (?, ?, ?, ?)",
                        (lesson_id, ids["teacher"], f"{title.split(':')[0]} quiz", ts),
                    ).lastrowid
                    for pos, (prompt, a, b, c, d, correct) in enumerate(questions, 1):
                        db.execute(
                            "INSERT INTO questions (quiz_id, position, prompt, option_a, option_b, option_c, option_d, correct)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (quiz_id, pos, prompt, a, b, c, d, correct),
                        )
    except Exception as e:
        print(f"Demo data already loaded or error: {e}")


def _load_secret(instance_path):
    path = os.path.join(instance_path, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(path) as fh:
        return fh.read().strip()


# ---------------------------------------------------------------- helpers

def _register_helpers(app):
    @app.before_request
    def load_user():
        g.user = None
        uid = session.get("user_id")
        if uid:
            user = store.get_db().execute(
                "SELECT * FROM users WHERE id = ? AND active = 1", (uid,)
            ).fetchone()
            if user is None:
                session.clear()
            g.user = user
        g.lang = session.get("lang") or (g.user["language"] if g.user else "en")
        if request.method == "POST":
            token = session.get("csrf")
            if not token or token != request.form.get("csrf"):
                abort(400)

    @app.context_processor
    def inject():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return {
            "t": lambda key: translate(key, g.lang),
            "lang": g.lang,
            "csrf": session["csrf"],
            "SUBJECTS": SUBJECTS,
            "GRADES": GRADES,
        }


def login_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login"))
            if roles and g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _save_upload(file_storage, folder):
    """Write the file to a temp name, fsync, then rename — so a power cut
    never leaves a half-written lesson file behind (NFR 6)."""
    if not file_storage or not file_storage.filename:
        return None
    name = secure_filename(file_storage.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_FILES:
        raise ValueError(f"File type .{ext} is not allowed.")
    final = f"{secrets.token_hex(6)}_{name}"
    tmp = os.path.join(folder, final + ".part")
    with open(tmp, "wb") as fh:
        file_storage.save(fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, os.path.join(folder, final))
    return final


def _own_lesson(lesson_id):
    lesson = store.get_db().execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
    if lesson is None:
        abort(404)
    if lesson["teacher_id"] != g.user["id"]:
        abort(403)  # business rule: teachers only touch their own content
    return lesson


# ----------------------------------------------------------------- routes

def _register_routes(app):

    @app.route("/")
    def home():
        if g.user is None:
            return redirect(url_for("login"))
        return redirect(url_for({
            "admin": "admin_users", "teacher": "teacher_home", "student": "student_home",
        }[g.user["role"]]))

    @app.route("/lang/<code>")
    def set_lang(code):
        if code in SUPPORTED:
            session["lang"] = code
        return redirect(request.referrer or url_for("home"))

    # FR 1.2 — offline login on the hub
    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            user = store.get_db().execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            if user is None or not check_password_hash(user["password_hash"], request.form.get("password", "")):
                error = translate("login_failed", g.lang)
            elif not user["active"]:
                error = translate("account_off", g.lang)
            else:
                lang = session.get("lang", user["language"])
                session.clear()
                session["user_id"] = user["id"]
                session["lang"] = lang
                return redirect(url_for("home"))
        return render_template("login.html", error=error)

    @app.route("/logout", methods=["POST"])
    def logout():
        lang = session.get("lang")
        session.clear()
        if lang:
            session["lang"] = lang
        return redirect(url_for("login"))

    # ------------------------------------------------------------ admin
    # FR 1.1 create accounts, FR 6.1 activate / deactivate
    @app.route("/admin/users", methods=["GET", "POST"])
    @login_required("admin")
    def admin_users():
        db = store.get_db()
        if request.method == "POST":
            f = request.form
            username = f.get("username", "").strip().lower()
            password = f.get("password", "")
            role = f.get("role")
            errors = []
            if not username or not username.replace("_", "").replace(".", "").isalnum():
                errors.append("Username can only use letters, numbers, dots and underscores.")
            if len(password) < 4:
                errors.append("Password or PIN must be at least 4 characters.")
            if role not in ("admin", "teacher", "student"):
                errors.append("Choose a role.")
            if role == "student" and f.get("grade") not in GRADES:
                errors.append("Students need a grade.")
            if not f.get("full_name", "").strip():
                errors.append("Full name is required.")
            if not errors and db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                errors.append("That username is already taken.")
            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                with db:
                    db.execute(
                        "INSERT INTO users (username, password_hash, full_name, role, grade, language, created_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (username, generate_password_hash(password), f["full_name"].strip(), role,
                         f.get("grade") if role == "student" else None,
                         f.get("language") if f.get("language") in SUPPORTED else "en", store.now()),
                    )
                    store.log_event(db, g.user["id"], "create_account", f"{role} {username}")
                flash(f"Account created for {username}.", "ok")
                return redirect(url_for("admin_users"))
        users = db.execute("SELECT * FROM users ORDER BY role, full_name").fetchall()
        return render_template("admin/users.html", users=users)

    @app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
    @login_required("admin")
    def admin_toggle(user_id):
        if user_id == g.user["id"]:
            flash("You can't switch off your own account.", "error")
            return redirect(url_for("admin_users"))
        db = store.get_db()
        with db:
            db.execute("UPDATE users SET active = 1 - active WHERE id = ?", (user_id,))
            store.log_event(db, g.user["id"], "toggle_account", str(user_id))
        return redirect(url_for("admin_users"))

    @app.route("/admin/log")
    @login_required("admin")
    def admin_log():
        rows = store.get_db().execute(
            "SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id"
            " ORDER BY a.id DESC LIMIT 200"
        ).fetchall()
        return render_template("admin/log.html", rows=rows)

    # ---------------------------------------------------------- teacher
    @app.route("/teacher")
    @login_required("teacher")
    def teacher_home():
        db = store.get_db()
        lessons = db.execute(
            "SELECT l.*, (SELECT COUNT(*) FROM quizzes q WHERE q.lesson_id = l.id) AS quiz_count"
            " FROM lessons l WHERE teacher_id = ? ORDER BY updated_at DESC", (g.user["id"],)
        ).fetchall()
        return render_template("teacher/home.html", lessons=lessons)

    # FR 2.1 upload, FR 2.2 edit
    @app.route("/teacher/lessons/new", methods=["GET", "POST"])
    @app.route("/teacher/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
    @login_required("teacher")
    def lesson_form(lesson_id=None):
        lesson = _own_lesson(lesson_id) if lesson_id else None
        if request.method == "POST":
            f = request.form
            title, subject, grade = f.get("title", "").strip(), f.get("subject"), f.get("grade")
            body = f.get("body", "").strip()
            errors = []
            if not title:
                errors.append("Give the lesson a title.")
            if subject not in SUBJECTS:
                errors.append("Choose a subject.")
            if grade not in GRADES:
                errors.append("Choose a grade.")
            file_name = lesson["file_name"] if lesson else None
            if not errors:
                try:
                    new_file = _save_upload(request.files.get("file"), app.config["UPLOAD_FOLDER"])
                    file_name = new_file or file_name
                except ValueError as exc:
                    errors.append(str(exc))
            if not errors and not body and not file_name:
                errors.append("Add lesson notes or attach a file.")
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("teacher/lesson_form.html", lesson=lesson, form=f)
            db = store.get_db()
            ts = store.now()
            with db:
                if lesson:
                    db.execute(
                        "UPDATE lessons SET title=?, subject=?, grade=?, body=?, file_name=?, updated_at=?,"
                        " sync_status='PENDING' WHERE id=?",
                        (title, subject, grade, body, file_name, ts, lesson["id"]),
                    )
                    store.log_event(db, g.user["id"], "edit_lesson", title)
                else:
                    db.execute(
                        "INSERT INTO lessons (teacher_id, title, subject, grade, body, file_name, created_at, updated_at)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (g.user["id"], title, subject, grade, body, file_name, ts, ts),
                    )
                    store.log_event(db, g.user["id"], "upload_lesson", title)
            flash("Lesson saved.", "ok")
            return redirect(url_for("teacher_home"))
        return render_template("teacher/lesson_form.html", lesson=lesson, form=lesson or {})

    @app.route("/teacher/lessons/<int:lesson_id>/delete", methods=["POST"])
    @login_required("teacher")
    def lesson_delete(lesson_id):
        lesson = _own_lesson(lesson_id)
        db = store.get_db()
        with db:
            db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            store.log_event(db, g.user["id"], "delete_lesson", lesson["title"])
        flash("Lesson removed.", "ok")
        return redirect(url_for("teacher_home"))

    # FR 2.3 create quiz with answer key
    @app.route("/teacher/lessons/<int:lesson_id>/quiz", methods=["GET", "POST"])
    @login_required("teacher")
    def quiz_form(lesson_id):
        lesson = _own_lesson(lesson_id)
        if request.method == "POST":
            f = request.form
            title = f.get("title", "").strip() or f"{lesson['title']} quiz"
            questions, errors = [], []
            for i in range(1, MAX_QUESTIONS + 1):
                prompt = f.get(f"q{i}_prompt", "").strip()
                if not prompt:
                    continue
                opts = {k: f.get(f"q{i}_{k}", "").strip() for k in OPTION_KEYS}
                correct = f.get(f"q{i}_correct")
                if not opts["a"] or not opts["b"]:
                    errors.append(f"Question {i} needs at least options A and B.")
                elif correct not in OPTION_KEYS or not opts[correct]:
                    errors.append(f"Question {i}: pick which filled-in option is correct.")
                else:
                    questions.append((prompt, opts, correct))
            if not questions and not errors:
                errors.append("Add at least one question.")
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template("teacher/quiz_form.html", lesson=lesson, form=f, n=MAX_QUESTIONS)
            db = store.get_db()
            with db:
                cur = db.execute(
                    "INSERT INTO quizzes (lesson_id, teacher_id, title, created_at) VALUES (?, ?, ?, ?)",
                    (lesson_id, g.user["id"], title, store.now()),
                )
                for pos, (prompt, opts, correct) in enumerate(questions, 1):
                    db.execute(
                        "INSERT INTO questions (quiz_id, position, prompt, option_a, option_b, option_c, option_d, correct)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (cur.lastrowid, pos, prompt, opts["a"], opts["b"], opts["c"] or None, opts["d"] or None, correct),
                    )
                store.log_event(db, g.user["id"], "create_quiz", title)
            flash(f"Quiz saved with {len(questions)} question(s).", "ok")
            return redirect(url_for("teacher_home"))
        return render_template("teacher/quiz_form.html", lesson=lesson, form={}, n=MAX_QUESTIONS)

    # FR 4.3 class progress (only on this teacher's quizzes)
    @app.route("/teacher/progress")
    @login_required("teacher")
    def teacher_progress():
        db = store.get_db()
        quizzes = db.execute(
            "SELECT q.id, q.title, l.grade, l.subject,"
            " COUNT(r.id) AS attempts, ROUND(AVG(100.0 * r.score / r.total)) AS avg_pct"
            " FROM quizzes q JOIN lessons l ON l.id = q.lesson_id"
            " LEFT JOIN quiz_results r ON r.quiz_id = q.id"
            " WHERE q.teacher_id = ? GROUP BY q.id ORDER BY q.created_at DESC", (g.user["id"],)
        ).fetchall()
        results = db.execute(
            "SELECT r.*, u.full_name, u.grade, q.title FROM quiz_results r"
            " JOIN users u ON u.id = r.student_id JOIN quizzes q ON q.id = r.quiz_id"
            " WHERE q.teacher_id = ? ORDER BY r.submitted_at DESC", (g.user["id"],)
        ).fetchall()
        return render_template("teacher/progress.html", quizzes=quizzes, results=results)

    # ---------------------------------------------------------- student
    # FR 3.1 browse + search
    @app.route("/student")
    @login_required("student")
    def student_home():
        subject = request.args.get("subject", "")
        grade = request.args.get("grade", g.user["grade"] or "")
        q = request.args.get("q", "").strip()
        sql = ("SELECT l.*, (SELECT q.id FROM quizzes q WHERE q.lesson_id = l.id LIMIT 1) AS quiz_id"
               " FROM lessons l WHERE 1=1")
        params = []
        if subject in SUBJECTS:
            sql += " AND subject = ?"
            params.append(subject)
        if grade in GRADES:
            sql += " AND grade = ?"
            params.append(grade)
        if q:
            sql += " AND (title LIKE ? OR body LIKE ?)"
            params += [f"%{q}%", f"%{q}%"]
        sql += " ORDER BY subject, title"
        lessons = store.get_db().execute(sql, params).fetchall()
        return render_template("student/home.html", lessons=lessons, subject=subject, grade=grade, q=q)

    # FR 3.2 view lesson + FR 4.1 record activity
    @app.route("/lessons/<int:lesson_id>")
    @login_required("student")
    def lesson_view(lesson_id):
        db = store.get_db()
        lesson = db.execute(
            "SELECT l.*, u.full_name AS teacher FROM lessons l JOIN users u ON u.id = l.teacher_id WHERE l.id = ?",
            (lesson_id,),
        ).fetchone()
        if lesson is None:
            abort(404)
        quizzes = db.execute("SELECT * FROM quizzes WHERE lesson_id = ?", (lesson_id,)).fetchall()
        taken = {r["quiz_id"] for r in db.execute(
            "SELECT quiz_id FROM quiz_results WHERE student_id = ?", (g.user["id"],))}
        with db:
            db.execute(
                "INSERT INTO activity (student_id, kind, lesson_id, at) VALUES (?, 'view_lesson', ?, ?)",
                (g.user["id"], lesson_id, store.now()),
            )
        return render_template("student/lesson.html", lesson=lesson, quizzes=quizzes, taken=taken)

    @app.route("/files/<path:name>")
    @login_required()
    def lesson_file(name):
        return send_from_directory(app.config["UPLOAD_FOLDER"], name)

    # FR 3.3 take quiz offline, auto-mark, lock result
    @app.route("/quizzes/<int:quiz_id>", methods=["GET", "POST"])
    @login_required("student")
    def quiz_take(quiz_id):
        db = store.get_db()
        quiz = db.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        if quiz is None:
            abort(404)
        questions = db.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)
        ).fetchall()
        existing = db.execute(
            "SELECT * FROM quiz_results WHERE quiz_id = ? AND student_id = ?", (quiz_id, g.user["id"])
        ).fetchone()
        if existing:
            return render_template("student/quiz_result.html", quiz=quiz, questions=questions,
                                   result=existing, answers=json.loads(existing["answers"]), locked=True)
        if request.method == "POST":
            answers = {str(qn["id"]): request.form.get(f"q{qn['id']}") for qn in questions}
            if any(a not in OPTION_KEYS for a in answers.values()):
                flash(translate("answer_all", g.lang), "error")
                return render_template("student/quiz.html", quiz=quiz, questions=questions, chosen=answers)
            score = sum(1 for qn in questions if answers[str(qn["id"])] == qn["correct"])
            with db:  # result + activity commit together or not at all
                db.execute(
                    "INSERT INTO quiz_results (quiz_id, student_id, score, total, answers, submitted_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (quiz_id, g.user["id"], score, len(questions), json.dumps(answers), store.now()),
                )
                db.execute(
                    "INSERT INTO activity (student_id, kind, quiz_id, lesson_id, at) VALUES (?, 'submit_quiz', ?, ?, ?)",
                    (g.user["id"], quiz_id, quiz["lesson_id"], store.now()),
                )
            result = db.execute(
                "SELECT * FROM quiz_results WHERE quiz_id = ? AND student_id = ?", (quiz_id, g.user["id"])
            ).fetchone()
            return render_template("student/quiz_result.html", quiz=quiz, questions=questions,
                                   result=result, answers=answers, locked=False)
        return render_template("student/quiz.html", quiz=quiz, questions=questions, chosen={})

    # FR 4.2 own progress
    @app.route("/student/progress")
    @login_required("student")
    def student_progress():
        db = store.get_db()
        results = db.execute(
            "SELECT r.*, q.title, l.subject FROM quiz_results r JOIN quizzes q ON q.id = r.quiz_id"
            " JOIN lessons l ON l.id = q.lesson_id WHERE r.student_id = ? ORDER BY r.submitted_at DESC",
            (g.user["id"],),
        ).fetchall()
        opened = db.execute(
            "SELECT COUNT(DISTINCT lesson_id) FROM activity WHERE student_id = ? AND kind = 'view_lesson'",
            (g.user["id"],),
        ).fetchone()[0]
        avg = round(sum(100 * r["score"] / r["total"] for r in results) / len(results)) if results else None
        return render_template("student/progress.html", results=results, opened=opened, avg=avg)

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, message="You don't have access to that page."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="That page doesn't exist."), 404
