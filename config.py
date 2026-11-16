"""Konfiguration fuer den devstack-jira-mcp Server."""
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", "https://devstack.vwgroup.com/jira").rstrip("/")
JIRA_PAT: Optional[str] = os.getenv("JIRA_PAT") or None

# Hinweis: Wir validieren das Fehlen erst beim ersten echten API-Call (lazy),
# damit z.B. /health auch ohne PAT antwortet und der Nutzer eine klare
# Fehlermeldung sieht statt eines harten Crashes beim Importzeitpunkt.

JIRA_DEFAULT_PROJECT_KEY: str = os.getenv("JIRA_DEFAULT_PROJECT_KEY", "PPSE")

MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "http").lower()
MCP_PORT: int = int(os.getenv("MCP_PORT", "8766"))
JIRA_HTTP_TIMEOUT: int = int(os.getenv("JIRA_HTTP_TIMEOUT", "30"))
