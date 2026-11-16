"""Health- und Connection-Test-Endpunkte."""
import logging

from fastapi import APIRouter

import client
from config import JIRA_BASE_URL, JIRA_DEFAULT_PROJECT_KEY, JIRA_PAT

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health Check", operation_id="health_check")
async def health_check():
    return {
        "status": "healthy",
        "service": "devstack-jira-mcp",
        "version": "1.0.0",
        "base_url": JIRA_BASE_URL,
        "default_project_key": JIRA_DEFAULT_PROJECT_KEY,
        "pat_configured": bool(JIRA_PAT),
    }


@router.get(
    "/test_connection",
    summary="PAT + Erreichbarkeit pruefen (ruft /rest/api/2/myself)",
    operation_id="test_connection",
)
async def test_connection():
    if not JIRA_PAT:
        return {
            "status": "error",
            "stage": "config",
            "message": "JIRA_PAT ist nicht gesetzt. Bitte in .env hinterlegen.",
        }
    try:
        me = client.request_json("GET", "/rest/api/2/myself")
    except Exception as exc:
        return {
            "status": "error",
            "stage": "http",
            "base_url": JIRA_BASE_URL,
            "message": f"Jira-Request fehlgeschlagen: {exc}",
        }
    return {
        "status": "connected",
        "base_url": JIRA_BASE_URL,
        "user": {
            "name": me.get("name"),
            "displayName": me.get("displayName"),
            "emailAddress": me.get("emailAddress"),
            "active": me.get("active"),
        },
        "default_project_key": JIRA_DEFAULT_PROJECT_KEY,
    }
