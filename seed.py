"""Load demo accounts and sample content into the Local Hub.

Run once:  python seed.py
Demo logins (change these before any real pilot):
    admin   / admin123
    teacher / teach123
    student / 1234   (PIN, grade P6)
"""
from werkzeug.security import generate_password_hash

from edureach import create_app
from edureach import db as store

USERS = [
    ("admin", "admin123", "Hub Administrator", "admin", None, "en"),
    ("teacher", "teach123", "Mukamana Claudine", "teacher", None, "en"),
    ("student", "1234", "Ishimwe Eric", "student", "P6", "en"),
    ("aline", "5678", "Uwase Aline", "student", "P6", "rw"),
]

LESSONS = [
    ("Fractions: adding and subtracting", "Mathematics", "P6",
     "A fraction shows part of a whole. The top number is the numerator and the bottom number is the denominator.\n\n"
     "To add fractions with the same denominator, add the numerators and keep the denominator:\n"
     "   2/7 + 3/7 = 5/7\n\n"
     "If the denominators are different, first find a common denominator:\n"
     "   1/2 + 1/3 = 3/6 + 2/6 = 5/6\n\n"
     "Practice: 1/4 + 2/4 = ?   3/5 - 1/5 = ?",
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
]


def main():
    app = create_app()
    with app.app_context():
        db = store.get_db()
        # Check if users table exists and has data
        try:
            user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if user_count > 0:
                print("Hub already has data; nothing to do.")
                return
        except Exception as e:
            # Table doesn't exist yet, that's fine - init_db will create it
            pass
        with db:
            ids = {}
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
        print("Demo data loaded. Logins: admin/admin123, teacher/teach123, student/1234")


if __name__ == "__main__":
    main()
