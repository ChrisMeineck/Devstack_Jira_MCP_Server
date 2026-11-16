"""Issue-Operationen: lesen, erstellen, aktualisieren, transitionieren."""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

import client
from config import JIRA_BASE_URL, JIRA_DEFAULT_PROJECT_KEY

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Issues"])


def _person(user) -> Optional[dict]:
    if not user:
        return None
    return {
        "name": getattr(user, "name", None) or getattr(user, "key", None),
        "displayName": getattr(user, "displayName", None),
        "emailAddress": getattr(user, "emailAddress", None),
    }


def _format_issue(issue) -> dict:
    f = issue.fields
    return {
        "key": issue.key,
        "id": issue.id,
        "url": f"{JIRA_BASE_URL}/browse/{issue.key}",
        "summary": f.summary,
        "description": f.description or "",
        "issuetype": getattr(f.issuetype, "name", None) if f.issuetype else None,
        "status": getattr(f.status, "name", None) if f.status else None,
        "priority": getattr(f.priority, "name", None) if getattr(f, "priority", None) else None,
        "resolution": getattr(f.resolution, "name", None) if getattr(f, "resolution", None) else None,
        "assignee": _person(getattr(f, "assignee", None)),
        "reporter": _person(getattr(f, "reporter", None)),
        "creator": _person(getattr(f, "creator", None)),
        "labels": list(getattr(f, "labels", []) or []),
        "components": [c.name for c in (getattr(f, "components", None) or [])],
        "fix_versions": [v.name for v in (getattr(f, "fixVersions", None) or [])],
        "affects_versions": [v.name for v in (getattr(f, "versions", None) or [])],
        "created": getattr(f, "created", None),
        "updated": getattr(f, "updated", None),
        "duedate": getattr(f, "duedate", None),
        "parent": (
            {"key": f.parent.key, "summary": getattr(f.parent.fields, "summary", None)}
            if getattr(f, "parent", None) else None
        ),
    }


# ----------------------------- READ -----------------------------

@router.get(
    "/issues/{issue_key}",
    summary="Jira-Ticket-Details abrufen",
    operation_id="get_issue",
)
async def get_issue(
    issue_key: str = Path(..., description=f"Issue-Key, z.B. {JIRA_DEFAULT_PROJECT_KEY}-123"),
):
    try:
        issue = client.get_jira_client().issue(issue_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Issue {issue_key} nicht gefunden: {exc}")
    return _format_issue(issue)


# ----------------------------- CREATE -----------------------------

class CreateIssueRequest(BaseModel):
    project_key: str = Field(
        default=JIRA_DEFAULT_PROJECT_KEY,
        description=f"Projektschluessel (Default: {JIRA_DEFAULT_PROJECT_KEY})",
    )
    summary: str = Field(..., description="Kurzer Titel des Tickets")
    description: str = Field("", description="Beschreibung (Wiki/Markdown laut Jira-Konfig)")
    issuetype: str = Field("Task", description="Issue-Typ (Task, Bug, Story, ...)")
    assignee: Optional[str] = Field(None, description="Username des Assignees (z.B. P123456)")
    labels: list[str] = Field(default_factory=list, description="Liste von Labels")
    components: list[str] = Field(default_factory=list, description="Liste von Component-Namen")
    parent_key: Optional[str] = Field(
        None,
        description="Optionaler Parent-Issue-Key (z.B. fuer Subtasks)",
    )


@router.post(
    "/issues",
    summary="Neues Jira-Ticket anlegen",
    operation_id="create_issue",
)
async def create_issue(payload: CreateIssueRequest):
    fields: Dict[str, Any] = {
        "project": {"key": payload.project_key},
        "summary": payload.summary,
        "description": payload.description,
        "issuetype": {"name": payload.issuetype},
    }
    if payload.assignee:
        fields["assignee"] = {"name": payload.assignee}
    if payload.labels:
        fields["labels"] = payload.labels
    if payload.components:
        fields["components"] = [{"name": c} for c in payload.components]
    if payload.parent_key:
        fields["parent"] = {"key": payload.parent_key}

    try:
        new_issue = client.get_jira_client().create_issue(fields=fields)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Anlage fehlgeschlagen: {exc}")

    return {
        "key": new_issue.key,
        "id": new_issue.id,
        "url": f"{JIRA_BASE_URL}/browse/{new_issue.key}",
    }


# ----------------------------- UPDATE -----------------------------

class UpdateIssueRequest(BaseModel):
    summary: Optional[str] = None
    description: Optional[str] = None
    assignee: Optional[str] = Field(None, description="Username oder leerer String zum Entziehen")
    # Listen-Felder: Standardwert None signalisiert "nicht aendern", leere Liste
    # wuerde die Werte loeschen. Wir nutzen eine Sentinel-Liste mit Default=None
    # ueber Optional, aber MIT explicit array-Schema durch list[str] | None.
    labels: Optional[list[str]] = Field(
        default=None,
        description="Komplette neue Label-Liste (ersetzt bestehende). Weglassen = nicht aendern.",
        json_schema_extra={"items": {"type": "string"}},
    )
    components: Optional[list[str]] = Field(
        default=None,
        description="Komplette neue Component-Liste. Weglassen = nicht aendern.",
        json_schema_extra={"items": {"type": "string"}},
    )
    priority: Optional[str] = Field(None, description="Prioritaetsname, z.B. 'High'")
    duedate: Optional[str] = Field(None, description="ISO-Datum YYYY-MM-DD")


@router.patch(
    "/issues/{issue_key}",
    summary="Felder eines Jira-Tickets aktualisieren",
    operation_id="update_issue",
)
async def update_issue(
    issue_key: str,
    payload: UpdateIssueRequest,
):
    fields: Dict[str, Any] = {}
    if payload.summary is not None:
        fields["summary"] = payload.summary
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.assignee is not None:
        fields["assignee"] = {"name": payload.assignee} if payload.assignee else None
    if payload.labels is not None:
        fields["labels"] = payload.labels
    if payload.components is not None:
        fields["components"] = [{"name": c} for c in payload.components]
    if payload.priority is not None:
        fields["priority"] = {"name": payload.priority}
    if payload.duedate is not None:
        fields["duedate"] = payload.duedate

    if not fields:
        raise HTTPException(status_code=400, detail="Keine Felder im Update angegeben.")

    try:
        issue = client.get_jira_client().issue(issue_key)
        issue.update(fields=fields)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Update fehlgeschlagen: {exc}")

    return _format_issue(client.get_jira_client().issue(issue_key))


# ----------------------------- TRANSITIONS -----------------------------

@router.get(
    "/issues/{issue_key}/transitions",
    summary="Verfuegbare Status-Transitions auflisten",
    operation_id="list_transitions",
)
async def list_transitions(issue_key: str):
    try:
        transitions = client.get_jira_client().transitions(issue_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Issue {issue_key} nicht gefunden: {exc}")
    return {
        "issue": issue_key,
        "transitions": [
            {"id": t["id"], "name": t["name"], "to": t.get("to", {}).get("name")}
            for t in transitions
        ],
    }


class TransitionRequest(BaseModel):
    transition_name: Optional[str] = Field(None, description="Name der Transition, z.B. 'In Progress'")
    transition_id: Optional[str] = Field(None, description="Alternativ: numerische Transition-ID")
    comment: Optional[str] = Field(None, description="Optionaler Kommentar beim Statuswechsel")


@router.post(
    "/issues/{issue_key}/transitions",
    summary="Jira-Ticket auf neuen Status setzen",
    operation_id="transition_issue",
)
async def transition_issue(issue_key: str, payload: TransitionRequest):
    if not payload.transition_name and not payload.transition_id:
        raise HTTPException(
            status_code=400,
            detail="Entweder transition_name oder transition_id angeben.",
        )

    jira = client.get_jira_client()
    try:
        transition_id = payload.transition_id
        if not transition_id:
            transitions = jira.transitions(issue_key)
            match = next(
                (t for t in transitions if t["name"].lower() == payload.transition_name.lower()),
                None,
            )
            if not match:
                available = [t["name"] for t in transitions]
                raise HTTPException(
                    status_code=400,
                    detail=f"Transition '{payload.transition_name}' nicht verfuegbar. Erlaubt: {available}",
                )
            transition_id = match["id"]

        kwargs: Dict[str, Any] = {}
        if payload.comment:
            kwargs["comment"] = payload.comment
        jira.transition_issue(issue_key, transition_id, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Transition fehlgeschlagen: {exc}")

    issue = jira.issue(issue_key)
    return {
        "issue": issue_key,
        "new_status": getattr(issue.fields.status, "name", None),
        "url": f"{JIRA_BASE_URL}/browse/{issue_key}",
    }
