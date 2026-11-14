# EduReach Rwanda — Local Hub

An offline learning hub for rural schools. Teachers upload lessons and quizzes to a low-cost device at the school, and students use them over the school Wi-Fi/LAN with **no internet**. Quiz results are saved on the hub and marked `PENDING` so a later sync module can upload them to the Central Sync Server.

Built from the EduReach Rwanda SRS v1.0 (Lancelot Nshuti, ALU). This is **increment 1**: the full student journey running offline.

## What works now

| SRS requirement | Status |
|---|---|
| FR 1.1 Admin creates accounts (no self sign-up) | ✅ |
| FR 1.2 Offline login with password or PIN | ✅ |
| FR 2.1 Upload lessons (notes + PDF/slides/image/video), tagged by subject & grade | ✅ |
| FR 2.2 Edit / remove own lessons (teachers can't touch other teachers' content) | ✅ |
| FR 2.3 Create quizzes with an answer key | ✅ |
| FR 3.1 Browse and search lessons by subject and grade | ✅ |
| FR 3.2 View lessons offline | ✅ |
| FR 3.3 Take quizzes offline with instant marking; results locked after submit | ✅ |
| FR 4.1 Record lesson views and quiz submissions | ✅ |
| FR 4.2 Student sees own quiz history and average | ✅ |
| FR 4.3 Teacher sees class results on their own quizzes | ✅ |
| FR 6.1 Admin switches accounts on/off | ✅ |
| NFR 3 English / Kinyarwanda toggle (student screens) | ✅ partial |
| NFR 6 Power-cut safety (SQLite WAL + synchronous=FULL, atomic file writes) | ✅ |
| NFR 9 Log of uploads and account changes | ✅ |
| FR 5 Sync with Central Sync Server | ⏳ next increment |
| FR 6.2 / 6.3 Reports and hub status | ⏳ |
| Teacher resets a quiz attempt | ⏳ |

## Run it

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                                       # demo accounts + sample lessons
flask --app edureach run --host 0.0.0.0 --port 5000
```

Open http://localhost:5000. Other devices on the same Wi-Fi use `http://<hub-ip>:5000`.

Demo logins: `admin / admin123`, `teacher / teach123`, `student / 1234` (P6). Change these before a real pilot.

## Tests

```bash
pytest
```

20 tests cover login and roles, CSRF protection, account creation and switching off, lesson upload and file-type checks, teacher ownership, quiz answer keys, browse/search, auto-marking and result locking, progress views, the language toggle, and power-cut safety.

## Stack

Python 3 + Flask, SQLite, server-rendered HTML with almost no JavaScript, and no web fonts or animation, so it stays light on low-power hardware. Data lives in `instance/` (database, uploaded files and secret key) and is not committed.

## Known gaps

- Kinyarwanda strings are a first draft and need checking by a fluent speaker. Teacher and admin screens are English only for now.
- Not yet tested on a Raspberry Pi or a low-end Android tablet, or with 40 students at once (NFR 2, NFR 7).
- Use a production server (e.g. `waitress`) instead of `flask run` on the real hub.
