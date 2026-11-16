"""Tests fuer die SRG- und GSEP-Auswertungen (Hilfsfunktionen + gemockte Endpunkte)."""
from unittest.mock import patch

import pytest

from routes import gsep, srg

# ----------------------------------------------------------------- Hilfsfunktionen


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0x13", "0013"), ("0626", "0626"), ("0x8146", "8146"), (" 8146 ", "8146"), ("abcd", "ABCD"),
     ("", None), (None, None), ("MRR", None), ("0x12345", None)],
)
def test_norm_diag(raw, expected):
    assert gsep.norm_diag(raw) == expected


def test_jql_quote_escapes():
    assert srg._jql_quote('a"b\\c') == '"a\\"b\\\\c"'
    assert srg._jql_in("cf[1]", ["x", "y"]) == 'cf[1] in ("x", "y")'


def test_checklist_ignores_headers_and_counts():
    items = [
        {"name": "Header", "isHeader": True},
        {"name": "A", "checked": True, "mandatory": True},
        {"name": "B", "checked": False, "mandatory": True},
        {"name": "B", "checked": False},
    ]
    res = srg._checklist(items, include_items=True)
    assert res["checked"] == 1
    assert res["total"] == 3
    assert res["open_mandatory"] == 1
    assert res["duplicate_items"] == 1
    assert len(res["items"]) == 3
    assert srg._checklist(None, include_items=False) is None


def test_simplify_values():
    assert srg._simplify({"value": "MRR"}) == "MRR"
    assert srg._simplify({"value": "A", "child": {"value": "B"}}) == "A / B"
    assert srg._simplify({"displayName": "Test, User", "name": "x"}) == "Test, User"
    assert srg._simplify("<p>Hallo <b>Welt</b></p>") == "Hallo Welt"
    assert srg._simplify([{"value": "x"}, {"value": "y"}]) == ["x", "y"]


def test_cat_summary():
    rows = [
        {"status": "Done", "status_category": "done"},
        {"status": "In Work", "status_category": "indeterminate"},
        {"status": "Open", "status_category": "new"},
        {"status": "Canceled", "status_category": "done"},
    ]
    assert gsep._cat_summary(rows) == {"total": 4, "done": 1, "in_progress": 1, "open": 1, "canceled": 1}


def test_row_flattens_aliases_and_links():
    issue = {
        "key": "GSEP-1",
        "fields": {
            "summary": "Radar (MRR)",
            "status": {"name": "Open", "statusCategory": {"key": "new"}},
            "fixVersions": [{"name": "PO616-K1"}],
            gsep.FIELD_ALIASES["diag_address"]: "0x13",
            gsep.FIELD_ALIASES["ecu"]: [{"value": "MRR"}],
            "issuelinks": [{"type": {"outward": "relates to", "inward": "relates to"},
                            "outwardIssue": {"key": "GSEP-2", "fields": {"issuetype": {"name": "Release"}}}}],
        },
    }
    row = gsep._row(issue, ["summary", "status", "fixVersions", "diag_address", "ecu", "issuelinks"])
    assert row["status"] == "Open"
    assert row["fix_versions"] == ["PO616-K1"]
    assert row["diag_address_norm"] == "0013"
    assert row["ecu"] == ["MRR"]
    assert row["links"][0] == {"key": "GSEP-2", "direction": "relates to", "issuetype": "Release",
                               "status": None, "summary": None}


def test_matched_by():
    info = {"ecu_values": ["MRR"], "diag_address": "0013", "text": "MRR"}
    row = {"ecu": ["MRR"], "diag_address_norm": "0013", "summary": "Radar (MRR)"}
    assert gsep._matched_by(row, "MRR", info) == ["corresponding_ecu", "diag_address", "summary"]
    assert gsep._matched_by({"summary": "x"}, "MRR", {"ecu_values": [], "diag_address": None}) == ["fulltext"]


def test_search_all_paginates():
    pages = [
        {"total": 3, "issues": [{"key": "A"}, {"key": "B"}]},
        {"total": 3, "issues": [{"key": "C"}]},
    ]
    with patch("client.request_json", side_effect=pages) as m:
        issues, total = srg._search_all("project = GSEP", "summary", 10)
    assert [i["key"] for i in issues] == ["A", "B", "C"]
    assert total == 3
    assert m.call_args_list[1].kwargs["params"]["startAt"] == 2


# ----------------------------------------------------------------- Endpunkte

def test_srg_lookup_unknown_field(api):
    r = api.get("/srg/lookup", params={"field": "unbekannt"})
    assert r.status_code == 400


def test_srg_lookup_autocomplete_strips_quotes(api):
    res = {"results": [{"value": '"MRR"'}, {"value": "SRR"}]}
    with patch("client.request_json", return_value=res):
        r = api.get("/srg/lookup", params={"field": "ecu", "query": "rr"})
    assert r.json()["values"] == ["MRR", "SRR"]


def test_gsep_search_group_by(api):
    page = {"total": 2, "issues": [
        {"key": "GSEP-1", "fields": {"status": {"name": "Open", "statusCategory": {"key": "new"}}}},
        {"key": "GSEP-2", "fields": {"status": {"name": "Open", "statusCategory": {"key": "new"}}}},
    ]}
    with patch("client.request_json", return_value=page):
        r = api.get("/gsep/search", params={"jql": "project = GSEP", "group_by": "status", "rows": "false"})
    body = r.json()
    assert body["groups"] == {"Open": 2}
    assert body["rows"] is None
    assert body["truncated"] is False


def test_get_issue_fields_uses_names(api):
    data = {"key": "GSEP-1", "names": {"customfield_1": "Corresponding ECU"},
            "fields": {"customfield_1": [{"value": "MRR"}], "comment": {"x": 1}, "empty": None}}
    with patch("client.request_json", return_value=data):
        r = api.get("/issues/GSEP-1/fields")
    assert r.json()["fields"] == {"Corresponding ECU": ["MRR"]}
