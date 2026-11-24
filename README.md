# EduReach Rwanda — Local Hub

An offline learning hub for rural schools. Teachers upload lessons and quizzes to a low-cost device at the school, and students use them over the school Wi-Fi/LAN with **no internet**. Quiz results are saved on the hub and marked `PENDING` so a later sync module can upload them to the Central Sync Server.

Built from the EduReach Rwanda SRS v1.0 (Lancelot Nshuti, ALU). This is **increment 1**: the full student journey running offline.

## 🌐 Live Demo

**Try it now**: https://edureach-rwanda.onrender.com

Demo accounts:
- **Student**: username `student`, password `1234` (P6 class)
- **Teacher**: username `teacher`, password `teach123`
- **Admin**: username `admin`, password `admin123`

The app works completely offline. Try logging in, opening a lesson, and taking a quiz!

## What works now

| SRS requirement | Status |
|---|---|
| FR 1.1 Admin creates accounts (no self sign-up) | Done |
| FR 1.2 Offline login with password or PIN | Done |
| FR 2.1 Upload lessons (notes + PDF/slides/image/video), tagged by subject & grade | Done |
| FR 2.2 Edit / remove own lessons (teachers can't touch other teachers' content) | Done |
| FR 2.3 Create quizzes with an answer key | Done |
| FR 3.1 Browse and search lessons by subject and grade | Done |
| FR 3.2 View lessons offline | Done |
| FR 3.3 Take quizzes offline with instant marking; results locked after submit | Done |
| FR 4.1 Record lesson views and quiz submissions | Done |
| FR 4.2 Student sees own quiz history and average | Done |
| FR 4.3 Teacher sees class results on their own quizzes | Done |
| FR 6.1 Admin switches accounts on/off | Done |
| FR 6.2 / 6.3 Administrator reports and hub status | Done |
| NFR 1 Works with no internet connection (installable PWA, offline shell, IndexedDB) | Done |
| NFR 3 English / Kinyarwanda toggle (student screens) | Done |
| NFR 6 Power-cut safety (SQLite WAL + synchronous=FULL, atomic file writes) | Done |
| NFR 9 Log of uploads and account changes | Done |
| Teacher writes, edits and removes lessons with no connection | Done |
| Teacher resets a pupil's quiz attempt | Done |
| FR 5 Sync with Central Sync Server | In progress |
| NFR 3 Kinyarwanda on teacher and administrator screens | In progress |

## Run it on your own machine

Nothing beyond Python is needed: no database server, no Node, no build step.

**Before you start** — Python 3.9 or newer, and Git. Check with:

```bash
python3 --version
git --version
```

If `python3` is missing: [python.org/downloads](https://www.python.org/downloads/), or
`sudo apt install python3 python3-venv` on Ubuntu or Debian.

**1. Get the code**

```bash
git clone https://github.com/nshutilancelot3/edureach-rwanda.git
cd edureach-rwanda
```

**2. Create a virtual environment and switch to it**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, the second line is `.venv\Scripts\activate` instead. Your prompt
should now start with `(.venv)`.

**3. Install the dependencies**

```bash
pip install -r requirements.txt
```

**4. Start the hub**

```bash
flask --app edureach run --host 0.0.0.0 --port 5000
```

The first start creates the database and fills it with the demo accounts and
six sample lessons, so there is no separate setup command to remember. Leave
this terminal running.

**5. Open it**

Go to **http://localhost:5000** and sign in with any of:

| Role | Username | Password |
|---|---|---|
| Student (P6) | `student` | `1234` |
| Teacher | `teacher` | `teach123` |
| Administrator | `admin` | `admin123` |

Change these before any real pilot.

Other devices on the same Wi-Fi reach the hub at `http://<hub-ip>:5000` — that
is how a classroom uses it, with the hub on the teacher's device and pupils on
tablets or phones. Find the address with `hostname -I` on Linux or `ipconfig`
on Windows.

**To stop it**, press `Ctrl+C`. To come back later, repeat steps 2, 4 and 5 —
your data is kept in `instance/`.

**Useful to know**

- `python seed.py` prints what is currently on the hub, and seeds it if empty.
- To start over from scratch, delete the `instance/` folder and start the hub again.

## Working offline

EduReach is an installable PWA. Once you have signed in with a connection
available, the device keeps working with none.

**How to check it yourself**

1. Open the app and sign in while connected. The header shows **Online**.
2. Open any lesson once so the service worker finishes installing.
3. Cut the connection — switch off Wi-Fi, or stop the server entirely.
4. Reload the page. It still opens. The header now shows **Offline**.
5. Browse lessons, filter by subject and grade, and search. Open a lesson you
   have **never** opened before — it still works.
6. Take a quiz. It is marked instantly and the score is saved on the device.
7. Close the browser completely, reopen it, still offline. Your result is there,
   and *My progress* lists it tagged `PENDING`.
8. Reconnect. The badge returns to **Online**, the pending counter falls to zero,
   and the result appears on the hub for the teacher.

**How it works**

A service worker precaches an *application shell*. When a page request cannot
reach the hub, the shell is served instead and rebuilds the screen from
IndexedDB using the same markup and CSS as the server templates. Because it
routes on the URL rather than replaying a cached response, lessons and quizzes
that were never visited still open — caching visited pages alone could not do
that, and a quiz submission is a `POST`, which can never come from a cache.

Work done offline is appended to an outbox. When the hub answers again the
outbox is replayed; each item carries a `client_uuid`, so a sync that fails
half-way is safe to retry without creating duplicates. An item is removed from
the device only after the hub confirms it, and a failed sync never deletes
local data.

Quizzes are re-marked on the hub rather than trusting the score the browser
reports. If a result already exists for that student and quiz, the hub keeps it
(FR 3.3 locks results) and reports the late submission as a duplicate.

**What still needs a connection**

- Signing in for the first time on a device, and creating accounts.
- Uploading a lesson file, creating or editing lessons and quizzes.
- A teacher's class results, which live on the hub.

Each is reported in the interface rather than failing silently.

**A note on the answer key**

Marking a quiz with no connection is only possible if the device holds the
correct answers, so the bootstrap sends them. This is inherent to the offline
requirement (FR 3.3) rather than an oversight; a determined pupil could read
them from browser storage. On the real deployment the hub is a device kept by
the teacher, which limits the exposure.

## Tests

With the virtual environment active:

```bash
pytest
```

49 tests cover login and roles, CSRF protection, account creation and switching
off, lesson upload and file-type checks, teacher ownership, quiz answer keys,
browse/search, auto-marking and result locking, progress views, the language
toggle, power-cut safety, administrator reports, resetting a pupil's attempt,
and the offline layer — service worker scope, the shell carrying no user data,
bootstrap contents, sync idempotency, locked results surviving a late sync,
lessons written offline reaching the hub without duplicating, and one bad
outbox item not blocking the rest.

## Stack

Python 3 + Flask, SQLite, server-rendered HTML with almost no JavaScript, and no web fonts or animation, so it stays light on low-power hardware. Data lives in `instance/` (database, uploaded files and secret key) and is not committed.

## Deploy it

Running at **https://edureach-rwanda.onrender.com**.

To put up your own copy on Render, which has a free tier:

1. Sign in to [render.com](https://render.com) with GitHub.
2. **New +** → **Web Service**, and pick this repository.
3. Set:
   - **Runtime** — `Python 3`
   - **Build command** — `pip install -r requirements.txt`
   - **Start command** — `waitress-serve --port=$PORT --host=0.0.0.0 --call 'edureach:create_app'`
   - **Instance type** — `Free`
4. **Create Web Service** and wait a few minutes.

The hub seeds itself on first start, so there is no database to set up. A
`Procfile` with the same start command is included for Heroku-compatible hosts.

Two things to expect on a free tier: the service sleeps after inactivity, so the
first request can take about a minute, and the disk is wiped on each deploy, so
the hub seeds itself fresh. Both are properties of free hosting rather than the
application — a real school hub keeps its disk.

## Known gaps

- Kinyarwanda strings are a first draft and need checking by a fluent speaker. Teacher and admin screens are English only for now.
- Not yet tested on a Raspberry Pi or a low-end Android tablet, or with 40 students at once (NFR 2, NFR 7).
- Production deployment uses `waitress` server; local development uses Flask dev server.
