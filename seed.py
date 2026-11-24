"""Set up the Local Hub's demo content and show what is on it.

    python seed.py

Creating the app already seeds an empty hub, so this script mostly exists to
run that from the command line and print what ended up there. The content
itself lives in edureach/db.py, so there is only one copy to keep correct.

Demo logins (change these before any real pilot):
    admin   / admin123
    teacher / teach123
    student / 1234   (PIN, grade P6)
"""
from edureach import create_app
from edureach import db as store


def main():
    app = create_app()
    with app.app_context():
        db = store.get_db()
        users = db.execute("SELECT role, COUNT(*) n FROM users GROUP BY role").fetchall()
        lessons = db.execute(
            "SELECT grade, subject, title,"
            " (SELECT COUNT(*) FROM quizzes q WHERE q.lesson_id = l.id) AS quizzes"
            " FROM lessons l ORDER BY grade, subject"
        ).fetchall()

        print("Accounts on the hub:")
        for row in users:
            print(f"  {row['n']} {row['role']}")

        print(f"\nLessons on the hub ({len(lessons)}):")
        for row in lessons:
            mark = f"  quiz x{row['quizzes']}" if row["quizzes"] else "  no quiz"
            print(f"  {row['grade']:<3} {row['subject']:<15} {row['title']}{mark}")

        print("\nLogins: admin/admin123, teacher/teach123, student/1234")


if __name__ == "__main__":
    main()
