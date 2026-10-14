# ADHD HQ

ADHD HQ is a local desktop planner for school assignments, weekly sprints, daily work, goals, and project timelines. It keeps the existing School and Projects work areas together without requiring a hosted service or an account.

![Sprint planning and Gantt timeline](docs/screenshots/gantt.jpg)

## What it does

- Track assignments with priorities, due dates, notes, and status changes.
- Plan weekly sprints and assign work to individual days, including past days.
- View scheduled work and deadlines in a calendar with month navigation.
- Track numeric goals and monthly roadmap milestones.
- Create Gantt milestones, move or resize them, and attach tasks to them.

The Gantt chart uses whole calendar days and includes the final day. Its range starts at a month boundary, covers at least six months, and expands to include existing milestones. Small windows get a horizontally scrollable timeline. The edit form provides exact dates and a keyboard-accessible alternative to dragging.

## Run the desktop app

The Windows package contains `ADHD HQ.exe` and an `_internal` folder. Keep both together and open the executable. Python is included in the package. Windows needs the Microsoft Edge WebView2 Runtime.

This build is an unsigned portable application. It has been built and launched on Windows x64; it has not been tested on a fresh Windows installation, macOS, or Linux. It does not include an installer or automatic updates.

## Develop locally

Use Python 3.12 on Windows for the tested build environment. In PowerShell, from this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe desktop.py
```

To use a browser during development:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8844
```

Open `http://127.0.0.1:8844`. This is a personal local application. Keep the server bound to loopback; it has no multi-user login system.

## Data and backups

On Windows, the SQLite database lives at `%LOCALAPPDATA%\ADHD HQ\taskhq.db`, outside the application and source folders. Desktop errors are recorded in `desktop.log` in the same folder. Closing the window shuts down its server. Each launch reserves an available loopback port, so an occupied fixed port does not prevent startup.

Set `ADHD_HQ_DATA_DIR` to use a different data directory. A new installation starts empty. For the small built-in sample dataset, set `ADHD_HQ_DEMO=1` before starting the app.

Close the app before copying the database for a backup. To bring an older database across, choose a new destination and run:

```powershell
.\.venv\Scripts\python.exe import_database.py "C:\path\to\old\taskhq.db" --destination "C:\path\to\new-data\taskhq.db"
$env:ADHD_HQ_DATA_DIR = "C:\path\to\new-data"
.\.venv\Scripts\python.exe desktop.py
```

The import tool checks the source and refuses to replace an existing destination. The app adds missing planning columns when it starts. Original databases are not included in the repository or desktop package.

## Architecture and data flow

| Component | Responsibility |
| --- | --- |
| `desktop.py` | Native pywebview window, loopback server lifecycle, startup checks, rotating log |
| `app.py` | FastAPI routes, form validation, calendar and sprint calculations, template rendering |
| `db.py` | SQLite schema, migrations, parameterized queries, task and milestone storage |
| `config.json` | Work areas, subcategories, priorities, and statuses |
| `templates/` | Jinja pages for the dashboard, assignments, sprints, calendar, and goals |
| `static/js/app.js` | Form feedback, save controls, and subcategory selection |
| `static/js/gantt.js` | Timeline layout, whole-day date calculations, drag persistence, failure recovery |
| `static/css/style.css` | Shared styling and responsive layouts |

A form goes to a FastAPI route, which validates it and writes through `db.py`. The response sends the browser to the relevant page. Gantt changes save through the same routes and revert visually if saving fails. SQLite connections close after each operation; task edits and status changes preserve sprint, agenda, effort, and Gantt links.

## Tests and Windows build

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests/gantt.test.cjs
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm ADHD_HQ.spec
```

The output is `dist\ADHD HQ\ADHD HQ.exe`. The spec includes templates, static assets, and the shared configuration; it excludes personal databases. `requirements-build.lock.txt` records the exact environment used for the verified Windows build.

The regression suite covers page rendering, task planning links, input validation, calendar behavior, database setup, and timeline calculations. Browser checks cover form saves and Gantt interaction. A native launch check verifies the packaged window separately. Email, cloud sync, and external API services are not part of this application.

Packaging follows the [pywebview freezing guide](https://pywebview.flowrl.com/guide/freezing) and [PyInstaller spec documentation](https://pyinstaller.org/en/latest/spec-files.html).

## Publication

The current source excludes databases, caches, build output, and local tool files. Older Git history contains a previously tracked database. Review and remove that historical copy before making the existing repository public; deleting it from the current tree does not remove it from history. No repository visibility or history changes are part of this source update.
