from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import date, datetime, timedelta
import threading, time, json
from pathlib import Path

import db as DB

APP_DIR = Path(__file__).parent
CONFIG = json.loads((APP_DIR / "config.json").read_text(encoding="utf-8"))

PILLARS = CONFIG["pillars"]
SUBCATS = CONFIG["subcategories"]
PRIORITIES = CONFIG["priorities"]
STATUSES = CONFIG["statuses"]

# (1) Lock the /tasks tab to School-only
SCHOOL_PILLAR = "School"

app = FastAPI()
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def iso_today():
    return date.today().isoformat()


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
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
        "overdue": overdue_sorted,
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


@app.on_event("startup")
def startup():
    DB.init_db()
    DB.seed_if_empty()


@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    # Keep your original stats logic
    tasks_all = DB.list_tasks()
    stats = compute_stats(tasks_all)

    # Get current sprint data
    today = date.today()
    current_sprint = DB.get_current_sprint(today.isoformat())
    sprint_task_count = 0
    if current_sprint:
        sprint_tasks = DB.list_tasks_for_sprint(int(current_sprint["id"]), pillar=PROJECT_PILLAR)
        sprint_task_count = len(list(sprint_tasks))

    # Get properties data
    properties = [dict(p) for p in DB.list_properties()]
    active_properties = len([p for p in properties if p["status"] == "Active"])
    avg_nightly_price = None
    if properties:
        total_price = sum(p["nightly_price"] for p in properties)
        avg_nightly_price = total_price / len(properties) if properties else 0

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "statuses": STATUSES,
            "current_sprint": dict(current_sprint) if current_sprint else None,
            "sprint_task_count": sprint_task_count,
            "properties": properties,
            "active_properties": active_properties,
            "avg_nightly_price": avg_nightly_price,
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
    params = [SCHOOL_PILLAR]  # <-- was "School"

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
        "tasks.html",
        {
            "request": request,
            "tasks": tasks_ui,
            "pillars": [SCHOOL_PILLAR],  # <-- was PILLARS
            "subcats": SUBCATS,
            "priorities": PRIORITIES,
            "statuses": STATUSES,
            "filters": {
                "pillar": SCHOOL_PILLAR,  # <-- add this so template logic stays stable
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
    # NOTE: even if your form still submits a pillar, we ignore it and force School.
    subcategory: str = Form("Assignments"),
    priority: str = Form("Medium"),
    status: str = Form("Not Started"),
    due_date: str = Form(""),
    due_time: str = Form(""),
    notes: str = Form(""),
):
    pillar = SCHOOL_PILLAR
    if pillar in SUBCATS and subcategory not in SUBCATS[pillar]:
        subcategory = SUBCATS[pillar][0]
    DB.add_task(title, pillar, subcategory, priority, status, due_date, due_time, notes)
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
    agenda_date: str = Form(""),   # selected day from weekly page
):
    pillar = PROJECT_PILLAR

    if pillar in SUBCATS and subcategory not in SUBCATS[pillar]:
        subcategory = SUBCATS[pillar][0]

    # Create task and capture id
    new_id = DB.add_task(title, pillar, subcategory, priority, status, due_date, due_time, notes)

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

    return RedirectResponse(f"/weekly?day={agenda_date}" if agenda_date else "/weekly", status_code=303)

@app.post("/tasks/update")
def tasks_update(
    task_id: int = Form(...),
    title: str = Form(...),
    # NOTE: force School pillar on updates too
    subcategory: str = Form(...),
    priority: str = Form(...),
    status: str = Form(...),
    due_date: str = Form(""),
    due_time: str = Form(""),
    notes: str = Form(""),
):
    # Check if this is an Projects task
    task = DB.get_task(task_id)
    if task and task["pillar"] == PROJECT_PILLAR:
        # Allow Projects tasks to be updated with their original pillar
        DB.update_task(task_id, title, PROJECT_PILLAR, subcategory, priority, status, due_date, due_time, notes)
        return RedirectResponse("/weekly", status_code=303)
    else:
        # School tasks only
        pillar = SCHOOL_PILLAR
        if pillar in SUBCATS and subcategory not in SUBCATS[pillar]:
            subcategory = SUBCATS[pillar][0]
        DB.update_task(task_id, title, pillar, subcategory, priority, status, due_date, due_time, notes)
        return RedirectResponse("/tasks", status_code=303)


@app.post("/tasks/toggle")
def tasks_toggle(task_id: int = Form(...)):
    DB.toggle_complete(task_id)
    return RedirectResponse("/tasks", status_code=303)


@app.post("/tasks/cycle-status")
def tasks_cycle_status(task_id: int = Form(...)):
    DB.cycle_status(task_id)
    return RedirectResponse("/tasks", status_code=303)


@app.post("/tasks/delete")
def tasks_delete(task_id: int = Form(...)):
    DB.delete_task(task_id)
    return RedirectResponse("/tasks", status_code=303)


@app.get("/calendar", response_class=HTMLResponse)
def calendar_page(request: Request, y: int = 0, m: int = 0, day: str = ""):
    today = date.today()
    year = y or today.year
    month = m or today.month
    weeks = month_grid(year, month)

    tasks = DB.list_tasks()
    by_date = {}
    for t in tasks:
        dd = t["due_date"]
        if dd:
            by_date.setdefault(dd, []).append(t)

    selected_tasks = []
    if day:
        selected_tasks = [dict(t) for t in by_date.get(day, [])]

    # Gantt chart data - get next 6 months of Projects roadmap
    gantt_data = []
    months_data = []
    for i in range(6):
        check_date = today + timedelta(days=30*i)
        month_key = check_date.strftime("%Y-%m")
        months_data.append({
            "month": month_key,
            "display": check_date.strftime("%B %Y"),
            "short": check_date.strftime("%b"),
        })
        roadmap_items = [dict(r) for r in DB.list_roadmap(month=month_key, pillar="Projects")]
        for item in roadmap_items:
            gantt_data.append({
                "id": item.get("id"),
                "title": item["title"],
                "month": item["month"],
                "status": item["status"],
                "notes": item.get("notes", ""),
            })

    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "year": year,
            "month": month,
            "weeks": weeks,
            "today": today,
            "by_date": by_date,
            "selected_day": day,
            "selected_tasks": selected_tasks,
            "gantt_data": gantt_data,
            "months_data": months_data,
            "nav": "calendar",
        },
    )


@app.get("/weekly", response_class=HTMLResponse)
def weekly_page(request: Request, day: str = ""):
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
    sprint_tasks = [dict(t) for t in (DB.list_tasks_for_sprint(sprint_id, pillar=PROJECT_PILLAR) if sprint_id else [])]
    board = {s: [] for s in STATUSES}
    for t in sprint_tasks:
        board.setdefault(t["status"], []).append(t)

    selected_day = day or today.isoformat()
    agenda = [dict(t) for t in DB.list_tasks_for_agenda(selected_day)]

    month_key = today.strftime("%Y-%m")
    roadmap = [dict(r) for r in DB.list_roadmap(month=month_key, pillar="Projects")]

    # Get future sprints (next 3)
    all_sprints = [dict(s) for s in DB.list_sprints()]
    future_sprints = [s for s in all_sprints if s["start_date"] > today.isoformat()][:3]

    return templates.TemplateResponse(
        "weekly.html",
        {
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
        "goals.html",
        {
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


@app.get("/hosting", response_class=HTMLResponse)
def hosting_page(request: Request):
    properties = [dict(p) for p in DB.list_properties()]
    tasks = [dict(t) for t in DB.list_hosting_tasks()]
    
    # Enrich tasks with property names
    for t in tasks:
        prop = DB.get_property(t["property_id"])
        t["property_name"] = prop["name"] if prop else "Unknown"
    
    return templates.TemplateResponse(
        "hosting.html",
        {
            "request": request,
            "properties": properties,
            "tasks": tasks,
            "nav": "hosting",
        },
    )


@app.post("/hosting/property/add")
def hosting_add_property(
    name: str = Form(...),
    address: str = Form(""),
    listing_url: str = Form(""),
    nightly_price: float = Form(0.0),
    commission_rate: float = Form(0.03),
    status: str = Form("Active"),
    notes: str = Form(""),
):
    DB.add_property(name, address, listing_url, nightly_price, commission_rate, status, notes)
    return RedirectResponse("/hosting", status_code=303)


@app.post("/hosting/property/update")
def hosting_update_property(
    property_id: int = Form(...),
    name: str = Form(...),
    address: str = Form(""),
    listing_url: str = Form(""),
    nightly_price: float = Form(0.0),
    commission_rate: float = Form(0.03),
    status: str = Form("Active"),
    notes: str = Form(""),
):
    DB.update_property(property_id, name, address, listing_url, nightly_price, commission_rate, status, notes)
    return RedirectResponse("/hosting", status_code=303)


@app.post("/hosting/property/delete")
def hosting_delete_property(property_id: int = Form(...)):
    DB.delete_property(property_id)
    return RedirectResponse("/hosting", status_code=303)


@app.post("/hosting/task/add")
def hosting_add_task(
    property_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    status: str = Form("Not Started"),
    due_date: str = Form(""),
    priority: str = Form("Medium"),
):
    DB.add_hosting_task(property_id, title, description, status, due_date, priority)
    return RedirectResponse("/hosting", status_code=303)


@app.post("/hosting/task/update")
def hosting_update_task(
    task_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    status: str = Form("Not Started"),
    due_date: str = Form(""),
    priority: str = Form("Medium"),
):
    DB.update_hosting_task(task_id, title, description, status, due_date, priority)
    return RedirectResponse("/hosting", status_code=303)


@app.post("/hosting/task/delete")
def hosting_delete_task(task_id: int = Form(...)):
    DB.delete_hosting_task(task_id)
    return RedirectResponse("/hosting", status_code=303)


def run_desktop():
    import webview
    import uvicorn

    def server():
        uvicorn.run(app, host="127.0.0.1", port=8844, log_level="warning")

    t = threading.Thread(target=server, daemon=True)
    t.start()
    time.sleep(0.6)

    webview.create_window(
        "ADHD HQ",
        "http://127.0.0.1:8844/dashboard",
        width=1400,
        height=860,
    )
    webview.start()


if __name__ == "__main__":
    run_desktop()