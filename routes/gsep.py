"""Nur-Lese-Tools fuer GSEP-Auswertungen: Steuergeraet finden, Prozessdurchlauf, Massnahmen, Bulk-Suche, Link-Graph.

GSEP-Ticketstruktur (verifiziert 05.11.2026, alles ueber Issue-Links, NICHT parent/subtask):

  Control Units / Use Case / Function   (Muttertickets)
    ├─ Correlates To  -> Security Relevance ("Preliminary Security Estimation")
    ├─ relates to     -> Risk Analysis, Security Concept, Security Specification,
    │                    Carry Over Status, Delta and Impact Analysis
    └─ relates to     -> Release ("Security Release Recommendation", je Fix Version/Cluster)
                           ├─ relates to -> Measure (je Standard Measure)
                           │                  ├─ relates to -> Test Tracking
                           │                  └─ Sub-tasks SRG0..SRG4 (Feld Maturity Level)
                           ├─ relates to -> Test Plan
                           └─ relates to -> Final Risks & Security Risk Acceptance
  Change Management: "is original of"/"is clone of" zwischen Muttertickets.

Join-Schluessel Steuergeraet: Diagnostic address (customfield_21627, z.B. "0626"/"0x8146"),
Corresponding ECU (customfield_49807, z.B. "MRR"), Kuerzel in Klammern im Summary.
Alle Endpunkte sind reine GET-Abfragen.
"""
from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

import client
from config import JIRA_BASE_URL
from routes.srg import (
    CF as SRG_CF,
)
from routes.srg import (
    SRG_FIELDS,
    SRG_LEVELS,
    _checklist,
    _jql_quote,
    _opt,
    _search_all,
    _simplify,
    _status,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["GSEP Auswertung"])

# ----------------------------------------------------------------- Feldmodell

FIELD_ALIASES: dict[str, str] = {
    "ecu": "customfield_49807",                 # Corresponding ECU (Multi-Select)
    "diag_address": "customfield_21627",        # Diagnostic address (Text)
    "diag_class": "customfield_21628",
    "standard_measure": "customfield_20319",
    "vehicle_architecture": "customfield_19601",
    "cluster": "customfield_18401",
    "lead_brand": "customfield_12861",
    "relevance": "customfield_29805",           # Security Relevance-Ergebnis
    "risk_level": "customfield_28401",
    "platform": "customfield_15203",
    "further_info": "customfield_13317",
    "references": "customfield_52668",          # References / Identification
    "maturity": "customfield_13302",            # SRG0..SRG4 (Sub-tasks)
    "status_reasoning": "customfield_20314",
    "ecu_owner": "customfield_20333",
    "approval": "customfield_14202",
    "dms_link": "customfield_16501",
    "rso": "customfield_29403",                 # Responsible Security Owner(s)
    "vsm": "customfield_49701",                 # Vehicle Security Manager
    "operational_implementation": "customfield_49901",
    "subjects": "customfield_25237",
    "last_comment": "customfield_19508",
    "checklist": "customfield_11736",
    "review_checklist": "customfield_26703",
    "todo": "customfield_12800",
}
STD_FIELDS = {"summary", "status", "issuetype", "fixVersions", "assignee", "updated", "created",
              "labels", "resolution", "duedate", "parent", "issuelinks", "subtasks", "priority"}
DEFAULT_ROW_FIELDS = ["summary", "status", "issuetype", "fixVersions", "assignee", "updated"]

MOTHER_TYPES = ("Control Units", "Use Case", "Function")
STAGE_TYPES = ("Security Relevance", "Risk Analysis", "Security Concept", "Security Specification",
               "Release", "Carry Over Status", "Delta and Impact Analysis")
RELEASE_CHILD_TYPES = ("Measure", "Test Plan", "Final Risks & Security Risk Acceptance")

CU_FIELDS = ["summary", "status", "resolution", "issuetype", "fixVersions", "assignee", "updated", "issuelinks",
             "ecu", "diag_address", "vehicle_architecture", "cluster", "lead_brand", "relevance", "risk_level",
             "platform", "further_info", "references", "ecu_owner"]
STAGE_FIELDS = ["summary", "status", "resolution", "issuetype", "fixVersions", "assignee", "updated", "issuelinks",
                "cluster", "relevance", "risk_level", "approval", "status_reasoning", "dms_link"]
MEASURE_FIELDS = ["summary", "status", "resolution", "issuetype", "fixVersions", "assignee", "updated", "issuelinks",
                  "standard_measure", "ecu", "diag_address", "vehicle_architecture", "cluster", "lead_brand",
                  "status_reasoning", "approval"]


def _fid(name: str) -> str:
    return FIELD_ALIASES.get(name, name)


def _field_param(names: list[str]) -> str:
    return ",".join(dict.fromkeys(_fid(n) for n in names))


def _cf_jql(alias: str) -> str:
    return f"cf[{FIELD_ALIASES[alias].split('_')[1]}]"


def _url(key: str) -> str:
    return f"{JIRA_BASE_URL}/browse/{key}"


def norm_diag(value: Optional[str]) -> Optional[str]:
    """'0x13' -> '0013', '0626' -> '0626', '0x8146' -> '8146'. None, wenn kein Hex-Wert."""
    if not value:
        return None
    m = re.fullmatch(r"\s*(?:0x)?([0-9a-fA-F]{1,4})\s*", str(value))
    return m.group(1).upper().zfill(4) if m else None


def _links(f: dict) -> list[dict]:
    out = []
    for lk in f.get("issuelinks") or []:
        other = lk.get("outwardIssue") or lk.get("inwardIssue")
        if not other:
            continue
        of = other.get("fields") or {}
        out.append({
            "key": other["key"],
            "direction": lk["type"]["outward"] if "outwardIssue" in lk else lk["type"]["inward"],
            "issuetype": (of.get("issuetype") or {}).get("name"),
            "status": (of.get("status") or {}).get("name"),
            "summary": of.get("summary"),
        })
    return out


def _row(issue: dict, names: list[str]) -> dict:
    """Flacht ein REST-Issue auf lesbare Werte ab (Aliasnamen als Keys)."""
    f = issue.get("fields") or {}
    row: dict[str, Any] = {"key": issue["key"], "url": _url(issue["key"])}
    for n in names:
        fid = _fid(n)
        v = f.get(fid)
        if fid == "status":
            row.update(_status(f))
        elif fid == "resolution":
            row["resolution"] = (v or {}).get("name")
        elif fid == "issuelinks":
            row["links"] = _links(f)
        elif fid == "fixVersions":
            row["fix_versions"] = [x.get("name") for x in v or []]
        elif fid == "issuetype":
            row["issuetype"] = (v or {}).get("name")
        elif fid in (FIELD_ALIASES["checklist"], FIELD_ALIASES["review_checklist"], FIELD_ALIASES["todo"]):
            row[n] = _checklist(v, include_items=False)
        elif fid == FIELD_ALIASES["diag_address"]:
            row[n] = v
            row["diag_address_norm"] = norm_diag(v)
        elif v not in (None, "", [], {}):
            row[n] = _simplify(v)
    return row


def _fetch_keys(keys: list[str], names: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    keys = list(dict.fromkeys(keys))
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        issues, _ = _search_all(f"key in ({', '.join(chunk)})", _field_param(names), len(chunk))
        out.update({x["key"]: x for x in issues})
    return out


def _autocomplete(alias: str, text: str) -> list[str]:
    try:
        res = client.request_json("GET", "/rest/api/2/jql/autocompletedata/suggestions",
                                  params={"fieldName": _cf_jql(alias), "fieldValue": text})
    except Exception:  # noqa: BLE001
        return []
    vals = []
    for r in res.get("results", []):
        v = (r.get("value") or "").strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = v[1:-1].replace('\\"', '"')
        vals.append(v)
    return vals


def _text_term(q: str) -> str:
    return re.sub(r"[^\w\s]", " ", q, flags=re.UNICODE).strip()


def _ecu_clauses(query: str) -> tuple[list[str], dict]:
    """Baut OR-Klauseln fuer Summary-Text, Diagnoseadresse und Corresponding ECU."""
    clauses, info = [], {"text": None, "diag_address": None, "ecu_values": []}
    text = _text_term(query)
    if text:
        clauses.append(f"summary ~ {_jql_quote(text)}")
        info["text"] = text
    da = norm_diag(query) if re.fullmatch(r"\s*(0x)?[0-9a-fA-F]{2,4}\s*", query) else None
    if da:
        variants = {da, da.lstrip("0") or "0", f"0x{da}"}
        clauses.append("(" + " OR ".join(f"{_cf_jql('diag_address')} ~ {_jql_quote(v)}" for v in sorted(variants)) + ")")
        info["diag_address"] = da
    exact = [v for v in _autocomplete("ecu", query.strip()) if v.lower() == query.strip().lower()]
    if exact:
        clauses.append(f"{_cf_jql('ecu')} in ({', '.join(_jql_quote(v) for v in exact)})")
        info["ecu_values"] = exact
    return clauses, info


def _matched_by(row: dict, query: str, info: dict) -> list[str]:
    hits = []
    q = query.strip().lower()
    if info["ecu_values"] and any(v in (row.get("ecu") or []) for v in info["ecu_values"]):
        hits.append("corresponding_ecu")
    if info["diag_address"] and row.get("diag_address_norm") == info["diag_address"]:
        hits.append("diag_address")
    summ = (row.get("summary") or "").lower()
    if re.search(rf"\(\s*{re.escape(q)}\s*[\)_ ]", summ) or re.search(rf"\b{re.escape(q)}\b", summ):
        hits.append("summary")
    return hits or ["fulltext"]


def _srg_by_measure(measure_keys: list[str]) -> dict[str, dict]:
    """Kompakter SRG-Stand je Measure (Status je SRG-Level + lueckenlos geschlossen bis)."""
    res: dict[str, dict] = {}
    for i in range(0, len(measure_keys), 80):
        chunk = measure_keys[i:i + 80]
        jql = f"parent in ({', '.join(chunk)}) AND cf[{SRG_CF['maturity'].split('_')[1]}] is not EMPTY"
        subs, _ = _search_all(jql, SRG_FIELDS, 80 * 10)
        for s in subs:
            sf = s["fields"]
            parent = (sf.get("parent") or {}).get("key")
            lvl = _opt(sf.get(SRG_CF["maturity"]))
            if not parent or lvl not in SRG_LEVELS:
                continue
            todo = _checklist(sf.get(SRG_CF["todo"]), include_items=False)
            res.setdefault(parent, {})[lvl] = {
                "key": s["key"], **_status(sf),
                "todo": f"{todo['checked']}/{todo['total']}" if todo else None,
            }
    out = {}
    for mk, levels in res.items():
        closed = None
        for lvl in SRG_LEVELS:
            if levels.get(lvl, {}).get("status_category") == "done":
                closed = lvl
            else:
                break
        out[mk] = {"closed_consecutive_up_to": closed, "levels": levels}
    return out


_COMPACT_DROP = {"url", "resolution", "issuetype", "diag_address", "diag_address_norm", "vehicle_architecture",
                 "lead_brand", "approval", "dms_link", "updated", "ecu"}


def _compact(row: dict, keep: tuple[str, ...] = ()) -> dict:
    """Entfernt redundante Felder aus verschachtelten Zeilen (Kontext sparen)."""
    out = {}
    for k, v in row.items():
        if k in _COMPACT_DROP and k not in keep:
            continue
        if k in ("fix_versions", "cluster") and k not in keep:
            continue
        if isinstance(v, list) and v and isinstance(v[0], dict) and "key" in v[0]:
            v = [_compact(x) for x in v]
        elif k == "srg" and isinstance(v, dict):
            v = {"closed_consecutive_up_to": v.get("closed_consecutive_up_to"),
                 "levels": {lvl: f"{d.get('status')}" + (f" ({d['todo']})" if d.get("todo") else "")
                            for lvl, d in (v.get("levels") or {}).items()}}
        out[k] = v
    return out


def _cat_summary(rows: list[dict]) -> dict:
    s = {"total": len(rows), "done": 0, "in_progress": 0, "open": 0, "canceled": 0}
    for r in rows:
        if r.get("status") == "Canceled":
            s["canceled"] += 1
        elif r.get("status_category") == "done":
            s["done"] += 1
        elif r.get("status_category") == "indeterminate":
            s["in_progress"] += 1
        else:
            s["open"] += 1
    return s


# ----------------------------------------------------------------- gsep_find_ecu

@router.get(
    "/gsep/ecu/find",
    summary="Steuergeraet in GSEP suchen (Control-Units-Tickets per Name/Kuerzel, Diagnoseadresse oder Corresponding ECU)",
    operation_id="gsep_find_ecu",
)
def gsep_find_ecu(
    query: str = Query(..., description="Name, Kuerzel (z.B. 'BKE', 'LINDa', 'CI_Disp'), Diagnoseadresse ('0626', '0x13') oder Corresponding-ECU-Wert ('MRR')."),
    fix_version: list[str] = Query(default=[], description="Optional: nur diese Fix Versions/Baureihen (exakt, z.B. 'PO616-K1').", json_schema_extra={"items": {"type": "string"}}),
    include_canceled: bool = Query(False, description="Auch Tickets im Status Canceled liefern."),
    include_measure_hits: bool = Query(True, description="Zusaetzlich Measures zaehlen, die per Corresponding ECU/Diagnoseadresse passen (ECU evtl. nur als Measure vorhanden)."),
    max_results: int = Query(50, ge=1, le=500),
    project_key: str = Query("GSEP"),
):
    """Findet Muttertickets (Control Units) zu einem Steuergeraet und sagt, worueber getroffen wurde."""
    clauses, info = _ecu_clauses(query)
    if not clauses:
        raise HTTPException(status_code=400, detail="Leere Suchanfrage.")
    base = [f"project = {_jql_quote(project_key)}", 'issuetype = "Control Units"']
    if fix_version:
        base.append(f"fixVersion in ({', '.join(_jql_quote(v) for v in fix_version)})")
    if not include_canceled:
        base.append("status != Canceled")
    jql = " AND ".join(base) + " AND (" + " OR ".join(clauses) + ") ORDER BY key DESC"
    try:
        issues, total = _search_all(jql, _field_param(CU_FIELDS), max_results)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JQL-Fehler: {exc}\nJQL: {jql}")
    rows = []
    for x in issues:
        r = _row(x, CU_FIELDS)
        links = r.pop("links", [])
        r["linked_types"] = sorted({l["issuetype"] for l in links if l["issuetype"]})
        r["matched_by"] = _matched_by(r, query, info)
        rows.append(r)

    measure_hits = None
    m_clauses = clauses
    if include_measure_hits and m_clauses:
        m_jql = (f"project = {_jql_quote(project_key)} AND issuetype = Measure AND status != Canceled AND ("
                 + " OR ".join(m_clauses) + ")")
        try:
            m_issues, m_total = _search_all(m_jql, _field_param(["summary", "standard_measure", "fixVersions"]), 200)
            measure_hits = {
                "jql": m_jql, "total": m_total,
                "standard_measures": sorted({v for m in m_issues for v in (_row(m, ["standard_measure"]).get("standard_measure") or [])}),
                "fix_versions": sorted({v for m in m_issues for v in _row(m, ["fixVersions"])["fix_versions"]}),
            }
        except Exception as exc:  # noqa: BLE001
            measure_hits = {"error": str(exc), "jql": m_jql}

    return {
        "query": query, "interpreted_as": info, "jql": jql,
        "total": total, "returned": len(rows), "truncated": total > len(rows),
        "control_units": rows, "measure_hits": measure_hits,
    }


# ----------------------------------------------------------------- gsep_ecu_process

@router.get(
    "/gsep/ecu/process",
    summary="Prozessdurchlauf je Steuergeraet: alle Stages (Relevance..Release), Measures inkl. Test Tracking und SRG-Stand",
    operation_id="gsep_ecu_process",
)
def gsep_ecu_process(
    cu_keys: list[str] = Query(default=[], description="Control-Units-Keys (z.B. GSEP-4480). Alternativ 'query'.", json_schema_extra={"items": {"type": "string"}}),
    query: str = Query("", description="Wie gsep_find_ecu (Name/Kuerzel/Diagnoseadresse/ECU), wenn keine cu_keys angegeben."),
    fix_version: list[str] = Query(default=[], description="Optional Filter auf Fix Version des Control-Units-Tickets.", json_schema_extra={"items": {"type": "string"}}),
    include_srg: bool = Query(True, description="SRG0..SRG4-Stand je Measure ermitteln."),
    include_unlinked_measures: bool = Query(True, description="Measures mit gleicher Corresponding ECU/Diagnoseadresse, die NICHT am Release/CU haengen, separat melden."),
    include_canceled: bool = Query(False),
    max_cus: int = Query(5, ge=1, le=30, description="Maximalzahl Control Units (Schutz vor Riesenantworten)."),
    compact: bool = Query(True, description="Verschachtelte Tickets nur mit Key/Summary/Status/Assignee (+ Standard Measure, SRG, Test Tracking)."),
):
    """Liefert je Control Unit den kompletten GSEP-Prozessbaum mit Status und Zusammenfassung."""
    if not cu_keys:
        if not query:
            raise HTTPException(status_code=400, detail="cu_keys oder query angeben.")
        found = gsep_find_ecu(query=query, fix_version=fix_version, include_canceled=include_canceled,
                              include_measure_hits=False, max_results=max_cus, project_key="GSEP")
        cu_keys = [r["key"] for r in found["control_units"]]
        if not cu_keys:
            return {"query": query, "control_units": [], "hinweis": "Kein Control-Units-Ticket gefunden."}
    cu_keys = cu_keys[:max_cus]

    cus = _fetch_keys(cu_keys, CU_FIELDS)
    stage_keys = {l["key"] for k in cus for l in _links(cus[k]["fields"]) if l["issuetype"] in STAGE_TYPES + ("Measure",)}
    stages = _fetch_keys(list(stage_keys), STAGE_FIELDS)
    release_child_keys = {l["key"] for s in stages.values() if s["fields"]["issuetype"]["name"] == "Release"
                          for l in _links(s["fields"]) if l["issuetype"] in RELEASE_CHILD_TYPES}
    direct_measures = {k for k, s in stages.items() if s["fields"]["issuetype"]["name"] == "Measure"}
    children = _fetch_keys(list(release_child_keys | direct_measures), MEASURE_FIELDS)
    measure_keys = [k for k, c in children.items() if c["fields"]["issuetype"]["name"] == "Measure"]
    tt_keys = {l["key"] for k in measure_keys for l in _links(children[k]["fields"]) if l["issuetype"] == "Test Tracking"}
    tts = _fetch_keys(list(tt_keys), ["summary", "status", "resolution", "issuetype", "updated", "issuelinks"])
    srg = _srg_by_measure(measure_keys) if include_srg and measure_keys else {}

    def measure_row(k: str) -> dict:
        r = _row(children[k], MEASURE_FIELDS)
        links = r.pop("links", [])
        r["test_tracking"] = [
            {k2: v for k2, v in _row(tts[l["key"]], ["summary", "status"]).items() if k2 != "summary"}
            for l in links if l["key"] in tts
        ]
        if include_srg:
            r["srg"] = srg.get(k)
        return r

    result = []
    for cu_key in cu_keys:
        if cu_key not in cus:
            result.append({"key": cu_key, "error": "nicht gefunden"})
            continue
        cu = _row(cus[cu_key], CU_FIELDS)
        cu_links = cu.pop("links", [])
        st: dict[str, list] = {t: [] for t in STAGE_TYPES}
        seen_measures: set[str] = set()
        for l in cu_links:
            if l["key"] not in stages:
                continue
            s_issue = stages[l["key"]]
            itype = s_issue["fields"]["issuetype"]["name"]
            if itype == "Measure":
                continue
            row = _row(s_issue, STAGE_FIELDS)
            s_links = row.pop("links", [])
            if not include_canceled and row.get("status") == "Canceled":
                continue
            if itype == "Release":
                row["measures"] = [measure_row(x["key"]) for x in s_links
                                   if x["key"] in children and children[x["key"]]["fields"]["issuetype"]["name"] == "Measure"
                                   and (include_canceled or x["status"] != "Canceled")]
                seen_measures.update(m["key"] for m in row["measures"])
                row["test_plans"] = [_row(children[x["key"]], ["summary", "status"]) for x in s_links
                                     if x["issuetype"] == "Test Plan" and x["key"] in children]
                row["final_risks"] = [_row(children[x["key"]], ["summary", "status"]) for x in s_links
                                      if x["issuetype"] == RELEASE_CHILD_TYPES[2] and x["key"] in children]
                row["measure_summary"] = _cat_summary(row["measures"])
            st[itype].append(row)
        direct = [measure_row(l["key"]) for l in cu_links if l["key"] in direct_measures and l["key"] not in seen_measures
                  and (include_canceled or l["status"] != "Canceled")]

        unlinked = None
        if include_unlinked_measures:
            m_cl = []
            if cu.get("ecu"):
                m_cl.append(f"{_cf_jql('ecu')} in ({', '.join(_jql_quote(v) for v in cu['ecu'])})")
            if cu.get("diag_address"):
                m_cl.append(f"{_cf_jql('diag_address')} ~ {_jql_quote(cu['diag_address'])}")
            if m_cl:
                fv = cu.get("fix_versions") or []
                jql = "project = GSEP AND issuetype = Measure AND status != Canceled AND (" + " OR ".join(m_cl) + ")"
                if fv:
                    jql += f" AND fixVersion in ({', '.join(_jql_quote(v) for v in fv)})"
                try:
                    ms, _ = _search_all(jql, _field_param(["summary", "status", "standard_measure", "fixVersions", "diag_address"]), 300)
                    known = seen_measures | {d["key"] for d in direct}
                    unlinked = [_row(m, ["summary", "status", "standard_measure", "fixVersions", "diag_address"])
                                for m in ms if m["key"] not in known
                                and norm_diag((m["fields"].get(FIELD_ALIASES["diag_address"]) or "")) in (None, cu.get("diag_address_norm"))]
                except Exception as exc:  # noqa: BLE001
                    unlinked = [{"error": str(exc), "jql": jql}]

        all_measures = [m for rel in st["Release"] for m in rel["measures"]] + direct
        summary = {t: _cat_summary(v) for t, v in st.items() if v}
        summary["Measure"] = _cat_summary(all_measures)
        if include_srg:
            dist: dict[str, int] = {}
            for m in all_measures:
                lvl = (m.get("srg") or {}).get("closed_consecutive_up_to") or "none"
                dist[lvl] = dist.get(lvl, 0) + 1
            summary["srg_closed_up_to_distribution"] = dist
        missing = [t for t in ("Security Relevance", "Release") if not st[t]]
        if compact:
            st = {t: [_compact(r, keep=("fix_versions", "cluster") if t == "Release" else ()) for r in v]
                  for t, v in st.items()}
            direct = [_compact(m) for m in direct]
            if unlinked:
                unlinked = [_compact(m, keep=("fix_versions",)) for m in unlinked]
        result.append({
            **cu,
            "process_summary": summary,
            "missing_or_canceled_stages": missing,
            "stages": {t: v for t, v in st.items() if v},
            "measures_linked_directly_to_cu": direct,
            "measures_same_ecu_not_linked": unlinked,
            "other_links": [l for l in cu_links if l["issuetype"] not in STAGE_TYPES + ("Measure",)],
        })
    return {"control_units": result}


# ----------------------------------------------------------------- gsep_ecu_measures

@router.get(
    "/gsep/ecu/measures",
    summary="Security-Massnahmen (Measures) je Steuergeraet ueber Corresponding ECU und/oder Diagnoseadresse",
    operation_id="gsep_ecu_measures",
)
def gsep_ecu_measures(
    ecu: list[str] = Query(default=[], description="Corresponding ECU, exakte Werte (vorher mit srg_lookup field=ecu pruefen).", json_schema_extra={"items": {"type": "string"}}),
    diag_address: list[str] = Query(default=[], description="Diagnoseadressen ('0626', '0x13', '8146').", json_schema_extra={"items": {"type": "string"}}),
    fix_version: list[str] = Query(default=[], json_schema_extra={"items": {"type": "string"}}),
    vehicle_architecture: list[str] = Query(default=[], json_schema_extra={"items": {"type": "string"}}),
    include_canceled: bool = Query(False),
    include_srg: bool = Query(False, description="SRG-Stand je Measure mitliefern (langsamer)."),
    max_results: int = Query(300, ge=1, le=2000),
):
    """Liefert Measures inkl. Standard Measure, Status, Release-/CU-Verlinkung; gruppiert nach Standard Measure."""
    or_cl = []
    if ecu:
        or_cl.append(f"{_cf_jql('ecu')} in ({', '.join(_jql_quote(v) for v in ecu)})")
    for d in diag_address:
        n = norm_diag(d)
        if n:
            or_cl.append("(" + " OR ".join(f"{_cf_jql('diag_address')} ~ {_jql_quote(v)}" for v in sorted({n, f'0x{n}'})) + ")")
    if not or_cl:
        raise HTTPException(status_code=400, detail="ecu oder diag_address angeben.")
    cl = ["project = GSEP", "issuetype = Measure", "(" + " OR ".join(or_cl) + ")"]
    if fix_version:
        cl.append(f"fixVersion in ({', '.join(_jql_quote(v) for v in fix_version)})")
    if vehicle_architecture:
        cl.append(f"{_cf_jql('vehicle_architecture')} in ({', '.join(_jql_quote(v) for v in vehicle_architecture)})")
    if not include_canceled:
        cl.append("status != Canceled")
    jql = " AND ".join(cl) + " ORDER BY key"
    try:
        issues, total = _search_all(jql, _field_param(MEASURE_FIELDS), max_results)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JQL-Fehler: {exc}\nJQL: {jql}")
    wanted_diag = {norm_diag(d) for d in diag_address} - {None}
    srg = _srg_by_measure([x["key"] for x in issues]) if include_srg and issues else {}
    rows, by_std = [], {}
    for x in issues:
        r = _row(x, MEASURE_FIELDS)
        links = r.pop("links", [])
        r["releases"] = [l["key"] for l in links if l["issuetype"] == "Release"]
        r["control_units"] = [l["key"] for l in links if l["issuetype"] in MOTHER_TYPES]
        r["test_tracking"] = [{"key": l["key"], "status": l["status"]} for l in links if l["issuetype"] == "Test Tracking"]
        if wanted_diag and r.get("diag_address_norm") and r["diag_address_norm"] not in wanted_diag and not ecu:
            continue  # Volltext-Treffer mit anderer Adresse verwerfen
        if include_srg:
            r["srg"] = srg.get(x["key"])
        rows.append(r)
        for s in r.get("standard_measure") or ["(ohne Standard Measure)"]:
            by_std.setdefault(s, []).append({"key": r["key"], "status": r.get("status"), "fix_versions": r.get("fix_versions")})
    return {"jql": jql, "total": total, "returned": len(rows), "truncated": total > len(issues),
            "by_standard_measure": dict(sorted(by_std.items())), "measures": rows}


# ----------------------------------------------------------------- gsep_search

@router.get(
    "/gsep/search",
    summary="JQL-Bulk-Suche mit frei waehlbaren Feldern (Aliasnamen fuer GSEP-Custom-Fields), paginiert bis 2000",
    operation_id="gsep_search",
)
def gsep_search(
    jql: str = Query(..., description="Vollstaendige JQL, z.B. 'project = GSEP AND issuetype = Measure AND fixVersion = \"PO616-K1\"'."),
    fields: list[str] = Query(default=[], description=("Feldnamen: Standard (summary,status,issuetype,fixVersions,assignee,updated,created,labels,"
                                                         "resolution,duedate,parent,issuelinks,subtasks) oder Aliase: " + ", ".join(FIELD_ALIASES)
                                                         + " oder customfield_xxx. Leer = summary,status,issuetype,fixVersions,assignee,updated."),
                              json_schema_extra={"items": {"type": "string"}}),
    group_by: str = Query("", description="Optional: Feld/Alias zum Gruppieren (Zaehlung), z.B. 'status' oder 'standard_measure'."),
    rows: bool = Query(True, description="False = nur Zaehlung/Gruppierung ohne Einzelzeilen (spart Kontext)."),
    max_results: int = Query(500, ge=1, le=2000),
):
    names = fields or DEFAULT_ROW_FIELDS
    if group_by and group_by not in names:
        names = names + [group_by]
    try:
        issues, total = _search_all(jql, _field_param(names), max_results)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"JQL-Fehler: {exc}")
    out_rows = [_row(x, names) for x in issues]
    groups = None
    if group_by:
        key = {"fixVersions": "fix_versions", "issuelinks": "links"}.get(group_by, group_by)
        groups = {}
        for r in out_rows:
            v = r.get(key)
            for g in (v if isinstance(v, list) else [v]) or [None]:
                g = str(g) if g is not None else "(leer)"
                groups[g] = groups.get(g, 0) + 1
        groups = dict(sorted(groups.items(), key=lambda kv: -kv[1]))
    return {"jql": jql, "total": total, "returned": len(out_rows), "truncated": total > len(out_rows),
            "groups": groups, "rows": out_rows if rows else None}


# ----------------------------------------------------------------- gsep_links

@router.get(
    "/gsep/links",
    summary="Link-Graph ab einem Ticket verfolgen (Breitensuche ueber Issue-Links, optional Typfilter)",
    operation_id="gsep_links",
)
def gsep_links(
    key: str = Query(..., description="Start-Ticket, z.B. GSEP-4480"),
    depth: int = Query(2, ge=1, le=4),
    issuetypes: list[str] = Query(default=[], description="Nur diesen Issue-Typen folgen (z.B. Release, Measure, Test Tracking). Leer = allen.", json_schema_extra={"items": {"type": "string"}}),
    max_nodes: int = Query(150, ge=1, le=500),
):
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    queue: deque = deque([(key, 0)])
    seen = {key}
    while queue and len(nodes) < max_nodes:
        level = []
        d = queue[0][1]
        while queue and queue[0][1] == d:
            level.append(queue.popleft()[0])
        fetched = _fetch_keys(level, ["summary", "status", "issuetype", "fixVersions", "issuelinks"])
        for k in level:
            if k not in fetched:
                continue
            r = _row(fetched[k], ["summary", "status", "issuetype", "fixVersions", "issuelinks"])
            links = r.pop("links", [])
            r["depth"] = d
            nodes[k] = r
            for l in links:
                if issuetypes and l["issuetype"] not in issuetypes:
                    continue
                edges.append({"from": k, "to": l["key"], "type": l["direction"]})
                if l["key"] not in seen and d + 1 <= depth:
                    seen.add(l["key"])
                    queue.append((l["key"], d + 1))
    return {"start": key, "depth": depth, "nodes": list(nodes.values()), "edges": edges,
            "truncated": bool(queue)}
