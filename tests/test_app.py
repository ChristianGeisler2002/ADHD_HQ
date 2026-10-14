from datetime import date

import pytest
from fastapi.testclient import TestClient

import db
from app import app, month_grid


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tasks.db")
    monkeypatch.delenv("ADHD_HQ_DEMO", raising=False)
    with TestClient(app) as client:
        yield client


def test_pages_and_empty_start(client):
    for route in (
        "/dashboard",
        "/tasks",
        "/weekly",
        "/calendar",
        "/goals",
        "/api/stats",
    ):
        assert client.get(route).status_code == 200
    assert db.list_tasks() == []


def test_sample_workspace_stays_generic_and_seeds_once(client):
    db.seed_if_empty()
    titles = [row["title"] for row in db.list_tasks()]
    assert "Write a practice summary" in titles
    assert len(db.list_goals()) == 2
    db.seed_if_empty()
    assert len(db.list_tasks()) == len(titles)
    with db.conn() as connection:
        connection.execute("DELETE FROM tasks")
        connection.execute("DELETE FROM goals")
    db.seed_if_empty()
    assert db.list_tasks() == []


def test_samples_do_not_mix_with_an_existing_workspace(client):
    db.add_task("Existing task", "School", "Reading", "Low", "Not Started", "", "", "")
    db.seed_if_empty()
    assert [row["title"] for row in db.list_tasks()] == ["Existing task"]
    assert db.list_goals() == []


def test_task_edit_and_status_preserve_planning(client):
    bar = db.add_gantt_bar("Milestone", "2026-10-14", "2026-10-18")
    task = db.add_task(
        "Draft",
        "Projects",
        "UI/Frontend",
        "High",
        "In Progress",
        "2026-10-15",
        "",
        "",
        agenda_date="2026-10-14",
        gantt_id=bar,
    )
    db.create_sprint("Current", "2026-10-11", "2026-10-17")
    sprint = db.list_sprints()[0]["id"]
    db.update_task_planning(task, sprint, "2026-10-14", 3)
    result = client.post(
        "/tasks/update",
        data={
            "task_id": task,
            "title": "Revised",
            "subcategory": "UI/Frontend",
            "priority": "High",
            "status": "In Progress",
        },
    )
    assert result.status_code == 200
    for action in (db.toggle_complete, db.cycle_status):
        action(task)
        saved = db.get_task(task)
        assert (
            saved["sprint_id"],
            saved["agenda_date"],
            saved["effort_points"],
            saved["gantt_id"],
        ) == (sprint, "2026-10-14", 3, bar)
    assert client.get("/api/stats").status_code == 200


def test_validation_and_gantt_link_cleanup(client):
    assert (
        client.post(
            "/weekly/gantt/add",
            data={
                "title": "Bad range",
                "start_date": "2026-10-20",
                "end_date": "2026-10-14",
            },
        ).status_code
        == 400
    )
    assert client.post("/tasks/add", data={"title": " "}).status_code == 400
    assert (
        client.post(
            "/tasks/add",
            data={"title": "Valid"},
            headers={"origin": "https://example.com"},
        ).status_code
        == 403
    )
    assert client.post("/tasks/add", data={"title": "Valid"}).status_code == 200
    bar = db.add_gantt_bar("Same day", "2026-10-14", "2026-10-14")
    task = db.add_task(
        "Linked", "School", "Reading", "Low", "Not Started", "", "", "", gantt_id=bar
    )
    db.delete_gantt_bar(bar)
    assert db.get_task(task)["gantt_id"] is None


def test_calendar_unique_days_and_months(client):
    db.add_task(
        "Only once",
        "School",
        "Reading",
        "Low",
        "Not Started",
        "2026-01-31",
        "",
        "",
        agenda_date="2026-01-31",
    )
    html = client.get("/calendar?y=2026&m=1&day=2026-01-31").text
    assert "2 due" not in html
    assert 'value="2026-02"' in html and 'value="2026-03"' in html
    assert client.get("/calendar?m=13").status_code == 200
    grid = month_grid(2028, 2)
    assert grid[0][0].weekday() == 6
    assert date(2028, 2, 29) in [day for week in grid for day in week]


def test_legacy_migration_is_repeatable(client):
    db.init_db()
    db.init_db()
    with db.conn() as connection:
        assert "gantt_id" in {
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
        }


def test_older_database_keeps_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "legacy.db")
    with db.conn() as connection:
        connection.execute(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, pillar TEXT, subcategory TEXT, priority TEXT, status TEXT, due_date TEXT, due_time TEXT, notes TEXT, created_at TEXT, updated_at TEXT)"
        )
        connection.execute(
            "INSERT INTO tasks(id,title,pillar,status) VALUES(1,'Keep this task','School','In Progress')"
        )
    db.init_db()
    db.init_db()
    assert db.get_task(1)["title"] == "Keep this task"
    assert db.get_task(1)["gantt_id"] is None


def test_goals_roadmap_and_calendar_workflows(client):
    assert (
        client.post(
            "/goals/add",
            data={"title": "Reading target", "target_value": 10, "current_value": 2},
        ).status_code
        == 200
    )
    goal = db.list_goals()[0]
    assert (
        client.post(
            "/goals/update",
            data={
                "goal_id": goal["id"],
                "title": "Reading target",
                "pillar": "School",
                "target_value": 10,
                "current_value": 5,
            },
        ).status_code
        == 200
    )
    assert db.list_goals()[0]["current_value"] == 5
    assert (
        client.post(
            "/roadmap/add", data={"title": "Release", "month": "2026-10"}
        ).status_code
        == 200
    )
    item = db.list_roadmap()[0]
    assert (
        client.post(
            "/roadmap/update",
            data={
                "item_id": item["id"],
                "title": "Release",
                "month": "2026-11",
                "pillar": "Projects",
                "status": "Completed",
            },
        ).status_code
        == 200
    )
    assert db.list_roadmap()[0]["month"] == "2026-11"
    assert (
        client.post(
            "/calendar/add", data={"title": "Review", "due_date": "2026-10-15"}
        ).status_code
        == 200
    )
    task = db.list_tasks()[0]
    assert (
        client.post(
            "/calendar/task/update",
            data={
                "task_id": task["id"],
                "title": "Review moved",
                "due_date": "2026-10-16",
            },
        ).status_code
        == 200
    )
    assert db.get_task(task["id"])["agenda_date"] == "2026-10-16"


def test_database_import_refuses_overwrite(client, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    destination = tmp_path / "imported.db"
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "import_database.py"),
        str(db.DB_PATH),
        "--destination",
        str(destination),
    ]
    assert subprocess.run(command, capture_output=True).returncode == 0
    original = destination.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert destination.read_bytes() == original
