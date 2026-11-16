# devstack-jira-mcp

Ein **Model Context Protocol Server** fuer die VW-Group-Jira-Instanz
<https://devstack.vwgroup.com/jira> (z.B. fuer die Projekte **GSEP** und **PPSE**). Auth nur per
Personal Access Token. Laeuft Windows-nativ ohne Docker und ohne venv.

## Highlights

- **Nur PAT** – kein Zertifikat, kein UAC, kein Proxy-Setup.
- **Kein Docker, kein venv** – Standard-Python-Installation (`py`-Launcher oder `python`).
- **Doppelklick-Start:** `start-mcp.bat`.
- **Klare Standard-Tools** fuer Copilot/Claude: Issues, Search, Comments, Attachments.

## Voraussetzungen

- Python 3.10+ (`py`-Launcher oder `python` im PATH, z.B. aus dem Porsche Software-Center oder python.org)
- Personal Access Token fuer devstack.vwgroup.com
  ([Anleitung bei VW](https://devstack.vwgroup.com/jira/secure/ViewProfile.jspa))
- Netzwerk-Zugriff auf <https://devstack.vwgroup.com/jira>

## Installation & Start

```cmd
git clone https://github.com/ChrisMeineck/Devstack_Jira_MCP_Server.git devstack-jira-mcp
cd devstack-jira-mcp
copy .env.example .env
REM .env oeffnen und JIRA_PAT eintragen
start-mcp.bat
```

Der Server kann auf **alle** Projekte zugreifen, fuer die der PAT-Inhaber in devstack-Jira
berechtigt ist (z.B. GSEP und PPSE) – das Projekt wird je Anfrage per JQL bzw. `project_key`
gewaehlt. `JIRA_DEFAULT_PROJECT_KEY` ist nur der Vorschlag fuer Copilot bei vagen Anfragen
und der Default beim Anlegen neuer Tickets.

Beim ersten Start werden die Abhaengigkeiten aus `requirements.txt` per `pip` installiert
(Marker-Datei `.deps-installed`; zum erneuten Installieren nach einem `git pull` mit
geaenderter `requirements.txt` einfach loeschen).

Der Server lauscht danach auf <http://localhost:8766/mcp>.

> **Wichtig:** Die `.env` enthaelt deinen persoenlichen PAT und ist per `.gitignore`
> ausgeschlossen. Niemals einchecken oder weitergeben – jede Person nutzt ihren eigenen Token.
> Alle Jira-Aktionen laufen mit den Rechten des jeweiligen PAT-Inhabers.

### Verbindung pruefen

```powershell
Invoke-RestMethod http://localhost:8766/test_connection | ConvertTo-Json -Depth 4
```

Erwartete Ausgabe bei korrekt gesetztem PAT:

```json
{
  "status": "connected",
  "base_url": "https://devstack.vwgroup.com/jira",
  "user": { "name": "P123456", "displayName": "Mustermann, Max", "active": true },
  "default_project_key": "PPSE"
}
```

## VS Code einbinden

1. `Strg+Shift+P` -> **MCP: Add Server** -> **Add from URL**
2. URL: `http://localhost:8766/mcp`
3. Name: `devstack-jira-mcp`

Oder direkt in `mcp.json`:

```jsonc
{
  "servers": {
    "devstack-jira-mcp": {
      "url": "http://localhost:8766/mcp",
      "type": "http"
    }
  }
}
```

Beispiel im Copilot Chat:

> Suche alle offenen Bugs in PPSE, die mir zugewiesen sind.
> Zeig mir PPSE-123 mit allen Kommentaren.
> Setze PPSE-123 auf "In Progress" und kommentiere "Starte Analyse".

## Verfuegbare Endpoints / MCP-Tools

| Tool / Endpoint                                | Beschreibung                                              |
|------------------------------------------------|-----------------------------------------------------------|
| `GET /health`                                  | Basis-Healthcheck (laeuft ohne PAT)                       |
| `GET /test_connection`                         | PAT-/Erreichbarkeitstest via `/rest/api/2/myself`         |
| `GET /issues/{key}`                            | Ticket-Details                                            |
| `POST /issues`                                 | Ticket anlegen                                            |
| `PATCH /issues/{key}`                          | Felder aktualisieren (summary, description, labels, ...)  |
| `GET /issues/{key}/transitions`                | Verfuegbare Status-Transitions                            |
| `POST /issues/{key}/transitions`               | Status-Transition ausloesen (per Name oder ID)            |
| `GET /search?jql=...`                          | JQL-Suche                                                 |
| `GET /issues/{key}/comments`                   | Kommentare lesen                                          |
| `POST /issues/{key}/comments`                  | Kommentar hinzufuegen                                     |
| `GET /issues/{key}/attachments`                | Attachments auflisten                                     |
| `GET /attachments/{id}`                        | Attachment-Bytes als Base64                               |
| `GET /issues/{key}/fields`  (`get_issue_fields`) | Alle befuellten Felder inkl. Custom Fields (Klartext-Namen, Checklisten mit checked/mandatory) |
| `GET /srg/status`  (`srg_status`)              | Security-Reifegrad-Status je Measure: SRG0..SRG4-Sub-tasks mit Status und ToDo-Checkboxen. Filter: `ecu`, `standard_measure`, `fix_version`, `vehicle_architecture`, `lead_brand`, `measure_keys` |
| `GET /srg/lookup`  (`srg_lookup`)              | Exakte Filterwerte finden (ECU, Fix Version, Standard Measure, Architektur, Marke, Cluster) |
| `GET /gsep/ecu/find`  (`gsep_find_ecu`)        | Control-Units-Tickets per Name/Kuerzel, Diagnoseadresse (`0626`, `0x13`) oder Corresponding ECU; liefert `matched_by` + Measure-Treffer |
| `GET /gsep/ecu/process`  (`gsep_ecu_process`)  | Prozessdurchlauf je Control Unit: Security Relevance .. Release -> Measures (+Test Tracking, SRG), Zusammenfassung, fehlende Stages, nicht verlinkte Measures gleicher ECU (`compact=true` Default) |
| `GET /gsep/ecu/measures`  (`gsep_ecu_measures`) | Measures je Steuergeraet (Corresponding ECU und/oder Diagnoseadresse), gruppiert nach Standard Measure, optional SRG |
| `GET /gsep/search`  (`gsep_search`)            | JQL-Bulk-Suche bis 2000 Treffer mit frei waehlbaren Feldern (Aliase wie `ecu`, `diag_address`, `standard_measure`) und `group_by`-Zaehlung |
| `GET /gsep/links`  (`gsep_links`)              | Link-Graph ab einem Ticket (Breitensuche, Typfilter) |

Die SRG-Endpunkte (`routes/srg.py`, seit 19.10.2026) und die GSEP-Endpunkte (`routes/gsep.py`, seit 05.11.2026)
sind **nur lesend**. Custom-Field-IDs (GSEP: ToDo-List `customfield_12800`, Maturity Level `customfield_13302`,
Corresponding ECU `customfield_49807`, Standard Measure `customfield_20319`, Diagnostic address `customfield_21627`, ...)
stehen oben in `routes/srg.py` bzw. `FIELD_ALIASES` in `routes/gsep.py`; dort ist auch die GSEP-Ticketstruktur dokumentiert.
Die Tools lassen sich direkt im Copilot Chat nutzen oder ueber eigene Custom Agents / Skills
(z.B. "SRG-Status-Reporter", "GSEP Analyst") ansprechen.

OpenAPI-UI: <http://localhost:8766/docs>

## Konfiguration (`.env`)

| Variable                   | Default                                | Bedeutung                                            |
|----------------------------|----------------------------------------|------------------------------------------------------|
| `JIRA_PAT`                 | _(Pflicht)_                            | Personal Access Token                                |
| `JIRA_BASE_URL`            | `https://devstack.vwgroup.com/jira`    | Jira-Basis-URL                                       |
| `JIRA_DEFAULT_PROJECT_KEY` | `PPSE`                                 | Tool-Description-Hint fuer Copilot bei vagen Queries |
| `MCP_TRANSPORT`            | `http`                                 | `http` oder `stdio`                                  |
| `MCP_PORT`                 | `8766`                                 | HTTP-Port                                            |
| `JIRA_HTTP_TIMEOUT`        | `30`                                   | Timeout in Sekunden                                  |

## Troubleshooting

**`JIRA_PAT ist nicht gesetzt`**
- `.env` pruefen; Server nach Aenderung neu starten.

**`401 Unauthorized` bei `/test_connection`**
- PAT ist falsch oder abgelaufen.
- Neuen Token unter Jira -> Profil -> Personal Access Tokens erzeugen.

**`SSLError` / `Connection refused`**
- VPN aktiv? devstack ist evtl. nur ueber Konzernnetz erreichbar.

**Port 8766 belegt**
- `MCP_PORT` in `.env` aendern und `mcp.json` anpassen.

## Entwicklung

```powershell
py -m pip install -r requirements-dev.txt
py -m pytest          # Unit-Tests (Jira komplett gemockt, kein PAT/Netz noetig)
py -m ruff check .    # Lint (Konfiguration in pyproject.toml)
```

Neue Endpunkte: Route-Modul unter `routes/` anlegen, in `routes/__init__.py` registrieren,
Tests unter `tests/` ergaenzen und die Endpoint-Tabelle oben aktualisieren.

## Projektstruktur

```text
mcp_server.py        Entry Point (FastAPI + fastapi-mcp, HTTP oder stdio)
config.py            Konfiguration aus .env
client.py            Jira-Client (jira-Bibliothek) + requests-Session mit Bearer-PAT
routes/              Endpunkte (health, issues, search, comments, attachments, srg, gsep)
tests/               pytest-Unit-Tests
.env.example         Vorlage fuer die lokale .env
mcp.example.json     Vorlage fuer die VS-Code-MCP-Konfiguration
start-mcp.bat/.ps1   Start-Skripte (Python-Erkennung + einmalige Dependency-Installation)
```
