"""Gemeinsame Test-Fixtures.

Setzt Dummy-Konfiguration, BEVOR config.py importiert wird, damit keine echte
.env (mit echtem PAT) in die Tests einfliesst und kein Netzwerkzugriff passiert.
"""
import os
import sys
from pathlib import Path

os.environ["JIRA_PAT"] = "test-pat"
os.environ["JIRA_BASE_URL"] = "https://jira.example.test"
os.environ["JIRA_DEFAULT_PROJECT_KEY"] = "TEST"
os.environ["MCP_TRANSPORT"] = "http"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routes import register_routes  # noqa: E402


@pytest.fixture
def api() -> TestClient:
    app = FastAPI()
    register_routes(app)
    return TestClient(app)
