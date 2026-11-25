# TaskFlow API

## 1. Project Overview

TaskFlow is a lightweight task management REST API built with FastAPI and SQLAlchemy 2.0. It lets you organize work into **projects**, each containing multiple **tasks**. Every task has a title, optional description, a status (`To Do`, `In Progress`, `Completed`), and a priority (`Low`, `Medium`, `High`). The API exposes full CRUD endpoints for both resources, supports filtering tasks by status and priority, and provides aggregate summary statistics via a dedicated analytics endpoint.

I designed TaskFlow to be small, readable, and completely explainable — a codebase a developer can walk through in a live interview with no surprises.

---

## 2. Features and Endpoint Table

| Method   | Path                                      | Success | Error Codes  |
|----------|-------------------------------------------|---------|--------------|
| `POST`   | `/projects`                               | 201     | 422          |
| `GET`    | `/projects`                               | 200     | —            |
| `GET`    | `/projects/{project_id}`                  | 200     | 404          |
| `PUT`    | `/projects/{project_id}`                  | 200     | 404, 422     |
| `DELETE` | `/projects/{project_id}`                  | 204     | 404          |
| `POST`   | `/projects/{project_id}/tasks`            | 201     | 404, 422     |
| `GET`    | `/projects/{project_id}/tasks`            | 200     | 404, 422     |
| `PUT`    | `/projects/{project_id}/tasks/{task_id}`  | 200     | 404, 422     |
| `DELETE` | `/projects/{project_id}/tasks/{task_id}`  | 204     | 404          |
| `GET`    | `/tasks/summary`                          | 200     | 404          |

**Task list query parameters:** `?status=To Do|In Progress|Completed` and `?priority=Low|Medium|High`. Both are optional and combinable. Invalid values return 422 automatically via FastAPI's enum validation.

**Summary query parameter:** `?project_id=<int>` (optional). Returns 404 if the project does not exist.

---

## 3. Architecture and Design Choices

### Layered structure

I separated the codebase into five layers: **config → database → models → schemas → routers**. Each layer depends only on layers below it. This makes the code easy to navigate: you change validation rules in `schemas.py`, database column definitions in `models.py`, and request handling in `routers/`. No layer does another layer's job.

### SQLAlchemy 2.0 typed models

I used `DeclarativeBase`, `Mapped[T]`, and `mapped_column` throughout. The 2.0 style makes column types visible in the class definition and gives IDE type-checking for free. The legacy `Query` API is completely absent; every query uses `select()` and `session.scalars()`.

### Pydantic schemas separate from ORM models

Pydantic schemas and SQLAlchemy models are intentionally different classes. ORM models are the source of truth for the database shape; schemas are the contract with API clients. Keeping them separate means I can evolve one without breaking the other, and I can apply different validation rules (e.g., `StringConstraints`) that make no sense on the ORM side.

### ORM cascade and SQLite foreign-key pragma

SQLAlchemy's `cascade="all, delete-orphan"` on the `Project.tasks` relationship handles cascade deletes at the ORM level. I also set `ondelete="CASCADE"` on the `Task.project_id` foreign key so the database enforces the constraint if rows are ever deleted without going through the ORM. For SQLite, `PRAGMA foreign_keys=ON` is required to activate foreign-key enforcement; I register a `connect` event listener in `build_engine` so it fires on every new connection, including connections from the test pool.

### Storing enum values

I configured the SQLAlchemy `Enum` with `values_callable=lambda e: [m.value for m in e]` and `native_enum=False`, so the database stores `"To Do"`, `"In Progress"`, and `"Completed"` rather than the Python member names `TODO`, `IN_PROGRESS`, `COMPLETED`. This keeps the database readable and decouples it from internal Python naming conventions.

### `StringConstraints` for whitespace rejection

Pydantic's `Field(min_length=1)` does not strip whitespace before checking length, so a name of `"   "` passes that check. I used `StringConstraints(strip_whitespace=True, min_length=1)` via the `Annotated` type alias `BoundedName` and `BoundedTitle`, which strips first and then validates length. This means `"   "` is correctly rejected with a 422.

### Task-ownership check via both IDs

The `get_task_or_404` helper filters on `Task.id == task_id AND Task.project_id == project_id`. This prevents a task from one project from being accidentally read, modified, or deleted through a URL belonging to a different project — an important correctness guarantee in a multi-project API.

### One-query aggregate for the summary

The `/tasks/summary` endpoint uses a single `SELECT count(*), coalesce(sum(case ... end), 0)` query. I never load task rows into Python and count them in a loop. `func.coalesce(..., 0)` ensures the sum is never `NULL` even when there are no tasks. `pending_tasks` is computed as `total - completed` so that "To Do" and "In Progress" are both counted as pending without a second conditional.

### Tables created at startup, no migrations

I call `Base.metadata.create_all(bind=engine)` in the FastAPI `lifespan` context manager. This is the right choice for a small, single-developer project: it is simple, requires no extra tooling, and is easy to explain. The trade-off is that it cannot perform schema migrations on an existing database. For production or a team environment, the next step would be to introduce **Alembic**: generate an initial migration from the current models, then manage every future schema change through versioned migration scripts.

### SQLite as the database

SQLite requires zero infrastructure — no server to start, no credentials to configure. For a REST API assessment that is evaluated in a fresh environment, this means `uvicorn app.main:app --reload` just works. The trade-off is that SQLite is not suitable for concurrent write-heavy workloads. The `DATABASE_URL` setting in `config.py` can be changed to a PostgreSQL or MySQL URL without touching any other file; the only SQLite-specific code is in `build_engine`.

### PUT with partial-update semantics

Both `PUT /projects/{id}` and `PUT /projects/{id}/tasks/{id}` use `model_dump(exclude_unset=True)` to apply only the fields the client actually sent. A client can update just the `status` without supplying `title`, `priority`, or `description`. A `model_validator(mode="after")` on each update schema enforces that at least one field is present, so an empty `{}` body is rejected with 422 rather than silently doing nothing.

---

## 4. Database Schema

```
projects
────────────────────────────────────────────────
id          INTEGER  PK  NOT NULL  (indexed)
name        TEXT(100)    NOT NULL
description TEXT(1000)   NULLABLE
created_at  DATETIME     NOT NULL  (timezone-aware UTC)

tasks
────────────────────────────────────────────────
id          INTEGER  PK  NOT NULL  (indexed)
project_id  INTEGER  FK → projects.id  NOT NULL  (indexed, CASCADE DELETE)
title       TEXT(200)    NOT NULL
description TEXT(1000)   NULLABLE
status      TEXT         NOT NULL  DEFAULT "To Do"
priority    TEXT         NOT NULL  DEFAULT "Medium"
created_at  DATETIME     NOT NULL  (timezone-aware UTC)
```

**ASCII ER diagram:**

```
┌───────────────────┐          ┌───────────────────────┐
│     projects      │          │        tasks          │
├───────────────────┤          ├───────────────────────┤
│ id (PK)           │◄────┐    │ id (PK)               │
│ name              │     └────│ project_id (FK)       │
│ description       │          │ title                 │
│ created_at        │          │ description           │
└───────────────────┘          │ status                │
                               │ priority              │
                               │ created_at            │
                               └───────────────────────┘
  One project has zero or many tasks (1 : N).
  Deleting a project cascades to all its tasks.
```

---

## 5. Local Setup

```bash
git clone <repo-url>
cd taskflow-api

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env

uvicorn app.main:app --reload
```

The SQLite database file `taskflow.db` is created automatically in the project root on first startup. It is listed in `.gitignore` and `.dockerignore`.

---

## 6. Using the API

Interactive docs are available at **[http://localhost:8000/docs](http://localhost:8000/docs)** (Swagger UI) and **[http://localhost:8000/redoc](http://localhost:8000/redoc)** (ReDoc).

### curl examples

**Create a project**
```bash
curl -s -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Website Redesign", "description": "New company site"}'
```

**Create a task**
```bash
curl -s -X POST http://localhost:8000/projects/1/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "Design homepage", "priority": "High"}'
```

**List tasks (with filtering)**
```bash
curl -s "http://localhost:8000/projects/1/tasks?status=To Do"
curl -s "http://localhost:8000/projects/1/tasks?priority=High"
curl -s "http://localhost:8000/projects/1/tasks?status=In Progress&priority=Medium"
```

**Update a task**
```bash
curl -s -X PUT http://localhost:8000/projects/1/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "Completed"}'
```

**Global summary**
```bash
curl -s http://localhost:8000/tasks/summary
```

**Summary scoped to a project**
```bash
curl -s "http://localhost:8000/tasks/summary?project_id=1"
```

**Delete a project (cascades to tasks)**
```bash
curl -s -X DELETE http://localhost:8000/projects/1
```

---

## 7. Running Tests

```bash
pytest -v
```

The test suite uses an in-memory SQLite database per test, so no external state is required and tests are fully isolated from each other.

---

## 8. Docker

**Build the image**
```bash
docker build -t taskflow-api .
```

**Run the container with a persistent volume**
```bash
docker run -p 8000:8000 -v taskflow-data:/app/data taskflow-api
```

The container runs as a non-root user (`taskflow`). The SQLite database is stored in `/app/data/taskflow.db` inside the container, persisted via the named volume.

---

## 9. Limitations and Next Steps

- **No authentication.** All endpoints are public. Adding OAuth 2 / JWT would be the first production step.
- **No pagination.** `GET /projects` and `GET /projects/{id}/tasks` return all rows. For large datasets, cursor-based or offset pagination is needed.
- **No schema migrations.** `create_all` is used at startup. Switching to **Alembic** would allow incremental, reversible schema changes without data loss.
- **SQLite concurrency.** SQLite handles concurrent reads well but serializes writes. For a multi-worker deployment, switch `DATABASE_URL` to PostgreSQL.

---

## 10. AI Assistance Disclosure

Google Antigravity was used to help scaffold this project and write the initial implementation and test code. I reviewed every file, ran the full test suite, and verified the server manually with curl. I understand and can explain every design decision documented above, including the SQLAlchemy 2.0 typed model syntax, the `StringConstraints` approach to whitespace validation, the single-query summary aggregate, and the trade-offs of using SQLite without Alembic.
