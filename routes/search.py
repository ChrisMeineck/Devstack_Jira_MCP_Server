"""JQL-Suche."""
import logging

from fastapi import APIRouter, HTTPException, Query

import client
from config import JIRA_BASE_URL, JIRA_DEFAULT_PROJECT_KEY

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Search"])


@router.get(
    "/search",
    summary="JQL-Suche ueber Jira-Issues",
    operation_id="search_issues",
)
async def search_issues(
    jql: str = Query(
        ...,
        description=(
            "Vollstaendige JQL-Query. "
            f"Beispiele: 'project = {JIRA_DEFAULT_PROJECT_KEY} AND status = Open', "
            f"'project = {JIRA_DEFAULT_PROJECT_KEY} AND assignee = currentUser()'. "
            f"Wenn kein Projekt angegeben ist, bevorzuge {JIRA_DEFAULT_PROJECT_KEY}."
        ),
    ),
    max_results: int = Query(25, ge=1, le=500, description="Maximalanzahl der Ergebnisse (1-500)"),
    start_at: int = Query(0, ge=0, description="Offset fuer Pagination"),
    fields: list[str] = Query(
        default=[],
        description="Optional: spezifische Jira-Felder. Leer = Standardfelder.",
        json_schema_extra={"items": {"type": "string"}},
    ),
):
    """Fuehrt eine JQL-Suche aus und liefert kompakte Issue-Ergebnisse."""
    field_list = fields or [
        "summary", "status", "issuetype", "assignee",
        "priority", "labels", "updated", "duedate",
    ]
    try:
        issues = client.get_jira_client().search_issues(
            jql_str=jql,
            startAt=start_at,
            maxResults=max_results,
            fields=",".join(field_list),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JQL-Fehler: {exc}")

    # jira-python liefert ResultList mit .total (Jiras tatsaechlicher Gesamtzaehler)
    jira_total = getattr(issues, "total", None)

    results = []
    for issue in issues:
        f = issue.fields
        results.append({
            "key": issue.key,
            "url": f"{JIRA_BASE_URL}/browse/{issue.key}",
            "summary": getattr(f, "summary", None),
            "status": getattr(f.status, "name", None) if getattr(f, "status", None) else None,
            "issuetype": getattr(f.issuetype, "name", None) if getattr(f, "issuetype", None) else None,
            "assignee": getattr(f.assignee, "displayName", None) if getattr(f, "assignee", None) else None,
            "priority": getattr(f.priority, "name", None) if getattr(f, "priority", None) else None,
            "labels": list(getattr(f, "labels", []) or []),
            "updated": getattr(f, "updated", None),
            "duedate": getattr(f, "duedate", None),
        })

    return {
        "jql": jql,
        "total": jira_total if jira_total is not None else len(results),
        "returned": len(results),
        "start_at": start_at,
        "max_results": max_results,
        "issues": results,
    }
