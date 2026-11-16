"""Routen-Registrierung fuer den devstack-jira-mcp Server."""
from fastapi import FastAPI

from routes.attachments import router as attachments_router
from routes.comments import router as comments_router
from routes.gsep import router as gsep_router
from routes.health import router as health_router
from routes.issues import router as issues_router
from routes.search import router as search_router
from routes.srg import router as srg_router


def register_routes(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(issues_router)
    app.include_router(search_router)
    app.include_router(comments_router)
    app.include_router(attachments_router)
    app.include_router(srg_router)
    app.include_router(gsep_router)
