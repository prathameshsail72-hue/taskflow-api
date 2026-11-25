from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.models import TaskPriority, TaskStatus

BoundedName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

BoundedTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

BoundedDescription = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, max_length=1000),
]


class ProjectCreate(BaseModel):
    name: BoundedName
    description: BoundedDescription = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Website Redesign",
                    "description": "Redesign the company website with a modern look.",
                }
            ]
        }
    )


class ProjectUpdate(BaseModel):
    name: BoundedName | None = None
    description: BoundedDescription = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Website Redesign v2",
                    "description": "Updated scope to include mobile-first design.",
                }
            ]
        }
    )

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "ProjectUpdate":
        if self.name is None and self.description is None:
            raise ValueError("At least one field must be provided for update.")
        return self


class TaskCreate(BaseModel):
    title: BoundedTitle
    description: BoundedDescription = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Design homepage mockup",
                    "description": "Create wireframes for the new homepage layout.",
                    "status": "To Do",
                    "priority": "High",
                }
            ]
        }
    )


class TaskUpdate(BaseModel):
    title: BoundedTitle | None = None
    description: BoundedDescription = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "In Progress",
                    "priority": "High",
                }
            ]
        }
    )

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "TaskUpdate":
        if (
            self.title is None
            and self.description is None
            and self.status is None
            and self.priority is None
        ):
            raise ValueError("At least one field must be provided for update.")
        return self


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime


class ProjectDetailResponse(ProjectResponse):
    tasks: list[TaskResponse]


class TaskSummaryResponse(BaseModel):
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
