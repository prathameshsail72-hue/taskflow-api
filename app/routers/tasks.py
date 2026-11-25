from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, Task, TaskPriority, TaskStatus
from app.routers.projects import get_project_or_404
from app.schemas import TaskCreate, TaskResponse, TaskSummaryResponse, TaskUpdate

router = APIRouter(prefix="/projects/{project_id}/tasks", tags=["Tasks"])

analytics_router = APIRouter(prefix="/tasks", tags=["Analytics"])


def get_task_or_404(db: Session, project_id: int, task_id: int) -> Task:
    task = db.scalar(
        select(Task).where(Task.id == task_id, Task.project_id == project_id)
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    description="Creates a new task under the specified project.",
    responses={
        404: {"description": "Project not found"},
        422: {"description": "Validation error"},
    },
)
def create_task(
    project_id: int, payload: TaskCreate, db: Session = Depends(get_db)
) -> Task:
    get_project_or_404(db, project_id)
    task = Task(project_id=project_id, **payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get(
    "",
    response_model=list[TaskResponse],
    summary="List tasks for a project",
    description="Returns all tasks for a project, with optional filtering by status and/or priority.",
    responses={404: {"description": "Project not found"}},
)
def list_tasks(
    project_id: int,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    db: Session = Depends(get_db),
) -> list[Task]:
    get_project_or_404(db, project_id)
    query = select(Task).where(Task.project_id == project_id).order_by(Task.id)
    if status is not None:
        query = query.where(Task.status == status)
    if priority is not None:
        query = query.where(Task.priority == priority)
    return list(db.scalars(query))


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update a task",
    description="Partially updates a task. Task must belong to the specified project.",
    responses={
        404: {"description": "Project not found or Task not found"},
        422: {"description": "Validation error"},
    },
)
def update_task(
    project_id: int,
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> Task:
    get_project_or_404(db, project_id)
    task = get_task_or_404(db, project_id, task_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Deletes a task. Task must belong to the specified project.",
    responses={404: {"description": "Project not found or Task not found"}},
)
def delete_task(
    project_id: int,
    task_id: int,
    db: Session = Depends(get_db),
) -> None:
    get_project_or_404(db, project_id)
    task = get_task_or_404(db, project_id, task_id)
    db.delete(task)
    db.commit()


@analytics_router.get(
    "/summary",
    response_model=TaskSummaryResponse,
    summary="Task summary statistics",
    description=(
        "Returns total, completed, and pending task counts. "
        "Optionally scope to a single project with ?project_id=. "
        "Returns 404 if the specified project does not exist."
    ),
    responses={404: {"description": "Project not found"}},
)
def task_summary(
    project_id: int | None = None,
    db: Session = Depends(get_db),
) -> TaskSummaryResponse:
    if project_id is not None:
        get_project_or_404(db, project_id)

    query = select(
        func.count(Task.id).label("total_tasks"),
        func.coalesce(
            func.sum(
                case(
                    (Task.status == TaskStatus.COMPLETED, 1),
                    else_=0,
                )
            ),
            0,
        ).label("completed_tasks"),
    )

    if project_id is not None:
        query = query.where(Task.project_id == project_id)

    row = db.execute(query).one()
    total = row.total_tasks
    completed = row.completed_tasks
    return TaskSummaryResponse(
        total_tasks=total,
        completed_tasks=completed,
        pending_tasks=total - completed,
    )
