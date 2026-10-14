import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db as DB

APP_DIR = Path(__file__).parent
CONFIG = json.loads((APP_DIR / "config.json").read_text(encoding="utf-8"))

PILLARS = CONFIG["pillars"]
SUBCATS = CONFIG["subcategories"]
PRIORITIES = CONFIG["priorities"]
STATUSES = CONFIG["statuses"]

SCHOOL_PILLAR = "School"


@asynccontextmanager
async def lifespan(app):
    DB.init_db()
    if os.environ.get("ADHD_HQ_DEMO") == "1":
        DB.seed_if_empty()
    yield


app = FastAPI(title="ADHD HQ", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
)


@app.middleware("http")
async def validate_forms(request: Request, call_next):
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse(
                {"error": "Please submit changes from the app window."}, status_code=403
            )
        try:
            await request.body()
            form = await request.form()
            for key in ("title", "name"):
                if key in form and not str(form[key]).strip():
                    raise ValueError("Enter a title before saving.")
            for key, choices in (
                ("status", STATUSES),
                ("priority", PRIORITIES),
                ("pillar", PILLARS),
            ):
                if key in form and form[key] not in choices:
                    raise ValueError(f"Choose a valid {key}.")
            for key in ("start_date", "end_date", "due_date", "agenda_date"):
                if form.get(key) and not parse_date(str(form[key])):
                    raise ValueError("Use a valid date in YYYY-MM-DD format.")
            if form.get("month"):
                datetime.strptime(str(form["month"]) + "-01", "%Y-%m-%d")
            if form.get("due_time"):
                datetime.strptime(str(form["due_time"]), "%H:%M")
            if (
                form.get("start_date")
                and form.get("end_date")
                and form["end_date"] < form["start_date"]
            ):
                raise ValueError("The end date must be on or after the start date.")
            for key, minimum in (
                ("target_value", 1),
                ("current_value", 0),
                ("effort_points", 1),
            ):
                if key in form and int(form[key]) < minimum:
                    raise ValueError(
                        f"{key.replace('_', ' ').capitalize()} must be at least {minimum}."
                    )
            if form.get("color"):
                import re

                if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(form["color"])):
                    raise ValueError("Choose a valid timeline color.")
            for key, getter in (
                ("task_id", DB.get_task),
                ("bar_id", DB.get_gantt_bar),
                ("gantt_id", DB.get_gantt_bar),
                ("sprint_id", DB.get_sprint),
            ):
                if form.get(key) and not getter(int(form[key])):
                    raise ValueError(
                        "The selected item no longer exists. Refresh the page."
                    )
        except (ValueError, TypeError) as error:
            return JSONResponse({"error": str(error)}, status_code=400)
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def iso_today():
    return date.today().isoformat()


def parse_date(s):
    if not s:
        return None
    try:
        parsed = date.fromisoformat(s)
        return parsed if parsed.isoformat() == s else None
    except ValueError:
        return None


def days_left(due_date_str):
    d = parse_date(due_date_str)
    if not d:
        return None
    return (d - date.today()).days


def compute_stats(tasks):
    total = len(tasks)
    by_status = {s: 0 for s in STATUSES}
    by_priority = {p: 0 for p in PRIORITIES}
    by_pillar = {p: {"total": 0, "completed": 0} for p in PILLARS}
    overdue = []

    for t in tasks:
        st = t["status"]
        pr = t["priority"]
        pi = t["pillar"]

        by_status[st] = by_status.get(st, 0) + 1
        by_priority[pr] = by_priority.get(pr, 0) + 1

        if pi in by_pillar:
            by_pillar[pi]["total"] += 1
            if st == "Completed":
                by_pillar[pi]["completed"] += 1

        dl = days_left(t["due_date"])
        if dl is not None and dl < 0 and st != "Completed":
            overdue.append(t)

    completed = by_status.get("Completed", 0)
    progress = int((completed / total) * 100) if total else 0

    def overdue_key(t):
        dl = days_left(t["due_date"])
        return dl if dl is not None else 999999

    overdue_sorted = sorted(overdue, key=overdue_key)[:6]

    return {
        "total": total,
        "completed": completed,
        "pending": total - completed,
        "progress": progress,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_pillar": by_pillar,
        "overdue": [dict(task) for task in overdue_sorted],
        "today": iso_today(),
    }


def month_grid(year: int, month: int):
    first = date(year, month, 1)
    start = first - timedelta(days=(first.weekday() + 1) % 7)  # Sunday start
    days = [start + timedelta(days=i) for i in range(42)]
    weeks = [days[i : i + 7] for i in range(0, 42, 7)]
    return weeks


def week_bounds_sun_to_sat(d: date):
    """Return (start_sun, end_sat) for the week containing date d."""
    start = d - timedelta(days=(d.weekday() + 1) % 7)  # Sunday
    end = start + timedelta(days=6)
    return start, end


def sprint_name_for_week(start_sun: date):
    iso_year, iso_week, _ = start_sun.isocalendar()
    return f"Sprint {iso_year}-W{iso_week:02d}"


@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    tasks_all = DB.list_tasks()
    stats = compute_stats(tasks_all)

    # Get current sprint data
    today = date.today()
    current_sprint = DB.get_current_sprint(today.isoformat())
    sprint_task_count = 0
    if current_sprint:
        sprint_tasks = DB.list_tasks_for_sprint(
            int(current_sprint["id"]), pillar=PROJECT_PILLAR
        )
        sprint_task_count = len(list(sprint_tasks))

    # Daily sprint and Gantt progress metrics
    daily_tasks = [dict(t) for t in DB.list_tasks_for_agenda(today.isoformat())]
    daily_completed = len([t for t in daily_tasks if t["status"] == "Completed"])
    daily_progress = (
        int((daily_completed / len(daily_tasks)) * 100) if daily_tasks else 0
    )

    weekly_sprint_progress = 0
    if current_sprint:
        sprint_tasks = [
            dict(t)
            for t in DB.list_tasks_for_sprint(
                int(current_sprint["id"]), pillar=PROJECT_PILLAR
            )
        ]
        sprint_completed = len([t for t in sprint_tasks if t["status"] == "Completed"])
        weekly_sprint_progress = (
            int((sprint_completed / len(sprint_tasks)) * 100) if sprint_tasks else 0
        )

    gantt_bars = [dict(b) for b in DB.list_gantt_bars()]
    if gantt_bars:
        gantt_completed = len([b for b in gantt_bars if b["status"] == "Completed"])
        gantt_progress = int((gantt_completed / len(gantt_bars)) * 100)
    else:
        gantt_progress = 0

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "stats": stats,
            "statuses": STATUSES,
            "current_sprint": dict(current_sprint) if current_sprint else None,
            "sprint_task_count": sprint_task_count,
            "daily_progress": daily_progress,
            "weekly_sprint_progress": weekly_sprint_progress,
            "gantt_progress": gantt_progress,
            "nav": "dashboard",
        },
    )


@app.get("/tasks", response_class=HTMLResponse)
def tasks_page(
    request: Request,
    status: str = "",
    priority: str = "",
    q: str = "",
):
    # Force this page to ONLY show School tasks
    where = ["pillar=?"]
    params = [SCHOOL_PILLAR]

    if status:
        where.append("status=?")
        params.append(status)

    if priority:
        where.append("priority=?")
        params.append(priority)

    if q:
        where.append("(title LIKE ? OR notes LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    tasks = DB.list_tasks(" AND ".join(where), tuple(params))

    tasks_ui = []
    for t in tasks:
        td = dict(t)
        td["days_left"] = days_left(td.get("due_date"))
        tasks_ui.append(td)

    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={
            "request": request,
            "tasks": tasks_ui,
            "subcats": SUBCATS,
            "priorities": PRIORITIES,
            "statuses": STATUSES,
            "filters": {
                "status": status,
                "priority": priority,
                "q": q,
            },
            "nav": "tasks",
        },
    )


@app.post("/tasks/add")
def tasks_add(
    title: str = Form(...),
    subcategory: str = Form("Assignments"),
    priority: str = Form("Medium"),
    status: str = Form("Not Started"),
    due_date: str = Form(""),
    due_time: str = Form(""),
    notes: str = Form(""),
    gantt_id: int = Form(None),
):
    pillar = SCHOOL_PILLAR
    if pillar in SUBCATS and subcategory not in SUBCATS[pillar]:
        subcategory = SUBCATS[pillar][0]
    DB.add_task(
        title,
        pillar,
        subcategory,
        priority,
        status,
        due_date,
        due_time,
        notes,
        gantt_id=gantt_id,
    )
    return RedirectResponse("/tasks", status_code=303)


PROJECT_PILLAR = "Projects"


@app.post("/weekly/add")
def weekly_add_task(
    title: str = Form(...),
    subcategory: str = Form("UI/Frontend"),
    priority: str = Form("Medium"),
    status: str = Form("Not Started"),
    due_date: str = Form(""),
    due_time: str = Form(""),
    notes: str = Form(""),
    agenda_date: str = Form(""),  # selected day from weekly page
):
    pillar = PROJECT_PILLAR

    if pillar in SUBCATS and subcategory not in SUBCATS[pillar]:
        subcategory = SUBCATS[pillar][0]

    # Create task and capture id
    new_id = DB.add_task(
        title, pillar, subcategory, priority, status, due_date, due_time, notes
    )

    # Attach to current sprint and selected agenda day
    today = date.today()
    sprint = DB.get_current_sprint(today.isoformat())
    if sprint:
        sprint_id = int(sprint["id"])
    else:
        start_sun, end_sat = week_bounds_sun_to_sat(today)
        name = sprint_name_for_week(start_sun)
        DB.create_sprint(name, start_sun.isoformat(), end_sat.isoformat(), focus="")
        sprint = DB.get_current_sprint(today.isoformat())
        sprint_id = int(sprint["id"]) if sprint else None

    DB.update_task_planning(
        new_id,
        sprint_id=sprint_id,
        agenda_date=agenda_date or None,
        effort_points=1,
    )

    return RedirectResponse(
        f"/weekly?day={agenda_date}" if agenda_date else "/weekly", status_code=303
    )


@app.post("/tasks/update")
def tasks_update(
    task_id: int = Form(...),
    title: str = Form(...),
    subcategory: str = Form(...),
    priority: str = Form(...),
    status: str = Form(...),
    due_date: str = Form(""),
    due_time: str = Form(""),
    notes: str = Form(""),
    gantt_id: int = Form(None),
):
    # Check if this is an Projects task
    task = DB.get_task(task_id)
    if task and task["pillar"] == PROJECT_PILLAR:
        # Allow Projects tasks to be updated with their original pillar
        DB.update_task(
            task_id,
            title,
            PROJECT_PILLAR,
            subcategory,
            priority,
            status,
            due_date,
            due_time,
            notes,
            gantt_id=gantt_id if gantt_id is not None else DB.UNSET,
        )
        return RedirectResponse("/weekly", status_code=303)
    else:
        # School tasks only
        pillar = SCHOOL_PILLAR
        if pillar in SUBCATS and subcategory not in SUBCATS[pillar]:
            subcategory = SUBCATS[pillar][0]
        DB.update_task(
            task_id,
            title,
            pillar,
            subcategory,
            priority,
            status,
            due_date,
            due_time,
            notes,
            gantt_id=gantt_id if gantt_id is not None else DB.UNSET,
        )
        return RedirectResponse("/tasks", status_code=303)


@app.post("/tasks/toggle")
def tasks_toggle(task_id: int = Form(...)):
    task = DB.get_task(task_id)
    DB.toggle_complete(task_id)
    return RedirectResponse(
        "/weekly" if task and task["pillar"] == PROJECT_PILLAR else "/tasks",
        status_code=303,
    )


@app.post("/tasks/cycle-status")
def tasks_cycle_status(task_id: int = Form(...)):
    task = DB.get_task(task_id)
    DB.cycle_status(task_id)
    return RedirectResponse(
        "/weekly" if task and task["pillar"] == PROJECT_PILLAR else "/tasks",
        status_code=303,
    )


@app.post("/tasks/delete")
def tasks_delete(task_id: int = Form(...)):
    task = DB.get_task(task_id)
    DB.delete_task(task_id)
    return RedirectResponse(
        "/weekly" if task and task["pillar"] == PROJECT_PILLAR else "/tasks",
        status_code=303,
    )


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request, y: int = 0, m: int = 0, day: str = ""):
    today = date.today()
    year = y or today.year
    month = m or today.month
    if not 1 <= month <= 12 or not 2 <= year <= 9998:
        year, month = today.year, today.month
    weeks = month_grid(year, month)

    tasks = [dict(t) for t in DB.list_tasks()]
    by_date = {}
    for t in tasks:
        for task_day in {t.get("due_date"), t.get("agenda_date")} - {None, ""}:
            by_date.setdefault(task_day, []).append(t)

    selected_tasks = []
    if day:
        selected_tasks = [
            t for t in tasks if t.get("due_date") == day or t.get("agenda_date") == day
        ]

    # Gantt chart data - get next 6 months of Projects roadmap
    gantt_data = []
    months_data = []
    for i in range(6):
        month_offset = year * 12 + month - 1 + i
        check_date = date(month_offset // 12, month_offset % 12 + 1, 1)
        month_key = check_date.strftime("%Y-%m")
        months_data.append(
            {
                "month": month_key,
                "display": check_date.strftime("%B %Y"),
                "short": check_date.strftime("%b"),
            }
        )
        roadmap_items = [
            dict(r) for r in DB.list_roadmap(month=month_key, pillar="Projects")
        ]
        for item in roadmap_items:
            gantt_data.append(
                {
                    "id": item.get("id"),
                    "title": item["title"],
                    "month": item["month"],
                    "status": item["status"],
                    "notes": item.get("notes", ""),
                }
            )

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "request": request,
            "previous_month": (date(year, month, 1) - timedelta(days=1)),
            "next_month": date(year + (month == 12), month % 12 + 1, 1),
            "year": year,
            "month": month,
            "weeks": weeks,
            "today": today,
            "by_date": by_date,
            "selected_day": day,
            "selected_tasks": selected_tasks,
            "gantt_data": gantt_data,
            "months_data": months_data,
            "priorities": PRIORITIES,
            "statuses": STATUSES,
            "nav": "calendar",
        },
    )


@app.get("/weekly", response_class=HTMLResponse)
def weekly_page(request: Request, day: str = "", gantt_id: int | None = None):
    """Sprint planning + daily agenda."""
    today = date.today()
    start_sun, end_sat = week_bounds_sun_to_sat(today)
    days = [start_sun + timedelta(days=i) for i in range(7)]

    sprint = DB.get_current_sprint(today.isoformat())
    if not sprint:
        name = sprint_name_for_week(start_sun)
        DB.create_sprint(name, start_sun.isoformat(), end_sat.isoformat(), focus="")
        sprint = DB.get_current_sprint(today.isoformat())

    sprint_id = int(sprint["id"]) if sprint else None
    sprint_tasks = [
        dict(t)
        for t in (
            DB.list_tasks_for_sprint(sprint_id, pillar=PROJECT_PILLAR)
            if sprint_id
            else []
        )
    ]
    board = {s: [] for s in STATUSES}
    for t in sprint_tasks:
        board.setdefault(t["status"], []).append(t)

    # Pre-calc agenda tasks per date for weekly day cards
    day_agenda_count = {}
    for t in sprint_tasks:
        ad = t.get("agenda_date")
        if ad:
            day_agenda_count[ad] = day_agenda_count.get(ad, 0) + 1

    selected_day = day or today.isoformat()
    agenda = [dict(t) for t in DB.list_tasks_for_agenda(selected_day)]

    month_key = today.strftime("%Y-%m")
    roadmap = [dict(r) for r in DB.list_roadmap(month=month_key, pillar="Projects")]

    # Gantt bars and selected badge
    gantt_bars = [dict(b) for b in DB.list_gantt_bars()]
    selected_gantt = DB.get_gantt_bar(gantt_id) if gantt_id else None
    gantt_tasks = (
        [dict(t) for t in DB.list_tasks_for_gantt(gantt_id)] if gantt_id else []
    )

    # Get future sprints (next 3)
    all_sprints = [dict(s) for s in DB.list_sprints()]
    future_sprints = sorted(
        (s for s in all_sprints if s["start_date"] > today.isoformat()),
        key=lambda s: s["start_date"],
    )[:3]

    return templates.TemplateResponse(
        request=request,
        name="weekly.html",
        context={
            "request": request,
            "today": today,
            "days": days,
            "selected_day": selected_day,
            "sprint": dict(sprint) if sprint else None,
            "board": board,
            "agenda": agenda,
            "future_sprints": future_sprints,
            "pillars": PILLARS,
            "subcats": SUBCATS,
            "priorities": PRIORITIES,
            "statuses": STATUSES,
            "roadmap": roadmap,
            "gantt_bars": gantt_bars,
            "selected_gantt": dict(selected_gantt) if selected_gantt else None,
            "gantt_tasks": gantt_tasks,
            "day_agenda_count": day_agenda_count,
            "nav": "weekly",
        },
    )


@app.post("/tasks/plan")
def tasks_plan(
    task_id: int = Form(...),
    sprint_id: int = Form(None),
    agenda_date: str = Form(""),
    effort_points: int = Form(1),
):
    DB.update_task_planning(
        task_id,
        sprint_id=sprint_id or None,
        agenda_date=agenda_date or None,
        effort_points=int(effort_points or 1),
    )
    return RedirectResponse("/weekly", status_code=303)


@app.post("/weekly/gantt/add")
def weekly_gantt_add(
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    color: str = Form("#1f77b4"),
    status: str = Form("Not Started"),
    notes: str = Form(""),
):
    DB.add_gantt_bar(title, start_date, end_date, color, status, notes)
    return RedirectResponse("/weekly", status_code=303)


@app.post("/weekly/gantt/update")
def weekly_gantt_update(
    bar_id: int = Form(...),
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    color: str = Form("#1f77b4"),
    status: str = Form("Not Started"),
    notes: str = Form(""),
):
    DB.update_gantt_bar(bar_id, title, start_date, end_date, color, status, notes)
    return RedirectResponse("/weekly", status_code=303)


@app.post("/weekly/gantt/delete")
def weekly_gantt_delete(bar_id: int = Form(...)):
    DB.delete_gantt_bar(bar_id)
    return RedirectResponse("/weekly", status_code=303)


@app.post("/weekly/gantt/task/add")
def weekly_gantt_task_add(
    title: str = Form(...),
    due_date: str = Form(""),
    due_time: str = Form(""),
    priority: str = Form("Medium"),
    status: str = Form("Not Started"),
    notes: str = Form(""),
    gantt_id: int = Form(None),
    agenda_date: str = Form(""),
):
    DB.add_task(
        title,
        PROJECT_PILLAR,
        "UI/Frontend",
        priority,
        status,
        due_date or None,
        due_time or None,
        notes,
        sprint_id=None,
        agenda_date=agenda_date or None,
        effort_points=1,
        gantt_id=gantt_id,
    )
    return RedirectResponse(f"/weekly?gantt_id={gantt_id}", status_code=303)


@app.post("/calendar/add")
def calendar_add_task(
    title: str = Form(...),
    due_date: str = Form(...),
    due_time: str = Form(""),
    priority: str = Form("Medium"),
    status: str = Form("Not Started"),
    notes: str = Form(""),
):
    DB.add_task(
        title,
        PROJECT_PILLAR,
        "UI/Frontend",
        priority,
        status,
        due_date,
        due_time or None,
        notes,
        sprint_id=None,
        agenda_date=due_date,
        effort_points=1,
    )
    return RedirectResponse(f"/calendar?day={due_date}", status_code=303)


@app.post("/calendar/task/update")
def calendar_task_update(
    task_id: int = Form(...),
    title: str = Form(...),
    due_date: str = Form(""),
    due_time: str = Form(""),
    priority: str = Form("Medium"),
    status: str = Form("Not Started"),
    notes: str = Form(""),
    agenda_date: str = Form(""),
):
    # Keep pillar Projects if this is a sprint task else fallback
    task = DB.get_task(task_id)
    task = dict(task) if task else None
    pillar = task["pillar"] if task else PROJECT_PILLAR
    DB.update_task(
        task_id,
        title,
        pillar,
        task["subcategory"] if task else "UI/Frontend",
        priority,
        status,
        due_date or None,
        due_time or None,
        notes,
        sprint_id=task.get("sprint_id") if task else None,
        agenda_date=agenda_date or due_date or None,
        effort_points=task.get("effort_points", 1),
        gantt_id=task.get("gantt_id") if task else None,
    )
    return RedirectResponse(f"/calendar?day={agenda_date or due_date}", status_code=303)


@app.post("/calendar/task/delete")
def calendar_task_delete(task_id: int = Form(...)):
    t = DB.get_task(task_id)
    if t:
        day = t["agenda_date"] or t["due_date"]
    else:
        day = ""
    DB.delete_task(task_id)
    return RedirectResponse(f"/calendar?day={day}", status_code=303)


@app.post("/sprints/create")
def sprints_create(
    name: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    focus: str = Form(""),
):
    DB.create_sprint(name, start_date, end_date, focus)
    return RedirectResponse("/weekly", status_code=303)


@app.get("/goals", response_class=HTMLResponse)
def goals_page(request: Request):
    goals = [dict(g) for g in DB.list_goals()]
    for g in goals:
        tv = max(int(g["target_value"]), 1)
        g["pct"] = int((int(g["current_value"]) / tv) * 100)

    today = date.today()
    month_key = today.strftime("%Y-%m")
    roadmap = [dict(r) for r in DB.list_roadmap(pillar="Projects")]

    return templates.TemplateResponse(
        request=request,
        name="goals.html",
        context={
            "request": request,
            "goals": goals,
            "roadmap": roadmap,
            "month_key": month_key,
            "pillars": PILLARS,
            "statuses": STATUSES,
            "nav": "goals",
        },
    )


@app.post("/roadmap/add")
def roadmap_add(
    pillar: str = Form("Projects"),
    month: str = Form(...),
    title: str = Form(...),
    status: str = Form("Not Started"),
    notes: str = Form(""),
):
    DB.add_roadmap(pillar, month, title, status, notes)
    return RedirectResponse("/goals", status_code=303)


@app.post("/roadmap/update")
def roadmap_update(
    item_id: int = Form(...),
    pillar: str = Form(...),
    month: str = Form(...),
    title: str = Form(...),
    status: str = Form(...),
    notes: str = Form(""),
):
    DB.update_roadmap(item_id, pillar, month, title, status, notes)
    return RedirectResponse("/goals", status_code=303)


@app.post("/roadmap/delete")
def roadmap_delete(item_id: int = Form(...)):
    DB.delete_roadmap(item_id)
    return RedirectResponse("/goals", status_code=303)


@app.post("/goals/add")
def goals_add(
    title: str = Form(...),
    pillar: str = Form("Projects"),
    target_value: int = Form(100),
    current_value: int = Form(0),
    due_date: str = Form(""),
):
    DB.add_goal(title, pillar, target_value, current_value, due_date)
    return RedirectResponse("/goals", status_code=303)


@app.post("/goals/update")
def goals_update(
    goal_id: int = Form(...),
    title: str = Form(...),
    pillar: str = Form(...),
    target_value: int = Form(...),
    current_value: int = Form(...),
    due_date: str = Form(""),
):
    DB.update_goal(goal_id, title, pillar, target_value, current_value, due_date)
    return RedirectResponse("/goals", status_code=303)


@app.post("/goals/delete")
def goals_delete(goal_id: int = Form(...)):
    DB.delete_goal(goal_id)
    return RedirectResponse("/goals", status_code=303)


@app.get("/api/config")
def api_config():
    return JSONResponse(CONFIG)


@app.get("/api/stats")
def api_stats():
    tasks = DB.list_tasks()
    return JSONResponse(compute_stats(tasks))


if __name__ == "__main__":
    from desktop import main

    main()
