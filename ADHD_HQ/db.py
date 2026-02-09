import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "taskhq.db"

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

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

        # Hosting properties (AirBnB properties management)
        db.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT DEFAULT NULL,
            listing_url TEXT DEFAULT NULL,
            nightly_price REAL DEFAULT 0.0,
            commission_rate REAL DEFAULT 0.03,
            status TEXT NOT NULL DEFAULT 'Active',
            notes TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT NULL
        );
        """)

        # Hosting tasks/events (daily to-dos for cohost management)
        db.execute("""
        CREATE TABLE IF NOT EXISTS hosting_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT NULL,
            status TEXT NOT NULL DEFAULT 'Not Started',
            due_date TEXT DEFAULT NULL,
            priority TEXT NOT NULL DEFAULT 'Medium',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT NULL,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        );
        """)

        # Lightweight migration for older DBs: add new columns if missing.
        # SQLite doesn't support IF NOT EXISTS for ALTER TABLE ADD COLUMN.
        def _add_col(sql: str):
            try:
                db.execute(sql)
            except Exception:
                pass

        _add_col("ALTER TABLE tasks ADD COLUMN sprint_id INTEGER DEFAULT NULL")
        _add_col("ALTER TABLE tasks ADD COLUMN agenda_date TEXT DEFAULT NULL")
        _add_col("ALTER TABLE tasks ADD COLUMN effort_points INTEGER NOT NULL DEFAULT 1")
        db.commit()

def _row_to_dict(r):
    return dict(r) if r is not None else None

def seed_if_empty():
    with conn() as db:
        n = db.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        if n == 0:
            db.execute(
                "INSERT INTO tasks(title,pillar,subcategory,priority,status,notes) VALUES (?,?,?,?,?,?)",
                ("Write a practice summary", "School", "Discussions", "High", "In Progress", "Fictional example task."),
            )
            db.execute(
                "INSERT INTO tasks(title,pillar,subcategory,priority,status,notes) VALUES (?,?,?,?,?,?)",
                ("Example planning item", "Airbnb", "Guest Messaging", "High", "Not Started", ""),
            )
            db.execute(
                "INSERT INTO tasks(title,pillar,subcategory,priority,status,notes) VALUES (?,?,?,?,?,?)",
                ("Sketch an example page", "Projects", "UI/Frontend", "High", "Not Started", "Fictional example task."),
            )
            db.execute(
                "INSERT INTO goals(title,pillar,target_value,current_value) VALUES (?,?,?,?)",
                ("Complete five study sessions", "Airbnb", 5000, 1900),
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
    q += " ORDER BY COALESCE(due_date,'9999-12-31'), COALESCE(due_time,'23:59'), id DESC"
    with conn() as db:
        return db.execute(q, params).fetchall()

def get_task(task_id: int):
    with conn() as db:
        return db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()

def add_task(title, pillar, subcategory, priority, status, due_date, due_time, notes):
    with conn() as db:
        cur = db.execute(
            """INSERT INTO tasks(
                title,pillar,subcategory,priority,status,
                due_date,due_time,
                sprint_id,agenda_date,effort_points,
                notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (title, pillar, subcategory, priority, status,
             due_date or None, due_time or None,
             None, None, 1,
             notes or None),
        )
        db.commit()
        return cur.lastrowid

def update_task(task_id, title, pillar, subcategory, priority, status, due_date, due_time, notes, sprint_id=None, agenda_date=None, effort_points=1):
    with conn() as db:
        db.execute(
            """UPDATE tasks SET
                title=?, pillar=?, subcategory=?, priority=?, status=?,
                due_date=?, due_time=?,
                sprint_id=?, agenda_date=?, effort_points=?,
                notes=?,
                updated_at=datetime('now')
                WHERE id=?""",
            (title, pillar, subcategory, priority, status,
             due_date or None, due_time or None,
             sprint_id, agenda_date or None, int(effort_points or 1),
             notes or None,
             task_id),
        )
        db.commit()

def set_task_sprint(task_id: int, sprint_id: int | None):
    with conn() as db:
        db.execute("UPDATE tasks SET sprint_id=?, updated_at=datetime('now') WHERE id=?", (sprint_id, task_id))
        db.commit()

def set_task_agenda_date(task_id: int, agenda_date: str | None):
    with conn() as db:
        db.execute("UPDATE tasks SET agenda_date=?, updated_at=datetime('now') WHERE id=?", (agenda_date, task_id))
        db.commit()

def create_sprint(name: str, start_date: str, end_date: str, focus: str = ""):
    with conn() as db:
        db.execute(
            "INSERT INTO sprints(name,start_date,end_date,focus) VALUES (?,?,?,?)",
            (name, start_date, end_date, focus or None),
        )
        db.commit()

def list_sprints():
    with conn() as db:
        return db.execute("SELECT * FROM sprints ORDER BY start_date DESC").fetchall()

def get_sprint(sprint_id: int):
    with conn() as db:
        return db.execute("SELECT * FROM sprints WHERE id=?", (sprint_id,)).fetchone()

def get_current_sprint(today_iso: str):
    with conn() as db:
        return db.execute(
            "SELECT * FROM sprints WHERE start_date<=? AND end_date>=? ORDER BY start_date DESC LIMIT 1",
            (today_iso, today_iso),
        ).fetchone()

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

def list_roadmap(month: str = "", pillar: str = ""):
    where = []
    params = []
    if month:
        where.append("month=?"); params.append(month)
    if pillar:
        where.append("pillar=?"); params.append(pillar)
    q = "SELECT * FROM roadmap"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY month DESC, id DESC"
    with conn() as db:
        return db.execute(q, tuple(params)).fetchall()

def add_roadmap(pillar: str, month: str, title: str, status: str, notes: str = ""):
    with conn() as db:
        db.execute(
            "INSERT INTO roadmap(pillar,month,title,status,notes) VALUES (?,?,?,?,?)",
            (pillar, month, title, status, notes or None),
        )
        db.commit()

def update_roadmap(item_id: int, pillar: str, month: str, title: str, status: str, notes: str = ""):
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


def update_task_planning(task_id: int, sprint_id=None, agenda_date=None, effort_points: int = 1):
    with conn() as db:
        db.execute(
            "UPDATE tasks SET sprint_id=?, agenda_date=?, effort_points=?, updated_at=datetime('now') WHERE id=?",
            (sprint_id, agenda_date or None, int(effort_points), task_id),
        )
        db.commit()


def list_sprints():
    with conn() as db:
        return db.execute("SELECT * FROM sprints ORDER BY start_date DESC, id DESC").fetchall()


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
        where.append("month=?"); params.append(month)
    if pillar:
        where.append("pillar=?"); params.append(pillar)
    q = "SELECT * FROM roadmap"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY month DESC, id DESC"
    with conn() as db:
        return db.execute(q, tuple(params)).fetchall()


def add_roadmap(pillar: str, month: str, title: str, status: str = "Not Started", notes: str = ""):
    with conn() as db:
        db.execute(
            "INSERT INTO roadmap(pillar,month,title,status,notes) VALUES (?,?,?,?,?)",
            (pillar, month, title, status, notes or None),
        )
        db.commit()


def update_roadmap(item_id: int, pillar: str, month: str, title: str, status: str, notes: str = ""):
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
    )


def list_goals():
    with conn() as db:
        return db.execute("SELECT * FROM goals ORDER BY id DESC").fetchall()

def add_goal(title: str, pillar: str, target_value: int, current_value: int, due_date: str = ""):
    with conn() as db:
        db.execute(
            "INSERT INTO goals(title,pillar,target_value,current_value,due_date) VALUES (?,?,?,?,?)",
            (title, pillar, int(target_value), int(current_value), due_date or None),
        )
        db.commit()

def update_goal(goal_id: int, title: str, pillar: str, target_value: int, current_value: int, due_date: str = ""):
    with conn() as db:
        db.execute(
            "UPDATE goals SET title=?, pillar=?, target_value=?, current_value=?, due_date=? WHERE id=?",
            (title, pillar, int(target_value), int(current_value), due_date or None, goal_id),
        )
        db.commit()

def delete_goal(goal_id: int):
    with conn() as db:
        db.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        db.commit()


# ===== HOSTING / AIRBNB PROPERTIES =====

def list_properties():
    with conn() as db:
        return db.execute("SELECT * FROM properties ORDER BY created_at DESC").fetchall()


def get_property(property_id: int):
    with conn() as db:
        return db.execute("SELECT * FROM properties WHERE id=?", (property_id,)).fetchone()


def add_property(name: str, address: str = "", listing_url: str = "", nightly_price: float = 0.0, commission_rate: float = 0.03, status: str = "Active", notes: str = ""):
    with conn() as db:
        db.execute(
            """INSERT INTO properties(name,address,listing_url,nightly_price,commission_rate,status,notes)
               VALUES (?,?,?,?,?,?,?)""",
            (name, address or None, listing_url or None, float(nightly_price), float(commission_rate), status, notes or None),
        )
        db.commit()
        cur = db.execute("SELECT last_insert_rowid() as id").fetchone()
        return cur["id"]


def update_property(property_id: int, name: str, address: str = "", listing_url: str = "", nightly_price: float = 0.0, commission_rate: float = 0.03, status: str = "Active", notes: str = ""):
    with conn() as db:
        db.execute(
            """UPDATE properties SET name=?, address=?, listing_url=?, nightly_price=?, commission_rate=?, status=?, notes=?, updated_at=datetime('now')
               WHERE id=?""",
            (name, address or None, listing_url or None, float(nightly_price), float(commission_rate), status, notes or None, property_id),
        )
        db.commit()


def delete_property(property_id: int):
    with conn() as db:
        db.execute("DELETE FROM hosting_tasks WHERE property_id=?", (property_id,))
        db.execute("DELETE FROM properties WHERE id=?", (property_id,))
        db.commit()


def list_hosting_tasks(property_id: int = None):
    if property_id:
        q = "SELECT * FROM hosting_tasks WHERE property_id=? ORDER BY due_date, priority DESC, id DESC"
        with conn() as db:
            return db.execute(q, (property_id,)).fetchall()
    else:
        q = "SELECT * FROM hosting_tasks ORDER BY due_date, priority DESC, id DESC"
        with conn() as db:
            return db.execute(q).fetchall()


def add_hosting_task(property_id: int, title: str, description: str = "", status: str = "Not Started", due_date: str = "", priority: str = "Medium"):
    with conn() as db:
        db.execute(
            """INSERT INTO hosting_tasks(property_id,title,description,status,due_date,priority)
               VALUES (?,?,?,?,?,?)""",
            (property_id, title, description or None, status, due_date or None, priority),
        )
        db.commit()


def update_hosting_task(task_id: int, title: str, description: str = "", status: str = "Not Started", due_date: str = "", priority: str = "Medium"):
    with conn() as db:
        db.execute(
            """UPDATE hosting_tasks SET title=?, description=?, status=?, due_date=?, priority=?, updated_at=datetime('now')
               WHERE id=?""",
            (title, description or None, status, due_date or None, priority, task_id),
        )
        db.commit()


def delete_hosting_task(task_id: int):
    with conn() as db:
        db.execute("DELETE FROM hosting_tasks WHERE id=?", (task_id,))
        db.commit()


def cycle_hosting_task_status(task_id: int):
    t = db.execute("SELECT * FROM hosting_tasks WHERE id=?", (task_id,)).fetchone() if False else None
    with conn() as db:
        task = db.execute("SELECT * FROM hosting_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            return
        order = ["Not Started", "In Progress", "Completed"]
        cur = task["status"] or "Not Started"
        try:
            idx = order.index(cur)
        except ValueError:
            idx = 0
        new_status = order[(idx + 1) % len(order)]
        db.execute(
            "UPDATE hosting_tasks SET status=?, updated_at=datetime('now') WHERE id=?",
            (new_status, task_id),
        )
        db.commit()
