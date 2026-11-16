"""Tests fuer /health und /test_connection."""
from unittest.mock import patch

import routes.health


def test_health_without_network(api):
    r = api.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["base_url"] == "https://jira.example.test"
    assert body["default_project_key"] == "TEST"
    assert body["pat_configured"] is True


def test_test_connection_ok(api):
    me = {"name": "P123456", "displayName": "Test, User", "emailAddress": "t@example.test", "active": True}
    with patch("client.request_json", return_value=me) as m:
        r = api.get("/test_connection")
    m.assert_called_once_with("GET", "/rest/api/2/myself")
    assert r.json()["status"] == "connected"
    assert r.json()["user"]["name"] == "P123456"


def test_test_connection_http_error(api):
    with patch("client.request_json", side_effect=RuntimeError("401 Unauthorized")):
        r = api.get("/test_connection")
    body = r.json()
    assert body["status"] == "error"
    assert body["stage"] == "http"
    assert "401" in body["message"]


def test_test_connection_without_pat(api, monkeypatch):
    monkeypatch.setattr(routes.health, "JIRA_PAT", None)
    r = api.get("/test_connection")
    assert r.json()["stage"] == "config"
