"""Kommentar-Operationen: lesen, hinzufuegen."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Comments"])


def _format_comment(c) -> dict:
    return {
        "id": getattr(c, "id", None),
        "author": getattr(c.author, "displayName", None) if getattr(c, "author", None) else None,
        "body": getattr(c, "body", ""),
        "created": getattr(c, "created", None),
        "updated": getattr(c, "updated", None),
    }


@router.get(
    "/issues/{issue_key}/comments",
    summary="Kommentare eines Jira-Tickets auflisten",
    operation_id="list_comments",
)
async def list_comments(issue_key: str):
    try:
        comments = client.get_jira_client().comments(issue_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Issue {issue_key} nicht gefunden: {exc}")
    return {
        "issue": issue_key,
        "total": len(comments),
        "comments": [_format_comment(c) for c in comments],
    }


class AddCommentRequest(BaseModel):
    body: str = Field(..., description="Kommentartext (Jira-Wiki-Markup)")


@router.post(
    "/issues/{issue_key}/comments",
    summary="Kommentar zu einem Jira-Ticket hinzufuegen",
    operation_id="add_comment",
)
async def add_comment(issue_key: str, payload: AddCommentRequest):
    try:
        comment = client.get_jira_client().add_comment(issue_key, payload.body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Kommentar konnte nicht hinzugefuegt werden: {exc}")
    return _format_comment(comment)
