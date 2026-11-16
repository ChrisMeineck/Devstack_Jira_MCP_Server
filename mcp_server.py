"""devstack-jira-mcp Entry Point.

MCP-Server fuer https://devstack.vwgroup.com/jira (VW-Group-Jira).
Authentifiziert nur per Personal Access Token (PAT) - kein Zertifikat, kein Proxy.
"""
import logging

# Windows-Zertifikatsspeicher fuer TLS nutzen (Firmen-Proxy/TLS-Interception-CAs).
# Muss vor dem ersten Import von requests/jira erfolgen.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

import uvicorn
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

from config import JIRA_BASE_URL, JIRA_DEFAULT_PROJECT_KEY, MCP_PORT, MCP_TRANSPORT
from routes import register_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="devstack-jira-mcp",
    description=(
        f"MCP-Server fuer {JIRA_BASE_URL}. "
        f"Default-Projekt: {JIRA_DEFAULT_PROJECT_KEY}. "
        "Liefert Issue-, Search-, Comment- und Attachment-Tools fuer Copilot/Claude."
    ),
    version="1.0.0",
)

register_routes(app)

mcp = FastApiMCP(app)
if MCP_TRANSPORT == "stdio":
    mcp.mount()
else:
    mcp.mount_http()


if __name__ == "__main__":
    if MCP_TRANSPORT == "stdio":
        logger.info("Starte devstack-jira-mcp im stdio-Modus")
    else:
        logger.info("Starte devstack-jira-mcp auf http://localhost:%d", MCP_PORT)
        uvicorn.run(app, host="127.0.0.1", port=MCP_PORT, log_level="info")
