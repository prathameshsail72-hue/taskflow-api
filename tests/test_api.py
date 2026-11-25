import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=test_engine)

    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def create_project(client: TestClient, name: str = "Test Project", description: str | None = None) -> dict:
    payload = {"name": name}
    if description is not None:
        payload["description"] = description
    response = client.post("/projects", json=payload)
    assert response.status_code == 201
    return response.json()


def create_task(
    client: TestClient,
    project_id: int,
    title: str = "Test Task",
    status: str | None = None,
    priority: str | None = None,
) -> dict:
    payload: dict = {"title": title}
    if status is not None:
        payload["status"] = status
    if priority is not None:
        payload["priority"] = priority
    response = client.post(f"/projects/{project_id}/tasks", json=payload)
    assert response.status_code == 201
    return response.json()


class TestProjects:
    def test_create_project_returns_201(self, client):
        response = client.post("/projects", json={"name": "Alpha", "description": "First project"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Alpha"
        assert data["description"] == "First project"
        assert "id" in data
        assert "created_at" in data

    def test_list_projects_returns_200(self, client):
        create_project(client, "P1")
        create_project(client, "P2")
        response = client.get("/projects")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_project_with_tasks(self, client):
        project = create_project(client, "With Tasks")
        create_task(client, project["id"], "Task A")
        create_task(client, project["id"], "Task B")
        response = client.get(f"/projects/{project['id']}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) == 2

    def test_update_project_returns_200(self, client):
        project = create_project(client, "Old Name")
        response = client.put(f"/projects/{project['id']}", json={"name": "New Name"})
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_delete_project_returns_204(self, client):
        project = create_project(client)
        response = client.delete(f"/projects/{project['id']}")
        assert response.status_code == 204

    def test_get_unknown_project_returns_404(self, client):
        response = client.get("/projects/9999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"

    def test_update_unknown_project_returns_404(self, client):
        response = client.put("/projects/9999", json={"name": "X"})
        assert response.status_code == 404

    def test_delete_unknown_project_returns_404(self, client):
        response = client.delete("/projects/9999")
        assert response.status_code == 404


class TestCascade:
    def test_delete_project_cascades_to_tasks(self, client):
        project = create_project(client)
        task = create_task(client, project["id"])
        client.delete(f"/projects/{project['id']}")
        summary = client.get("/tasks/summary").json()
        assert summary["total_tasks"] == 0

    def test_cascade_via_direct_project_check(self, client):
        project = create_project(client)
        create_task(client, project["id"])
        create_task(client, project["id"])
        client.delete(f"/projects/{project['id']}")
        get_response = client.get(f"/projects/{project['id']}")
        assert get_response.status_code == 404


class TestTasks:
    def test_create_task_returns_201(self, client):
        project = create_project(client)
        response = client.post(f"/projects/{project['id']}/tasks", json={"title": "My Task"})
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My Task"
        assert data["project_id"] == project["id"]

    def test_create_task_under_unknown_project_returns_404(self, client):
        response = client.post("/projects/9999/tasks", json={"title": "Orphan"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"

    def test_list_tasks_returns_200(self, client):
        project = create_project(client)
        create_task(client, project["id"], "T1")
        create_task(client, project["id"], "T2")
        response = client.get(f"/projects/{project['id']}/tasks")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_update_task_returns_200(self, client):
        project = create_project(client)
        task = create_task(client, project["id"])
        response = client.put(
            f"/projects/{project['id']}/tasks/{task['id']}",
            json={"status": "In Progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "In Progress"

    def test_delete_task_returns_204(self, client):
        project = create_project(client)
        task = create_task(client, project["id"])
        response = client.delete(f"/projects/{project['id']}/tasks/{task['id']}")
        assert response.status_code == 204

    def test_update_unknown_task_returns_404(self, client):
        project = create_project(client)
        response = client.put(
            f"/projects/{project['id']}/tasks/9999",
            json={"status": "Completed"},
        )
        assert response.status_code == 404

    def test_delete_unknown_task_returns_404(self, client):
        project = create_project(client)
        response = client.delete(f"/projects/{project['id']}/tasks/9999")
        assert response.status_code == 404


class TestTaskOwnership:
    def test_update_task_through_wrong_project_returns_404(self, client):
        p1 = create_project(client, "Project 1")
        p2 = create_project(client, "Project 2")
        task = create_task(client, p1["id"], "Task in P1")
        response = client.put(
            f"/projects/{p2['id']}/tasks/{task['id']}",
            json={"status": "Completed"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Task not found"

    def test_delete_task_through_wrong_project_returns_404(self, client):
        p1 = create_project(client, "Project 1")
        p2 = create_project(client, "Project 2")
        task = create_task(client, p1["id"], "Task in P1")
        response = client.delete(f"/projects/{p2['id']}/tasks/{task['id']}")
        assert response.status_code == 404


class TestFiltering:
    def test_filter_by_status(self, client):
        project = create_project(client)
        create_task(client, project["id"], "T1", status="To Do")
        create_task(client, project["id"], "T2", status="In Progress")
        response = client.get(f"/projects/{project['id']}/tasks?status=To Do")
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["status"] == "To Do"

    def test_filter_by_priority(self, client):
        project = create_project(client)
        create_task(client, project["id"], "T1", priority="High")
        create_task(client, project["id"], "T2", priority="Low")
        response = client.get(f"/projects/{project['id']}/tasks?priority=High")
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["priority"] == "High"

    def test_filter_by_status_and_priority(self, client):
        project = create_project(client)
        create_task(client, project["id"], "T1", status="Completed", priority="High")
        create_task(client, project["id"], "T2", status="Completed", priority="Low")
        create_task(client, project["id"], "T3", status="To Do", priority="High")
        response = client.get(f"/projects/{project['id']}/tasks?status=Completed&priority=High")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_filter_invalid_status_returns_422(self, client):
        project = create_project(client)
        response = client.get(f"/projects/{project['id']}/tasks?status=Bogus")
        assert response.status_code == 422

    def test_filter_invalid_priority_returns_422(self, client):
        project = create_project(client)
        response = client.get(f"/projects/{project['id']}/tasks?priority=Bogus")
        assert response.status_code == 422


class TestValidation:
    def test_blank_project_name_returns_422(self, client):
        response = client.post("/projects", json={"name": ""})
        assert response.status_code == 422

    def test_whitespace_only_project_name_returns_422(self, client):
        response = client.post("/projects", json={"name": "   "})
        assert response.status_code == 422

    def test_blank_task_title_returns_422(self, client):
        project = create_project(client)
        response = client.post(f"/projects/{project['id']}/tasks", json={"title": ""})
        assert response.status_code == 422

    def test_whitespace_only_task_title_returns_422(self, client):
        project = create_project(client)
        response = client.post(f"/projects/{project['id']}/tasks", json={"title": "   "})
        assert response.status_code == 422

    def test_invalid_status_enum_returns_422(self, client):
        project = create_project(client)
        response = client.post(
            f"/projects/{project['id']}/tasks",
            json={"title": "T", "status": "Done"},
        )
        assert response.status_code == 422

    def test_invalid_priority_enum_returns_422(self, client):
        project = create_project(client)
        response = client.post(
            f"/projects/{project['id']}/tasks",
            json={"title": "T", "priority": "Urgent"},
        )
        assert response.status_code == 422

    def test_empty_project_update_body_returns_422(self, client):
        project = create_project(client)
        response = client.put(f"/projects/{project['id']}", json={})
        assert response.status_code == 422

    def test_empty_task_update_body_returns_422(self, client):
        project = create_project(client)
        task = create_task(client, project["id"])
        response = client.put(f"/projects/{project['id']}/tasks/{task['id']}", json={})
        assert response.status_code == 422

    def test_explicit_null_title_returns_422(self, client):
        project = create_project(client)
        task = create_task(client, project["id"])
        response = client.put(
            f"/projects/{project['id']}/tasks/{task['id']}",
            json={"title": None},
        )
        assert response.status_code == 422


class TestDefaults:
    def test_task_created_with_only_title_has_default_status_and_priority(self, client):
        project = create_project(client)
        task = create_task(client, project["id"], "Minimal Task")
        assert task["status"] == "To Do"
        assert task["priority"] == "Medium"


class TestSummary:
    def test_empty_database_returns_zeros(self, client):
        response = client.get("/tasks/summary")
        assert response.status_code == 200
        data = response.json()
        assert data == {"total_tasks": 0, "completed_tasks": 0, "pending_tasks": 0}

    def test_mixed_statuses_returns_correct_counts(self, client):
        project = create_project(client)
        create_task(client, project["id"], "T1", status="Completed")
        create_task(client, project["id"], "T2", status="In Progress")
        create_task(client, project["id"], "T3", status="To Do")
        response = client.get("/tasks/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_tasks"] == 3
        assert data["completed_tasks"] == 1
        assert data["pending_tasks"] == 2

    def test_summary_scoped_by_project_id(self, client):
        p1 = create_project(client, "P1")
        p2 = create_project(client, "P2")
        create_task(client, p1["id"], "T1", status="Completed")
        create_task(client, p1["id"], "T2", status="To Do")
        create_task(client, p2["id"], "T3", status="Completed")
        response = client.get(f"/tasks/summary?project_id={p1['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["total_tasks"] == 2
        assert data["completed_tasks"] == 1
        assert data["pending_tasks"] == 1

    def test_summary_unknown_project_id_returns_404(self, client):
        response = client.get("/tasks/summary?project_id=9999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"
