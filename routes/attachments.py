"""Attachment-Operationen: auflisten und herunterladen (Base64)."""
import base64
import logging

from fastapi import APIRouter, HTTPException

import client
from config import JIRA_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Attachments"])

# Begrenzung, damit wir nicht versehentlich riesige Dateien in den
# Chat-Response packen. Bei Bedarf erhoehen.
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.get(
    "/issues/{issue_key}/attachments",
    summary="Attachments eines Jira-Tickets auflisten",
    operation_id="list_attachments",
)
async def list_attachments(issue_key: str):
    try:
        issue = client.get_jira_client().issue(issue_key, fields="attachment")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Issue {issue_key} nicht gefunden: {exc}")

    attachments = getattr(issue.fields, "attachment", None) or []
    return {
        "issue": issue_key,
        "total": len(attachments),
        "attachments": [
            {
                "id": a.id,
                "filename": a.filename,
                "mime_type": getattr(a, "mimeType", None),
                "size": getattr(a, "size", None),
                "created": getattr(a, "created", None),
                "author": getattr(a.author, "displayName", None) if getattr(a, "author", None) else None,
                "content_url": getattr(a, "content", None),
            }
            for a in attachments
        ],
    }


@router.get(
    "/attachments/{attachment_id}",
    summary="Attachment-Inhalt als Base64 herunterladen",
    operation_id="download_attachment",
)
async def download_attachment(attachment_id: str):
    """
    Laedt das Attachment ueber die Jira-Standard-Route und gibt die Bytes
    Base64-kodiert zurueck. Datei wird auf MAX_DOWNLOAD_BYTES begrenzt.
    """
    meta_path = f"/rest/api/2/attachment/{attachment_id}"
    try:
        meta = client.request_json("GET", meta_path)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Attachment {attachment_id} nicht gefunden: {exc}")

    content_url = meta.get("content")
    if not content_url:
        raise HTTPException(status_code=500, detail="Attachment hat keine content-URL.")

    size = meta.get("size") or 0
    if size and size > MAX_DOWNLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment zu gross ({size} Bytes > Limit {MAX_DOWNLOAD_BYTES}).",
        )

    try:
        response = client.get_http_session().get(content_url, stream=True, timeout=60)
        response.raise_for_status()
        raw = response.content
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Download fehlgeschlagen: {exc}")

    if len(raw) > MAX_DOWNLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Heruntergeladene Datei ueberschreitet Limit ({len(raw)} > {MAX_DOWNLOAD_BYTES}).",
        )

    return {
        "id": attachment_id,
        "filename": meta.get("filename"),
        "mime_type": meta.get("mimeType"),
        "size": len(raw),
        "content_base64": base64.b64encode(raw).decode("ascii"),
        "source_url": content_url,
        "browse_url": f"{JIRA_BASE_URL}/secure/attachment/{attachment_id}/{meta.get('filename', '')}",
    }
