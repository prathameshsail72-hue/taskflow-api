from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.config import get_settings
from app.database import Base, engine
from app.routers import projects, tasks

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "**TaskFlow** is a lightweight task management REST API.\n\n"
        "Manage projects and their tasks with full CRUD operations, "
        "status/priority filtering, and aggregate summary statistics."
    ),
    openapi_tags=[
        {
            "name": "Projects",
            "description": "Create and manage projects. Each project can contain many tasks.",
        },
        {
            "name": "Tasks",
            "description": "Create and manage tasks within a project. Supports filtering by status and priority.",
        },
        {
            "name": "Analytics",
            "description": "Aggregate statistics across all tasks or scoped to a single project.",
        },
    ],
    lifespan=lifespan,
)

app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(tasks.analytics_router)
