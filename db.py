import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(
    os.environ.get(
        "ADHD_HQ_DATA_DIR",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        / "ADHD HQ",
    )
)
DB_PATH = DATA_DIR / "taskhq.db"
UNSET = object()


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    with conn() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            pillar TEXT NOT NULL DEFAULT 'School',
            subcategory TEXT NOT NULL DEFAULT 'Assignments',
            priority TEXT NOT NULL DEFAULT 'Medium',
            status TEXT NOT NULL DEFAULT 'Not Started',
            due_date TEXT DEFAULT NULL,
            due_time TEXT DEFAULT NULL,
            sprint_id INTEGER DEFAULT NULL,
            agenda_date TEXT DEFAULT NULL,
            effort_points INTEGER NOT NULL DEFAULT 1,
            notes TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT NULL
        );
        """)

        # Sprint table (weekly sprint planning)
        db.execute("""
        CREATE TABLE IF NOT EXISTS sprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            focus TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Roadmap items (high-level milestones, especially Projects)
        db.execute("""
        CREATE TABLE IF NOT EXISTS roadmap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pillar TEXT NOT NULL DEFAULT 'Projects',
            month TEXT NOT NULL, -- YYYY-MM
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Not Started',
            notes TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        db.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            pillar TEXT NOT NULL DEFAULT 'Projects',
            target_value INTEGER NOT NULL DEFAULT 100,
            current_value INTEGER NOT NULL DEFAULT 0,
            due_date TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # Gantt timeline bars (Projects)
        db.execute("""
        CREATE TABLE IF NOT EXISTS gantt_bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#1f77b4',
            status TEXT NOT NULL DEFAULT 'Not Started',
            notes TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        columns = {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}
        for name, declaration in {
            "sprint_id": "INTEGER DEFAULT NULL",
            "agenda_date": "TEXT DEFAULT NULL",
            "effort_points": "INTEGER NOT NULL DEFAULT 1",
            "gantt_id": "INTEGER DEFAULT NULL",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {declaration}")
        db.execute("CREATE INDEX IF NOT EXISTS tasks_sprint ON tasks(sprint_id)")
        db.execute("CREATE INDEX IF NOT EXISTS tasks_agenda ON tasks(agenda_date)")
        db.execute("CREATE INDEX IF NOT EXISTS tasks_gantt ON tasks(gantt_id)")
        db.commit()


def _row_to_dict(r):
    return dict(r) if r is not None else None


def seed_if_empty():
    with conn() as db:
        n = db.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        if n == 0:
            db.execute(
                "INSERT INTO tasks(title,pillar,subcategory,priority,status,notes) VALUES (?,?,?,?,?,?)",
                (
                    "Write a practice summary",
                    "School",
                    "Discussions",
                    "High",
                    "In Progress",
                    "Fictional example task.",
                ),
            )
            db.execute(
                "INSERT INTO tasks(title,pillar,subcategory,priority,status,notes) VALUES (?,?,?,?,?,?)",
                (
                    "Sketch an example page",
                    "Projects",
                    "UI/Frontend",
                    "High",
                    "Not Started",
                    "Fictional example task.",
                ),
            )
            db.execute(
                "INSERT INTO goals(title,pillar,target_value,current_value) VALUES (?,?,?,?)",
                ("Example project progress", "Projects", 100, 35),
            )
            db.commit()


def list_tasks(where_sql="", params=()):
    q = "SELECT * FROM tasks"
    if where_sql:
        q += " WHERE " + where_sql
    q += (
        " ORDER BY COALESCE(due_date,'9999-12-31'), COALESCE(due_time,'23:59'), id DESC"
    )
    with conn() as db:
        return db.execute(q, params).fetchall()


def get_task(task_id: int):
    with conn() as db:
        return db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()


def add_task(
    title,
    pillar,
    subcategory,
    priority,
    status,
    due_date,
    due_time,
    notes,
    sprint_id=None,
    agenda_date=None,
    effort_points=1,
    gantt_id=None,
):
    with conn() as db:
        cur = db.execute(
            """INSERT INTO tasks(
                title,pillar,subcategory,priority,status,
                due_date,due_time,
                sprint_id,agenda_date,effort_points,gantt_id,
                notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                title,
                pillar,
                subcategory,
                priority,
                status,
                due_date or None,
                due_time or None,
                sprint_id,
                agenda_date,
                int(effort_points or 1),
                gantt_id,
                notes or None,
            ),
        )
        db.commit()
        return cur.lastrowid


def update_task(
    task_id,
    title,
    pillar,
    subcategory,
    priority,
    status,
    due_date,
    due_time,
    notes,
    sprint_id=UNSET,
    agenda_date=UNSET,
    effort_points=UNSET,
    gantt_id=UNSET,
):
    existing = get_task(task_id)
    if existing is None:
        raise ValueError("This task no longer exists. Refresh the page and try again.")
    sprint_id = existing["sprint_id"] if sprint_id is UNSET else sprint_id
    agenda_date = existing["agenda_date"] if agenda_date is UNSET else agenda_date
    effort_points = (
        existing["effort_points"] if effort_points is UNSET else effort_points
    )
    gantt_id = existing["gantt_id"] if gantt_id is UNSET else gantt_id
    with conn() as db:
        db.execute(
            """UPDATE tasks SET
                title=?, pillar=?, subcategory=?, priority=?, status=?,
                due_date=?, due_time=?,
                sprint_id=?, agenda_date=?, effort_points=?, gantt_id=?,
                notes=?,
                updated_at=datetime('now')
                WHERE id=?""",
            (
                title,
                pillar,
                subcategory,
                priority,
                status,
                due_date or None,
                due_time or None,
                sprint_id,
                agenda_date or None,
                int(effort_points or 1),
                gantt_id,
                notes or None,
                task_id,
            ),
        )
        db.commit()


def set_task_sprint(task_id: int, sprint_id: int | None):
    with conn() as db:
        db.execute(
            "UPDATE tasks SET sprint_id=?, updated_at=datetime('now') WHERE id=?",
            (sprint_id, task_id),
        )
        db.commit()


def set_task_agenda_date(task_id: int, agenda_date: str | None):
    with conn() as db:
        db.execute(
            "UPDATE tasks SET agenda_date=?, updated_at=datetime('now') WHERE id=?",
            (agenda_date, task_id),
        )
        db.commit()


def list_tasks_for_sprint(sprint_id: int, pillar: str = ""):
    q = "SELECT * FROM tasks WHERE sprint_id=?"
    params = [sprint_id]
    if pillar:
        q += " AND pillar=?"
        params.append(pillar)
    q += " ORDER BY status, priority, id DESC"
    with conn() as db:
        return db.execute(q, tuple(params)).fetchall()


def list_tasks_for_agenda(agenda_date: str):
    with conn() as db:
        return db.execute(
            "SELECT * FROM tasks WHERE agenda_date=? ORDER BY COALESCE(due_time,'23:59'), id DESC",
            (agenda_date,),
        ).fetchall()


def update_task_planning(
    task_id: int, sprint_id=None, agenda_date=None, effort_points: int = 1
):
    with conn() as db:
        db.execute(
            "UPDATE tasks SET sprint_id=?, agenda_date=?, effort_points=?, updated_at=datetime('now') WHERE id=?",
            (sprint_id, agenda_date or None, int(effort_points), task_id),
        )
        db.commit()


def list_sprints():
    with conn() as db:
        return db.execute(
            "SELECT * FROM sprints ORDER BY start_date DESC, id DESC"
        ).fetchall()


def get_sprint(sprint_id: int):
    with conn() as db:
        return db.execute("SELECT * FROM sprints WHERE id=?", (sprint_id,)).fetchone()


def create_sprint(name: str, start_date: str, end_date: str, focus: str = ""):
    with conn() as db:
        db.execute(
            "INSERT INTO sprints(name,start_date,end_date,focus) VALUES (?,?,?,?)",
            (name, start_date, end_date, focus or None),
        )
        db.commit()


def get_current_sprint(today_iso: str):
    with conn() as db:
        return db.execute(
            "SELECT * FROM sprints WHERE start_date<=? AND end_date>=? ORDER BY start_date DESC LIMIT 1",
            (today_iso, today_iso),
        ).fetchone()


def list_roadmap(month: str = "", pillar: str = ""):
    where = []
    params = []
    if month:
        where.append("month=?")
        params.append(month)
    if pillar:
        where.append("pillar=?")
        params.append(pillar)
    q = "SELECT * FROM roadmap"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY month DESC, id DESC"
    with conn() as db:
        return db.execute(q, tuple(params)).fetchall()


def add_roadmap(
    pillar: str, month: str, title: str, status: str = "Not Started", notes: str = ""
):
    with conn() as db:
        db.execute(
            "INSERT INTO roadmap(pillar,month,title,status,notes) VALUES (?,?,?,?,?)",
            (pillar, month, title, status, notes or None),
        )
        db.commit()


def update_roadmap(
    item_id: int, pillar: str, month: str, title: str, status: str, notes: str = ""
):
    with conn() as db:
        db.execute(
            "UPDATE roadmap SET pillar=?, month=?, title=?, status=?, notes=? WHERE id=?",
            (pillar, month, title, status, notes or None, item_id),
        )
        db.commit()


def delete_roadmap(item_id: int):
    with conn() as db:
        db.execute("DELETE FROM roadmap WHERE id=?", (item_id,))
        db.commit()


# ===== GANTT TIMELINE STORAGE =====


def list_gantt_bars():
    with conn() as db:
        return db.execute(
            "SELECT * FROM gantt_bars ORDER BY start_date ASC, id DESC"
        ).fetchall()


def get_gantt_bar(bar_id: int):
    with conn() as db:
        return db.execute("SELECT * FROM gantt_bars WHERE id=?", (bar_id,)).fetchone()


def add_gantt_bar(
    title: str,
    start_date: str,
    end_date: str,
    color: str = "#1f77b4",
    status: str = "Not Started",
    notes: str = "",
):
    with conn() as db:
        cur = db.execute(
            """INSERT INTO gantt_bars(title,start_date,end_date,color,status,notes) VALUES (?,?,?,?,?,?)""",
            (title, start_date, end_date, color, status, notes or None),
        )
        db.commit()
        return cur.lastrowid


def update_gantt_bar(
    bar_id: int,
    title: str,
    start_date: str,
    end_date: str,
    color: str = "#1f77b4",
    status: str = "Not Started",
    notes: str = "",
):
    with conn() as db:
        db.execute(
            """UPDATE gantt_bars SET title=?, start_date=?, end_date=?, color=?, status=?, notes=? WHERE id=?""",
            (title, start_date, end_date, color, status, notes or None, bar_id),
        )
        db.commit()


def delete_gantt_bar(bar_id: int):
    with conn() as db:
        db.execute("UPDATE tasks SET gantt_id=NULL WHERE gantt_id=?", (bar_id,))
        db.execute("DELETE FROM gantt_bars WHERE id=?", (bar_id,))
        db.commit()


def list_tasks_for_gantt(bar_id: int):
    with conn() as db:
        return db.execute(
            "SELECT * FROM tasks WHERE gantt_id=? ORDER BY COALESCE(due_date,'9999-12-31'), COALESCE(due_time,'23:59'), id DESC",
            (bar_id,),
        ).fetchall()


def update_task_gantt(task_id: int, gantt_id: int | None):
    with conn() as db:
        db.execute(
            "UPDATE tasks SET gantt_id=?, updated_at=datetime('now') WHERE id=?",
            (gantt_id, task_id),
        )
        db.commit()


def delete_task(task_id: int):
    with conn() as db:
        db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        db.commit()


def toggle_complete(task_id: int):
    t = get_task(task_id)
    if not t:
        return
    new_status = "Completed" if t["status"] != "Completed" else "In Progress"
    update_task(
        task_id=task_id,
        title=t["title"],
        pillar=t["pillar"],
        subcategory=t["subcategory"],
        priority=t["priority"],
        status=new_status,
        due_date=t["due_date"],
        due_time=t["due_time"],
        notes=t["notes"],
        sprint_id=t["sprint_id"],
        agenda_date=t["agenda_date"],
        effort_points=t["effort_points"],
        gantt_id=t["gantt_id"],
    )


def cycle_status(task_id: int):
    t = get_task(task_id)
    if not t:
        return

    # Cycle: Not Started -> In Progress -> Completed -> Not Started
    order = ["Not Started", "In Progress", "Completed"]
    cur = t["status"] or "Not Started"

    try:
        idx = order.index(cur)
    except ValueError:
        idx = 0

    new_status = order[(idx + 1) % len(order)]

    update_task(
        task_id=task_id,
        title=t["title"],
        pillar=t["pillar"],
        subcategory=t["subcategory"],
        priority=t["priority"],
        status=new_status,
        due_date=t["due_date"],
        due_time=t["due_time"],
        notes=t["notes"],
        sprint_id=t["sprint_id"],
        agenda_date=t["agenda_date"],
        effort_points=t["effort_points"],
        gantt_id=t["gantt_id"],
    )


def list_goals():
    with conn() as db:
        return db.execute("SELECT * FROM goals ORDER BY id DESC").fetchall()


def add_goal(
    title: str, pillar: str, target_value: int, current_value: int, due_date: str = ""
):
    with conn() as db:
        db.execute(
            "INSERT INTO goals(title,pillar,target_value,current_value,due_date) VALUES (?,?,?,?,?)",
            (title, pillar, int(target_value), int(current_value), due_date or None),
        )
        db.commit()


def update_goal(
    goal_id: int,
    title: str,
    pillar: str,
    target_value: int,
    current_value: int,
    due_date: str = "",
):
    with conn() as db:
        db.execute(
            "UPDATE goals SET title=?, pillar=?, target_value=?, current_value=?, due_date=? WHERE id=?",
            (
                title,
                pillar,
                int(target_value),
                int(current_value),
                due_date or None,
                goal_id,
            ),
        )
        db.commit()


def delete_goal(goal_id: int):
    with conn() as db:
        db.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        db.commit()
