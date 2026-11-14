"""English and Kinyarwanda interface text (NFR 3).

The Kinyarwanda strings are a first draft and need review by a fluent
speaker before the pilot.
"""

STRINGS = {
    "app_name": {"en": "EduReach Rwanda", "rw": "EduReach Rwanda"},
    "tagline": {"en": "Learning that works without internet", "rw": "Kwiga bidasaba interineti"},
    "username": {"en": "Username", "rw": "Izina ukoresha"},
    "password": {"en": "Password or PIN", "rw": "Ijambo ry'ibanga cyangwa PIN"},
    "login": {"en": "Log in", "rw": "Injira"},
    "logout": {"en": "Log out", "rw": "Sohoka"},
    "login_failed": {"en": "Wrong username or password.", "rw": "Izina cyangwa ijambo ry'ibanga si byo."},
    "account_off": {"en": "This account is switched off. Ask your administrator.", "rw": "Iyi konti yarahagaritswe. Baza umuyobozi."},
    "hello": {"en": "Hello", "rw": "Muraho"},
    "lessons": {"en": "Lessons", "rw": "Amasomo"},
    "my_progress": {"en": "My progress", "rw": "Aho ngeze"},
    "subject": {"en": "Subject", "rw": "Isomo"},
    "grade": {"en": "Grade", "rw": "Umwaka"},
    "all": {"en": "All", "rw": "Byose"},
    "search": {"en": "Search", "rw": "Shakisha"},
    "open": {"en": "Open", "rw": "Fungura"},
    "back": {"en": "Back", "rw": "Subira inyuma"},
    "no_lessons": {"en": "No lessons found.", "rw": "Nta masomo abonetse."},
    "take_quiz": {"en": "Take quiz", "rw": "Kora isuzuma"},
    "quiz_done": {"en": "Done", "rw": "Warakoze"},
    "submit": {"en": "Submit answers", "rw": "Ohereza ibisubizo"},
    "your_score": {"en": "Your score", "rw": "Amanota yawe"},
    "answer_all": {"en": "Please answer every question.", "rw": "Subiza ibibazo byose."},
    "already_taken": {"en": "You already took this quiz. Ask your teacher if you need to retake it.", "rw": "Wamaze gukora iri suzuma. Baza mwarimu niba ukeneye kongera."},
    "correct": {"en": "Correct", "rw": "Ni byo"},
    "wrong": {"en": "Not correct", "rw": "Si byo"},
    "right_answer": {"en": "Right answer", "rw": "Igisubizo nyacyo"},
    "quiz_history": {"en": "Quiz history", "rw": "Amasuzuma nakoze"},
    "lessons_opened": {"en": "Lessons opened", "rw": "Amasomo nafunguye"},
    "quizzes_taken": {"en": "Quizzes taken", "rw": "Amasuzuma nakoze"},
    "average": {"en": "Average score", "rw": "Impuzandengo"},
    "no_results": {"en": "No quizzes taken yet.", "rw": "Nta suzuma urakora."},
    "date": {"en": "Date", "rw": "Itariki"},
    "score": {"en": "Score", "rw": "Amanota"},
    "attachment": {"en": "Attached file", "rw": "Dosiye yometseho"},
    "language": {"en": "Kinyarwanda", "rw": "English"},
}

SUPPORTED = ("en", "rw")


def translate(key, lang):
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry["en"]
