"""Jira-Client (PAT-only) fuer den devstack-jira-mcp Server.

Exportiert:
  jira          - Lazy-initialisierter JIRA-Client (jira-Bibliothek)
  http_session  - requests.Session mit Bearer-Auth fuer direkte REST-Calls
"""
import logging

import requests
from jira import JIRA
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import JIRA_BASE_URL, JIRA_HTTP_TIMEOUT, JIRA_PAT

logger = logging.getLogger(__name__)

_jira_client: JIRA | None = None
_http_session: requests.Session | None = None


def _require_pat() -> str:
    if not JIRA_PAT:
        raise RuntimeError(
            "JIRA_PAT ist nicht gesetzt. Bitte in .env einen Personal Access Token "
            "fuer devstack.vwgroup.com hinterlegen."
        )
    return JIRA_PAT


def _create_http_session() -> requests.Session:
    pat = _require_pat()
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {pat}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    # Retries fuer idempotente Requests: Server/Proxy schliessen Keep-Alive-
    # Verbindungen nach Leerlauf, der erste Request danach scheitert sonst mit
    # "RemoteDisconnected".
    retry = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _create_jira_client() -> JIRA:
    pat = _require_pat()
    logger.info("Initialisiere JIRA-Client fuer %s", JIRA_BASE_URL)
    return JIRA(server=JIRA_BASE_URL, token_auth=pat)


def get_http_session() -> requests.Session:
    global _http_session
    if _http_session is None:
        _http_session = _create_http_session()
    return _http_session


def get_jira_client() -> JIRA:
    global _jira_client
    if _jira_client is None:
        _jira_client = _create_jira_client()
    return _jira_client


class _JiraClientProxy:
    def __getattr__(self, name):
        return getattr(get_jira_client(), name)

    def __repr__(self):
        return repr(get_jira_client())


class _HttpSessionProxy:
    def __getattr__(self, name):
        return getattr(get_http_session(), name)

    def __repr__(self):
        return repr(get_http_session())


jira = _JiraClientProxy()
http_session = _HttpSessionProxy()


def request_json(method: str, path: str, **kwargs) -> dict:
    """Bequemer Wrapper: relative Pfad gegen JIRA_BASE_URL, gibt geparsed JSON zurueck."""
    url = f"{JIRA_BASE_URL}{path}"
    kwargs.setdefault("timeout", JIRA_HTTP_TIMEOUT)
    response = get_http_session().request(method, url, **kwargs)
    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()
