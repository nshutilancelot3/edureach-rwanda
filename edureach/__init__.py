"""EduReach Rwanda — Local Hub web app (v1.0, first increment)."""
import json
import os
import secrets
from datetime import timedelta
from functools import wraps

from flask import (
    Flask, abort, flash, g, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from . import db as store
from .i18n import STRINGS, SUPPORTED, translate

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
        # A shared classroom tablet gets closed and reopened constantly, often
        # with no connection in between. A session cookie would log the pupil
        # out on every restart, so the sign-in is kept for a school term.
        PERMANENT_SESSION_LIFETIME=timedelta(days=90),
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ.get("EDUREACH_SECRET_KEY") or _load_secret(app.instance_path)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    # A fresh hub seeds itself with the demo accounts so a new deployment is
    # usable immediately. Tests bring their own fixtures, so they opt out.
    store.init_db(app.config["DATABASE"], seed=not app.config.get("TESTING"))
    app.teardown_appcontext(store.close_db)

    _register_helpers(app)
    _register_routes(app)
    return app


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
            if request.path.startswith("/api/"):
                # The sync endpoint posts JSON, so it carries no form token.
                # SameSite=Lax already stops another site sending our cookie on
                # a cross-site POST; requiring a custom header on top of that
                # means a hostile page would need a CORS preflight we never allow.
                if request.headers.get("X-EduReach-Sync") != "1":
                    abort(400)
            else:
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
            "human_size": human_size,
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


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _folder_size(folder):
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            total += _file_size(os.path.join(root, name))
    return total


def _folder_count(folder):
    return sum(len(files) for _root, _dirs, files in os.walk(folder))


def human_size(num_bytes):
    """Sizes an administrator can read at a glance on a small screen."""
    value = float(num_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


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
                session.permanent = True      # survives closing the browser
                session["user_id"] = user["id"]
                session["lang"] = lang
                return redirect(url_for("home"))
        return render_template("login.html", error=error)

    @app.route("/logout", methods=["GET", "POST"])
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

    # FR 6.2 reports + FR 6.3 hub status. An administrator visiting a school
    # needs to answer "is this hub healthy and is it being used?" without a
    # connection and without reading the database by hand.
    @app.route("/admin/reports")
    @login_required("admin")
    def admin_reports():
        db = store.get_db()

        def scalar(sql, args=()):
            return db.execute(sql, args).fetchone()[0]

        accounts = db.execute(
            "SELECT role, SUM(active) AS on_count, COUNT(*) - SUM(active) AS off_count"
            " FROM users GROUP BY role ORDER BY role"
        ).fetchall()

        by_subject = db.execute(
            "SELECT subject, COUNT(*) AS n FROM lessons GROUP BY subject ORDER BY n DESC, subject"
        ).fetchall()
        by_grade = db.execute(
            "SELECT grade, COUNT(*) AS n FROM lessons GROUP BY grade ORDER BY grade"
        ).fetchall()

        popular = db.execute(
            "SELECT l.title, l.subject, l.grade, COUNT(a.id) AS opens"
            " FROM lessons l LEFT JOIN activity a"
            "   ON a.lesson_id = l.id AND a.kind = 'view_lesson'"
            " GROUP BY l.id ORDER BY opens DESC, l.title LIMIT 5"
        ).fetchall()

        quizzes = db.execute(
            "SELECT q.title, l.grade, COUNT(r.id) AS attempts,"
            " ROUND(AVG(100.0 * r.score / r.total)) AS avg_pct"
            " FROM quizzes q JOIN lessons l ON l.id = q.lesson_id"
            " LEFT JOIN quiz_results r ON r.quiz_id = q.id"
            " GROUP BY q.id ORDER BY attempts DESC, q.title"
        ).fetchall()

        # FR 5 is not built yet, so everything still reads PENDING. Showing the
        # backlog now means the figure is already meaningful the day sync lands.
        pending = {
            "lessons": scalar("SELECT COUNT(*) FROM lessons WHERE sync_status = 'PENDING'"),
            "results": scalar("SELECT COUNT(*) FROM quiz_results WHERE sync_status = 'PENDING'"),
            "activity": scalar("SELECT COUNT(*) FROM activity WHERE sync_status = 'PENDING'"),
        }

        status = {
            "database_bytes": _file_size(app.config["DATABASE"]),
            "uploads_bytes": _folder_size(app.config["UPLOAD_FOLDER"]),
            "upload_count": _folder_count(app.config["UPLOAD_FOLDER"]),
            "last_activity": scalar("SELECT MAX(at) FROM activity") or None,
            "pending_total": sum(pending.values()),
        }

        totals = {
            "users": scalar("SELECT COUNT(*) FROM users"),
            "lessons": scalar("SELECT COUNT(*) FROM lessons"),
            "quizzes": scalar("SELECT COUNT(*) FROM quizzes"),
            "results": scalar("SELECT COUNT(*) FROM quiz_results"),
        }

        return render_template(
            "admin/reports.html", accounts=accounts, by_subject=by_subject,
            by_grade=by_grade, popular=popular, quizzes=quizzes,
            pending=pending, status=status, totals=totals,
        )

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

    # Teachers can clear one attempt so a pupil can sit the quiz again.
    # Results are otherwise locked (FR 3.3), so this is the only way back.
    @app.route("/teacher/results/<int:result_id>/reset", methods=["POST"])
    @login_required("teacher")
    def result_reset(result_id):
        db = store.get_db()
        row = db.execute(
            "SELECT r.*, u.full_name, q.title, q.teacher_id FROM quiz_results r"
            " JOIN users u ON u.id = r.student_id"
            " JOIN quizzes q ON q.id = r.quiz_id WHERE r.id = ?", (result_id,)
        ).fetchone()
        if row is None:
            abort(404)
        if row["teacher_id"] != g.user["id"]:
            abort(403)  # same rule as lessons: only your own content

        with db:
            db.execute("DELETE FROM quiz_results WHERE id = ?", (result_id,))
            # Drop the matching submission so the pupil's own progress page and
            # the hub's activity log agree with each other.
            db.execute(
                "DELETE FROM activity WHERE student_id = ? AND quiz_id = ? AND kind = 'submit_quiz'",
                (row["student_id"], row["quiz_id"]),
            )
            store.log_event(db, g.user["id"], "reset_quiz_result",
                            f"{row['full_name']} on {row['title']}")
        flash(f"{row['full_name']} can take {row['title']} again.", "ok")
        return redirect(url_for("teacher_progress"))

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

    # ------------------------------------------------------- offline support
    @app.route("/sw.js")
    def service_worker():
        """Served from the root so the worker's scope covers the whole site.
        A worker living under /static/ could only control /static/."""
        response = send_from_directory(
            os.path.join(app.static_folder, "js"), "sw.js", mimetype="text/javascript"
        )
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    @app.route("/offline-shell")
    def offline_shell():
        """The page the worker falls back to when the hub is unreachable.
        Renders no user data — shell.js rebuilds the screen from IndexedDB."""
        config = json.dumps({
            "strings": STRINGS,
            "subjects": SUBJECTS,
            "grades": GRADES,
        })
        response = app.make_response(render_template("offline_shell.html", config_json=config))
        response.headers["Cache-Control"] = "no-cache"
        return response

    @app.route("/api/ping")
    def api_ping():
        """Cheap reachability check. The browser's navigator.onLine only proves
        a link exists, not that this hub answers."""
        return jsonify({"ok": True, "time": store.now()})

    @app.route("/api/bootstrap")
    def api_bootstrap():
        """Everything the signed-in user needs to work with no network."""
        if g.user is None:
            return jsonify({"error": "signed out"}), 401
        db = store.get_db()
        uid, role = g.user["id"], g.user["role"]

        lessons = db.execute(
            "SELECT l.*, u.full_name AS teacher FROM lessons l"
            " JOIN users u ON u.id = l.teacher_id ORDER BY l.subject, l.title"
        ).fetchall()
        quizzes = db.execute("SELECT * FROM quizzes").fetchall()

        # The answer key travels to the device on purpose: FR 3.3 requires a
        # quiz to be marked instantly with no connection, which is only
        # possible if the device holds the correct answers.
        questions = db.execute("SELECT * FROM questions ORDER BY quiz_id, position").fetchall()

        if role == "teacher":
            results = db.execute(
                "SELECT r.* FROM quiz_results r JOIN quizzes q ON q.id = r.quiz_id"
                " WHERE q.teacher_id = ?", (uid,)
            ).fetchall()
            opened = 0
        else:
            results = db.execute("SELECT * FROM quiz_results WHERE student_id = ?", (uid,)).fetchall()
            opened = db.execute(
                "SELECT COUNT(DISTINCT lesson_id) FROM activity"
                " WHERE student_id = ? AND kind = 'view_lesson'", (uid,)
            ).fetchone()[0]

        return jsonify({
            "user": {
                "id": uid, "username": g.user["username"], "full_name": g.user["full_name"],
                "role": role, "grade": g.user["grade"], "language": g.user["language"],
            },
            "lessons": [dict(r) for r in lessons],
            "quizzes": [dict(r) for r in quizzes],
            "questions": [dict(r) for r in questions],
            "results": [dict(r) for r in results],
            "counts": {"lessons_opened": opened},
            "server_time": store.now(),
        })

    def _sync_quiz_result(db, uid, payload):
        """Replay one offline quiz submission. Idempotent on client_uuid, and
        it never overwrites a result the hub already locked in."""
        uuid = payload.get("client_uuid")
        quiz_id = payload.get("quiz_id")
        if not uuid or not quiz_id:
            return "failed", "missing client_uuid or quiz_id"

        if db.execute("SELECT 1 FROM quiz_results WHERE client_uuid = ?", (uuid,)).fetchone():
            return "duplicate", None
        # FR 3.3: one locked result per student per quiz. If the hub already has
        # one, the offline attempt loses — but the student's copy is kept on the
        # device, so nothing is silently destroyed.
        if db.execute(
            "SELECT 1 FROM quiz_results WHERE quiz_id = ? AND student_id = ?", (quiz_id, uid)
        ).fetchone():
            return "duplicate", None

        quiz = db.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
        if quiz is None:
            return "failed", "that quiz no longer exists on the hub"

        # Re-mark on the hub rather than trusting a score sent by the browser.
        questions = db.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)
        ).fetchall()
        answers = payload.get("answers") or {}
        score = sum(1 for qn in questions if answers.get(str(qn["id"])) == qn["correct"])

        db.execute(
            "INSERT INTO quiz_results (quiz_id, student_id, score, total, answers, submitted_at, client_uuid)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (quiz_id, uid, score, len(questions), json.dumps(answers),
             payload.get("submitted_at") or store.now(), uuid),
        )
        db.execute(
            "INSERT INTO activity (student_id, kind, quiz_id, lesson_id, at, client_uuid)"
            " VALUES (?, 'submit_quiz', ?, ?, ?, ?)",
            (uid, quiz_id, quiz["lesson_id"], payload.get("submitted_at") or store.now(), uuid + "-act"),
        )
        return "applied", None

    def _sync_lesson(db, uid, op, payload):
        """Replay a lesson a teacher wrote, edited or removed with no network.

        Offline lessons are notes only — an attachment needs the upload route,
        which the interface says plainly rather than failing here."""
        uuid = payload.get("client_uuid")
        if op == "create":
            if not uuid:
                return "failed", "missing client_uuid"
            if db.execute("SELECT 1 FROM lessons WHERE client_uuid = ?", (uuid,)).fetchone():
                return "duplicate", None
            title = (payload.get("title") or "").strip()
            subject, grade = payload.get("subject"), payload.get("grade")
            body = (payload.get("body") or "").strip()
            if not title:
                return "failed", "a lesson needs a title"
            if subject not in SUBJECTS or grade not in GRADES:
                return "failed", "unknown subject or grade"
            if not body:
                return "failed", "a lesson written offline needs notes"
            ts = payload.get("updated_at") or store.now()
            db.execute(
                "INSERT INTO lessons (teacher_id, title, subject, grade, body, created_at, updated_at, client_uuid)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, title, subject, grade, body, ts, ts, uuid),
            )
            store.log_event(db, uid, "upload_lesson", f"{title} (offline)")
            return "applied", None

        lesson_id = payload.get("id")
        if not lesson_id:
            return "failed", "missing lesson id"
        owned = db.execute(
            "SELECT * FROM lessons WHERE id = ? AND teacher_id = ?", (lesson_id, uid)
        ).fetchone()
        if owned is None:
            # Either it was removed on the hub meanwhile, or it is not theirs.
            # Reported as a duplicate for a delete, since the end state matches.
            if op == "delete":
                return "duplicate", None
            return "failed", "that lesson is no longer yours to edit"

        if op == "delete":
            db.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            store.log_event(db, uid, "delete_lesson", owned["title"])
            return "applied", None

        if op == "update":
            title = (payload.get("title") or "").strip()
            subject, grade = payload.get("subject"), payload.get("grade")
            body = (payload.get("body") or "").strip()
            if not title:
                return "failed", "a lesson needs a title"
            if subject not in SUBJECTS or grade not in GRADES:
                return "failed", "unknown subject or grade"
            if not body and not owned["file_name"]:
                return "failed", "a lesson needs notes or an attachment"
            db.execute(
                "UPDATE lessons SET title=?, subject=?, grade=?, body=?, updated_at=?,"
                " sync_status='PENDING' WHERE id=?",
                (title, subject, grade, body, payload.get("updated_at") or store.now(), lesson_id),
            )
            store.log_event(db, uid, "edit_lesson", title)
            return "applied", None

        return "failed", f"unknown operation {op!r}"

    def _sync_activity(db, uid, payload):
        uuid = payload.get("client_uuid")
        if not uuid:
            return "failed", "missing client_uuid"
        if db.execute("SELECT 1 FROM activity WHERE client_uuid = ?", (uuid,)).fetchone():
            return "duplicate", None
        kind = payload.get("kind")
        if kind not in ("view_lesson", "submit_quiz"):
            return "failed", "unknown activity kind"
        db.execute(
            "INSERT INTO activity (student_id, kind, lesson_id, quiz_id, at, client_uuid)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (uid, kind, payload.get("lesson_id"), payload.get("quiz_id"),
             payload.get("at") or store.now(), uuid),
        )
        return "applied", None

    @app.route("/api/sync", methods=["POST"])
    def api_sync():
        """Replay the device's outbox. Each item is reported on separately so a
        single bad record cannot block the rest, and the device only clears an
        item this hub has confirmed."""
        if g.user is None:
            return jsonify({"error": "signed out"}), 401

        body = request.get_json(silent=True) or {}
        items = body.get("items") or []
        if not isinstance(items, list):
            return jsonify({"error": "items must be a list"}), 400

        db = store.get_db()
        uid = g.user["id"]
        out = []

        for item in items[:200]:
            uuid = item.get("uuid")
            entity = item.get("entity")
            payload = item.get("payload") or {}
            try:
                with db:  # each item commits on its own
                    if entity == "quiz_result":
                        status, error = _sync_quiz_result(db, uid, payload)
                    elif entity == "activity":
                        status, error = _sync_activity(db, uid, payload)
                    elif entity == "lesson":
                        if g.user["role"] != "teacher":
                            status, error = "failed", "only teachers can change lessons"
                        else:
                            status, error = _sync_lesson(db, uid, item.get("op"), payload)
                    else:
                        status, error = "failed", f"unknown entity {entity!r}"
            except Exception as exc:                      # noqa: BLE001 — reported per item
                status, error = "failed", str(exc)
            out.append({"uuid": uuid, "status": status, "error": error})

        return jsonify({"results": out, "server_time": store.now()})

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, message="You don't have access to that page."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="That page doesn't exist."), 404
