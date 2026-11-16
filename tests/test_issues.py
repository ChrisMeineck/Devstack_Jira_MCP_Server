"""Tests fuer Issue-, Search-, Comment- und Attachment-Endpunkte (Jira gemockt)."""
import base64
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import routes.attachments


def _issue(key="TEST-1", status="Open"):
    fields = NS(
        summary="Titel", description=None, issuetype=NS(name="Task"), status=NS(name=status),
        priority=NS(name="High"), resolution=None, assignee=NS(name="P123456", displayName="Test, User"),
        reporter=None, creator=None, labels=["a"], components=[NS(name="Comp")],
        fixVersions=[NS(name="V1")], versions=[], created="2026-01-01", updated="2026-01-02",
        duedate=None, parent=None,
    )
    return NS(key=key, id="10001", fields=fields)


# ----------------------------------------------------------------- issues

def test_get_issue_formats_fields(api):
    jira = MagicMock()
    jira.issue.return_value = _issue()
    with patch("client.get_jira_client", return_value=jira):
        r = api.get("/issues/TEST-1")
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "TEST-1"
    assert body["url"] == "https://jira.example.test/browse/TEST-1"
    assert body["status"] == "Open"
    assert body["components"] == ["Comp"]
    assert body["assignee"]["name"] == "P123456"
    assert body["description"] == ""


def test_get_issue_not_found(api):
    jira = MagicMock()
    jira.issue.side_effect = RuntimeError("404")
    with patch("client.get_jira_client", return_value=jira):
        r = api.get("/issues/TEST-404")
    assert r.status_code == 404


def test_create_issue_builds_fields(api):
    jira = MagicMock()
    jira.create_issue.return_value = NS(key="TEST-2", id="10002")
    with patch("client.get_jira_client", return_value=jira):
        r = api.post("/issues", json={"summary": "Neu", "labels": ["x"], "parent_key": "TEST-1"})
    assert r.status_code == 200
    assert r.json()["key"] == "TEST-2"
    fields = jira.create_issue.call_args.kwargs["fields"]
    assert fields["project"] == {"key": "TEST"}
    assert fields["issuetype"] == {"name": "Task"}
    assert fields["labels"] == ["x"]
    assert fields["parent"] == {"key": "TEST-1"}
    assert "assignee" not in fields


def test_update_issue_without_fields_is_400(api):
    r = api.patch("/issues/TEST-1", json={})
    assert r.status_code == 400


def test_update_issue_sets_fields(api):
    issue = _issue()
    issue.update = MagicMock()
    jira = MagicMock()
    jira.issue.return_value = issue
    with patch("client.get_jira_client", return_value=jira):
        r = api.patch("/issues/TEST-1", json={"summary": "Neu", "assignee": ""})
    assert r.status_code == 200
    issue.update.assert_called_once_with(fields={"summary": "Neu", "assignee": None})


def test_transition_by_name(api):
    jira = MagicMock()
    jira.transitions.return_value = [{"id": "11", "name": "In Progress"}]
    jira.issue.return_value = _issue(status="In Progress")
    with patch("client.get_jira_client", return_value=jira):
        r = api.post("/issues/TEST-1/transitions", json={"transition_name": "in progress", "comment": "go"})
    assert r.status_code == 200
    jira.transition_issue.assert_called_once_with("TEST-1", "11", comment="go")
    assert r.json()["new_status"] == "In Progress"


def test_transition_unknown_name(api):
    jira = MagicMock()
    jira.transitions.return_value = [{"id": "11", "name": "In Progress"}]
    with patch("client.get_jira_client", return_value=jira):
        r = api.post("/issues/TEST-1/transitions", json={"transition_name": "Done"})
    assert r.status_code == 400
    assert "In Progress" in r.json()["detail"]


def test_transition_requires_name_or_id(api):
    r = api.post("/issues/TEST-1/transitions", json={})
    assert r.status_code == 400


# ----------------------------------------------------------------- search

def test_search_issues(api):
    result = MagicMock()
    result.__iter__.return_value = iter([_issue("TEST-1"), _issue("TEST-2")])
    result.total = 42
    jira = MagicMock()
    jira.search_issues.return_value = result
    with patch("client.get_jira_client", return_value=jira):
        r = api.get("/search", params={"jql": "project = TEST", "max_results": 2})
    body = r.json()
    assert body["total"] == 42
    assert body["returned"] == 2
    assert [i["key"] for i in body["issues"]] == ["TEST-1", "TEST-2"]


def test_search_jql_error(api):
    jira = MagicMock()
    jira.search_issues.side_effect = RuntimeError("bad jql")
    with patch("client.get_jira_client", return_value=jira):
        r = api.get("/search", params={"jql": "kaputt"})
    assert r.status_code == 400


# ----------------------------------------------------------------- comments

def test_list_and_add_comments(api):
    c = NS(id="1", author=NS(displayName="Test, User"), body="Hallo", created="c", updated="u")
    jira = MagicMock()
    jira.comments.return_value = [c]
    jira.add_comment.return_value = c
    with patch("client.get_jira_client", return_value=jira):
        r1 = api.get("/issues/TEST-1/comments")
        r2 = api.post("/issues/TEST-1/comments", json={"body": "Hallo"})
    assert r1.json()["total"] == 1
    assert r1.json()["comments"][0]["author"] == "Test, User"
    assert r2.json()["body"] == "Hallo"
    jira.add_comment.assert_called_once_with("TEST-1", "Hallo")


# ----------------------------------------------------------------- attachments

def test_download_attachment_base64(api):
    meta = {"content": "https://jira.example.test/secure/attachment/5/a.txt", "filename": "a.txt", "size": 3}
    resp = MagicMock(content=b"abc")
    session = MagicMock()
    session.get.return_value = resp
    with patch("client.request_json", return_value=meta), patch("client.get_http_session", return_value=session):
        r = api.get("/attachments/5")
    assert r.status_code == 200
    assert base64.b64decode(r.json()["content_base64"]) == b"abc"


def test_download_attachment_too_large(api):
    meta = {"content": "https://x", "filename": "big.bin", "size": routes.attachments.MAX_DOWNLOAD_BYTES + 1}
    with patch("client.request_json", return_value=meta):
        r = api.get("/attachments/6")
    assert r.status_code == 413
