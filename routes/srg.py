"""Nur-Lese-Tools fuer Security-Reifegrad-Tickets (SRG0..SRG4) im GSEP-Jira.

Datenmodell (GSEP, verifiziert 19.10.2026):
  Measure (issuetype "Measure", Mutterticket je Steuergeraet + Standardmassnahme)
    └─ Sub-task je Reifegrad "<Massnahme> (SRGx) - <ECUs>"  (per Automation angelegt)
         Feld "Maturity Level" = SRG0..SRG4, Feld "ToDo-List" = Checkliste

Filterfelder (ECU, Standard Measure, Fix Version, Vehicle Architecture, Lead Brand)
werden auf dem Measure ausgewertet und die SRG-Sub-tasks anschliessend per
`parent in (...)` nachgeladen. Alle Endpunkte sind reine GET-Abfragen.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

import client
from config import JIRA_BASE_URL

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Security Reifegrade"])

# Custom-Field-IDs im devstack-Jira (per /rest/api/2/issue/<key>?expand=names ermittelt)
CF = {
    "todo": "customfield_12800",            # ToDo-List (Checkliste)
    "maturity": "customfield_13302",        # Maturity Level (SRG0..SRG4)
    "ecu": "customfield_49807",             # Corresponding ECU (Multi-Select)
    "std_measure": "customfield_20319",     # Standard Measure (Multi-Checkbox)
    "veh_arch": "customfield_19601",        # Vehicle Architecture (Multi-Select)
    "cluster": "customfield_18401",         # Cluster (Select)
    "lead_brand": "customfield_12861",      # Lead Brand (Select)
    "status_reasoning": "customfield_20314",
    "further_info": "customfield_13317",
    "ecu_owner": "customfield_20333",
    "last_comment": "customfield_19508",    # HTML
}
SRG_LEVELS = ("SRG0", "SRG1", "SRG2", "SRG3", "SRG4")

MEASURE_FIELDS = ",".join([
    "summary", "status", "resolution", "fixVersions", "assignee", "updated",
    CF["ecu"], CF["std_measure"], CF["veh_arch"], CF["cluster"], CF["lead_brand"],
    CF["status_reasoning"], CF["further_info"], CF["ecu_owner"],
])
SRG_FIELDS = ",".join([
    "summary", "status", "resolution", "parent", "updated", "assignee",
    CF["maturity"], CF["todo"], CF["last_comment"],
])

_TAG_RE = re.compile(r"<[^>]+>")


# ----------------------------------------------------------------- Helfer

def _jql_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _jql_in(field: str, values: list[str]) -> str:
    return f"{field} in ({', '.join(_jql_quote(v) for v in values)})"


def _search_all(jql: str, fields: str, limit: int) -> tuple[list[dict], int]:
    """Paginierte Suche ueber die REST-API. Gibt (issues, jira_total) zurueck."""
    issues: list[dict] = []
    start, total = 0, 0
    while len(issues) < limit:
        page = client.request_json(
            "GET", "/rest/api/2/search",
            params={"jql": jql, "fields": fields, "startAt": start,
                    "maxResults": min(500, limit - len(issues))},
        )
        total = page.get("total", 0)
        batch = page.get("issues", [])
        issues.extend(batch)
        start += len(batch)
        if not batch or start >= total:
            break
    return issues, total


def _opt(v: Any) -> Optional[str]:
    return v.get("value") if isinstance(v, dict) else None


def _opts(v: Any) -> list[str]:
    return [x.get("value") for x in (v or []) if isinstance(x, dict) and x.get("value")]


def _html_to_text(s: Optional[str], limit: int = 400) -> Optional[str]:
    if not s:
        return None
    t = re.sub(r"\s+", " ", _TAG_RE.sub(" ", s)).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _status(f: dict) -> dict:
    st = f.get("status") or {}
    return {
        "status": st.get("name"),
        "status_category": (st.get("statusCategory") or {}).get("key"),  # new | indeterminate | done
        "resolution": (f.get("resolution") or {}).get("name"),
    }


def _checklist(items: Any, include_items: bool) -> Optional[dict]:
    """Wertet eine Checklist-Liste (ToDo-List) aus. Header-Zeilen zaehlen nicht mit."""
    if not isinstance(items, list):
        return None
    rows = [i for i in items if isinstance(i, dict) and not i.get("isHeader")]
    names = [r.get("name", "") for r in rows]
    result = {
        "checked": sum(1 for r in rows if r.get("checked")),
        "total": len(rows),
        "open_mandatory": sum(1 for r in rows if r.get("mandatory") and not r.get("checked")),
        "duplicate_items": len(names) - len(set(names)),
    }
    if include_items:
        result["items"] = [
            {"name": r.get("name"), "checked": bool(r.get("checked")),
             "mandatory": bool(r.get("mandatory"))}
            for r in rows
        ]
    return result


# ----------------------------------------------------------------- srg_status

@router.get(
    "/srg/status",
    summary="Security-Reifegrad-Status (SRG0-SRG4) je Massnahme/Steuergeraet inkl. ToDo-Checkboxen",
    operation_id="srg_status",
)
def srg_status(
    ecu: list[str] = Query(default=[], description="Corresponding ECU, exakte Werte (z.B. TSG_FS). Werte vorher mit srg_lookup pruefen.", json_schema_extra={"items": {"type": "string"}}),
    standard_measure: list[str] = Query(default=[], description="Standard Measure, exakte Werte (z.B. 'VKMS (Folgemaßnahme)', 'SOK').", json_schema_extra={"items": {"type": "string"}}),
    fix_version: list[str] = Query(default=[], description="Fix Version = Baureihe/Projekt, exakte Werte (z.B. 'PO616-K1').", json_schema_extra={"items": {"type": "string"}}),
    vehicle_architecture: list[str] = Query(default=[], description="Vehicle Architecture, exakte Werte (z.B. 'SDV-0.1 (P1)').", json_schema_extra={"items": {"type": "string"}}),
    lead_brand: list[str] = Query(default=[], description="Lead Brand (z.B. Porsche, Audi, VW).", json_schema_extra={"items": {"type": "string"}}),
    measure_keys: list[str] = Query(default=[], description="Optional: konkrete Measure-Keys (z.B. GSEP-5346).", json_schema_extra={"items": {"type": "string"}}),
    include_todo_items: bool = Query(True, description="ToDo-Punkte einzeln mit checked/mandatory ausgeben (sonst nur Zaehler)."),
    include_canceled: bool = Query(False, description="Auch Measures im Status 'Canceled' beruecksichtigen."),
    max_measures: int = Query(100, ge=1, le=2000, description="Maximalanzahl Measures (Schutz vor zu grossen Antworten)."),
    project_key: str = Query("GSEP", description="Jira-Projekt"),
):
    """Liefert je Measure die fuenf SRG-Sub-tasks mit Status und ToDo-Checkbox-Stati.

    Abgeleitete Kennzahl `closed_consecutive_up_to`: hoechster Reifegrad, bis zu dem
    alle SRG-Tickets ab SRG0 lueckenlos im Status-Kategorie 'done' sind (rein formal
    aus Jira abgeleitet, keine fachliche Bewertung).
    """
    clauses = [f"project = {_jql_quote(project_key)}", "issuetype = Measure"]
    if ecu:
        clauses.append(_jql_in(f"cf[{CF['ecu'].split('_')[1]}]", ecu))
    if standard_measure:
        clauses.append(_jql_in(f"cf[{CF['std_measure'].split('_')[1]}]", standard_measure))
    if fix_version:
        clauses.append(_jql_in("fixVersion", fix_version))
    if vehicle_architecture:
        clauses.append(_jql_in(f"cf[{CF['veh_arch'].split('_')[1]}]", vehicle_architecture))
    if lead_brand:
        clauses.append(_jql_in(f"cf[{CF['lead_brand'].split('_')[1]}]", lead_brand))
    if measure_keys:
        clauses.append(f"key in ({', '.join(measure_keys)})")
    if not include_canceled:
        clauses.append("status != Canceled")
    jql = " AND ".join(clauses) + " ORDER BY key"

    try:
        measures_raw, measures_total = _search_all(jql, MEASURE_FIELDS, max_measures)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JQL-Fehler (Measures): {exc}\nJQL: {jql}")

    # SRG-Sub-tasks in Bloecken nachladen
    by_parent: dict[str, list[dict]] = {}
    keys = [m["key"] for m in measures_raw]
    for i in range(0, len(keys), 80):
        chunk = keys[i:i + 80]
        sub_jql = (f"parent in ({', '.join(chunk)}) AND cf[{CF['maturity'].split('_')[1]}] is not EMPTY")
        try:
            subs, _ = _search_all(sub_jql, SRG_FIELDS, 80 * 10)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"JQL-Fehler (SRG-Sub-tasks): {exc}")
        for s in subs:
            parent = (s["fields"].get("parent") or {}).get("key")
            if parent:
                by_parent.setdefault(parent, []).append(s)

    measures: list[dict] = []
    agg = {lvl: {"tickets": 0, "status": {}, "todo_checked": 0, "todo_total": 0} for lvl in SRG_LEVELS}
    without_srg = 0
    warnings: list[str] = []

    for m in measures_raw:
        f = m["fields"]
        srg: dict[str, Any] = {lvl: None for lvl in SRG_LEVELS}
        for s in by_parent.get(m["key"], []):
            sf = s["fields"]
            lvl = _opt(sf.get(CF["maturity"]))
            if lvl not in srg:
                warnings.append(f"{s['key']}: unbekannter Maturity Level '{lvl}'")
                continue
            if srg[lvl] is not None:
                warnings.append(f"{m['key']}: mehrere Tickets fuer {lvl} ({srg[lvl]['key']}, {s['key']})")
                continue
            todo = _checklist(sf.get(CF["todo"]), include_todo_items)
            srg[lvl] = {
                "key": s["key"],
                "url": f"{JIRA_BASE_URL}/browse/{s['key']}",
                "summary": sf.get("summary"),
                **_status(sf),
                "updated": sf.get("updated"),
                "assignee": (sf.get("assignee") or {}).get("displayName"),
                "todo": todo,
                "last_comment": _html_to_text(sf.get(CF["last_comment"])),
            }
            a = agg[lvl]
            a["tickets"] += 1
            st = srg[lvl]["status"] or "?"
            a["status"][st] = a["status"].get(st, 0) + 1
            if todo:
                a["todo_checked"] += todo["checked"]
                a["todo_total"] += todo["total"]

        found = sum(1 for v in srg.values() if v)
        if found == 0:
            without_srg += 1
        closed_up_to = None
        for lvl in SRG_LEVELS:
            if srg[lvl] and srg[lvl]["status_category"] == "done":
                closed_up_to = lvl
            else:
                break

        measures.append({
            "key": m["key"],
            "url": f"{JIRA_BASE_URL}/browse/{m['key']}",
            "summary": f.get("summary"),
            **_status(f),
            "standard_measure": _opts(f.get(CF["std_measure"])),
            "ecus": _opts(f.get(CF["ecu"])),
            "fix_versions": [v.get("name") for v in (f.get("fixVersions") or [])],
            "vehicle_architecture": _opts(f.get(CF["veh_arch"])),
            "cluster": _opt(f.get(CF["cluster"])),
            "lead_brand": _opt(f.get(CF["lead_brand"])),
            "ecu_owner": f.get(CF["ecu_owner"]),
            "further_information": f.get(CF["further_info"]),
            "status_reasoning": f.get(CF["status_reasoning"]),
            "assignee": (f.get("assignee") or {}).get("displayName"),
            "updated": f.get("updated"),
            "srg_tickets_found": found,
            "closed_consecutive_up_to": closed_up_to,
            "srg": srg,
        })

    return {
        "jql": jql,
        "measures_total_in_jira": measures_total,
        "measures_returned": len(measures),
        "truncated": measures_total > len(measures),
        "measures_without_srg_tickets": without_srg,
        "aggregate_per_srg": agg,
        "warnings": warnings,
        "measures": measures,
    }


# ----------------------------------------------------------------- srg_lookup

_LOOKUP_FIELDS = {
    "ecu": CF["ecu"],
    "standard_measure": CF["std_measure"],
    "vehicle_architecture": CF["veh_arch"],
    "lead_brand": CF["lead_brand"],
    "cluster": CF["cluster"],
}


def _norm(s: str) -> str:
    return re.sub(r"[\s\-_/().]+", "", s.lower())


@router.get(
    "/srg/lookup",
    summary="Gueltige Filterwerte finden (ECU, Fix Version/Baureihe, Standard Measure, ...)",
    operation_id="srg_lookup",
)
def srg_lookup(
    field: str = Query(..., description="ecu | fix_version | standard_measure | vehicle_architecture | lead_brand | cluster"),
    query: str = Query("", description="Suchtext (Teilstring, Gross/Klein und Leer-/Bindestriche egal)"),
    project_key: str = Query("GSEP", description="Jira-Projekt (nur fuer fix_version)"),
):
    """Liefert exakte Jira-Werte, die in srg_status als Filter verwendet werden koennen."""
    q = _norm(query)
    if field == "fix_version":
        try:
            versions = client.request_json("GET", f"/rest/api/2/project/{project_key}/versions")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Versionen nicht lesbar: {exc}")
        hits = [
            {"value": v.get("name"), "released": v.get("released"), "archived": v.get("archived")}
            for v in versions if not q or q in _norm(v.get("name", ""))
        ]
        return {"field": field, "query": query, "count": len(hits), "values": hits}

    if field not in _LOOKUP_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unbekanntes Feld '{field}'. Erlaubt: fix_version, {', '.join(_LOOKUP_FIELDS)}")

    # Vollstaendige Werteliste ueber editmeta eines Measures bzw. SRG-Tickets ist nicht
    # stabil verfuegbar -> JQL-Autocomplete (liefert max. ~15 Treffer je Anfrage).
    cf_id = _LOOKUP_FIELDS[field].split("_")[1]
    try:
        res = client.request_json(
            "GET", "/rest/api/2/jql/autocompletedata/suggestions",
            params={"fieldName": f"cf[{cf_id}]", "fieldValue": query},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Autocomplete fehlgeschlagen: {exc}")
    values = []
    for r in res.get("results", []):
        v = (r.get("value") or "").strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1].replace('\\"', '"')
        values.append(v)
    return {
        "field": field, "query": query, "count": len(values), "values": values,
        "hinweis": "Autocomplete liefert nur die ersten Treffer; bei vielen Treffern Suchtext verfeinern.",
    }


# ----------------------------------------------------------------- get_issue_fields

def _simplify(v: Any) -> Any:
    if isinstance(v, list):
        if v and all(isinstance(x, dict) and "checked" in x for x in v):
            return [{"name": x.get("name"), "checked": bool(x.get("checked")),
                     "mandatory": bool(x.get("mandatory"))}
                    for x in v if not x.get("isHeader")]
        return [_simplify(x) for x in v]
    if isinstance(v, dict):
        if "value" in v:
            child = v.get("child")
            return f"{v['value']} / {child.get('value')}" if isinstance(child, dict) else v["value"]
        if "displayName" in v:
            return v["displayName"]
        if "name" in v:
            return v["name"]
        if "key" in v:
            return v["key"]
        return {k: _simplify(x) for k, x in v.items() if k not in ("self", "avatarUrls", "iconUrl")}
    if isinstance(v, str):
        if "<" in v and ">" in v:
            v = _html_to_text(v, 2000) or ""
        return v[:4000]
    return v


@router.get(
    "/issues/{issue_key}/fields",
    summary="Alle befuellten Felder eines Tickets inkl. Custom Fields (Klartext-Namen, Checklisten)",
    operation_id="get_issue_fields",
)
def get_issue_fields(issue_key: str):
    try:
        data = client.request_json("GET", f"/rest/api/2/issue/{issue_key}", params={"expand": "names"})
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Issue {issue_key} nicht lesbar: {exc}")
    names = data.get("names", {})
    skip = {"comment", "worklog", "attachment", "watches", "votes", "timetracking",
            "aggregateprogress", "progress", "thumbnail", "lastViewed", "customfield_10005"}
    fields = {}
    for fid, val in data.get("fields", {}).items():
        if fid in skip or val in (None, "", [], {}, "{}"):
            continue
        fields[names.get(fid, fid)] = _simplify(val)
    return {"key": data.get("key"), "url": f"{JIRA_BASE_URL}/browse/{data.get('key')}", "fields": fields}
