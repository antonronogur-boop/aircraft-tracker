# -*- coding: utf-8 -*-
"""Shared Supabase PostgREST client for the Aircraft Tracker pipeline.

Stdlib-only (urllib), Python 3.9+. All writes use the SERVICE_ROLE key.

Env vars:
    SUPABASE_URL                e.g. https://uqjhgdclaagfkopdfjlq.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   Supabase Dashboard -> Settings -> API -> service_role
"""
import json
import random
import time
import os
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

def _load_dotenv():
    """A projekt gyokereben levo .env betoltese, ha a valtozok nincsenek a
    kornyezetben. Igy nem kell minden uj cmd-ablakban ujra beallitani oket
    (a .env a .gitignore-ban van, tehat nem kerul a repoba)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in (".env", "scripts/.env"):
        path = os.path.join(root, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(),
                                          v.strip().strip('"').strip("'"))
        except OSError:
            pass


_load_dotenv()


def _require(name, hint):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            "\nMISSING ENVIRONMENT VARIABLE: {0}\n"
            "  {1}\n"
            "  Fix it in one of two ways:\n"
            "    1) create a .env file in the project root with lines like\n"
            "         SUPABASE_URL=https://<project>.supabase.co\n"
            "         SUPABASE_SERVICE_ROLE_KEY=<service_role key>\n"
            "         ANTHROPIC_API_KEY=<key>\n"
            "    2) or set it for this window:  set {0}=<value>\n".format(
                name, hint))
    return value.strip()


SUPABASE_URL = _require(
    "SUPABASE_URL", "Supabase project URL, e.g. https://xxxx.supabase.co"
).rstrip("/")
SERVICE_KEY = _require(
    "SUPABASE_SERVICE_ROLE_KEY",
    "Supabase Dashboard -> Settings -> API -> service_role key")

_PAGE_SIZE = 1000
_MAX_PAGES = 50


# ---------------------------------------------------------------------------
# UJRAPROBALKOZAS MULO HIBARA
#
# A 2026-09-12-i balkan-monitor-sync futas egyetlen "HTTP Error 504: Gateway
# Timeout" miatt allt le — az RSS-gyujtes kozben, tehat a teljes napi lanc
# elveszett egy masodpercekig tarto atjaro-hiba miatt.
#
# Az 5xx es a 429 NEM vegleges hiba: azt jelenti, hogy "most nem, probald
# ujra". Veglegeskent kezelni oket ugyanaz a tevedes, mint az Oryx-scrapernel
# volt. A 4xx (400, 401, 404, 409) viszont VALODI hiba — azt azonnal
# eldobjuk, mert varakozastol nem javul.
#
# IDEMPOTENCIA. Ujraprobalni csak akkor szabad, ha a megismetelt keres nem
# hoz letre masodpeldanyt:
#   GET            — mindig biztonsagos
#   PATCH szurovel — ugyanazt az erteket irja ujra
#   POST on_conflict-tal — a duplikatumot a DB szuri ki
#   POST anelkul   — NEM biztonsagos: ha az elso keres valojaban atment, csak
#                    a valasz veszett el, egy ujabb sor keletkezne. Ezert az
#                    egysoros insert() nem probalkozik ujra.
_RETRY_STATUS = (429, 500, 502, 503, 504)
_RETRY_ATTEMPTS = 4


def _sleep_backoff(attempt):
    time.sleep(min(2 ** attempt * 2, 20) + random.uniform(0, 1.5))


def _request(method, path, params=None, body=None, prefer=None,
             retry=True):
    url = "{}/rest/v1/{}".format(SUPABASE_URL, path)
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": "Bearer {}".format(SERVICE_KEY),
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    last = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            # A POSTGREST MEGMONDJA, MI A BAJ — csak eddig nem olvastuk el.
            # A valasz torzse tartalmazza a hibakodot, az erintett oszlopot
            # vagy megszoritast, gyakran javaslattal egyutt; a kivetel szovege
            # viszont csak annyi: "HTTP Error 400: Bad Request".
            try:
                detail = e.read().decode("utf-8", "replace")[:600]
            except Exception:  # noqa: BLE001
                detail = "(a valasz torzse nem olvashato)"
            last = "HTTP {}: {}".format(e.code, detail)
            if e.code not in _RETRY_STATUS or not retry:
                raise RuntimeError("Supabase {} {} -> {}".format(
                    method, path, last)) from None
        except Exception as e:  # noqa: BLE001 — halozati/idotullepes hiba
            last = "{}: {}".format(type(e).__name__, str(e)[:200])
            if not retry:
                raise
        if attempt < _RETRY_ATTEMPTS - 1:
            print("  [retry] Supabase {} {} — {} (ujraprobalkozas {}/{})".format(
                method, path, last, attempt + 1, _RETRY_ATTEMPTS - 1))
            _sleep_backoff(attempt)
    raise RuntimeError("Supabase {} {} — {} kiserlet utan sem sikerult: {}".format(
        method, path, _RETRY_ATTEMPTS, last))


def select(table, params=None):
    # type: (str, Optional[Dict[str, str]]) -> List[Dict[str, Any]]
    """SELECT with pagination.

    If the caller passes an explicit "limit", it is HONOURED (single request,
    no pagination) — batch caps in the pipeline scripts depend on this.
    Without a limit, all pages are fetched.
    """
    params = dict(params or {})
    explicit_limit = params.pop("limit", None)
    if explicit_limit is not None:
        params["limit"] = str(explicit_limit)
        return _request("GET", table, params=params) or []

    rows = []  # type: List[Dict[str, Any]]
    for page in range(_MAX_PAGES):
        page_params = dict(params)
        page_params["limit"] = str(_PAGE_SIZE)
        page_params["offset"] = str(page * _PAGE_SIZE)
        batch = _request("GET", table, params=page_params) or []
        rows.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
    return rows


def _normalise_keys(rows):
    # type: (List[Dict[str, Any]]) -> List[Dict[str, Any]]
    """Azonos kulcskeszlet minden sorban egy kotegelt beszurasnal.

    A PostgREST elutasitja (400) az olyan tomeges beszurast, ahol az objektumok
    kulcsai elternek — ez okozta a drone-uav-monitor napi futasanak elszallasat
    2026-09-10-tol. A combat_experience sorok tobbsegeben nincs
    "adversary_response", egyben viszont van; a vegyes kulcskeszlet miatt az
    EGESZ koteg elszallt, es vele a futas.

    A hianyzo kulcsok None-t kapnak. Ez tartalmilag azonos a kulcs
    elhagyasaval (a DB ugyanugy NULL-t tarol), viszont a koteg ervenyes lesz.
    """
    if len(rows) < 2:
        return rows
    keys = set()
    for r in rows:
        keys.update(r.keys())
    return [{k: r.get(k) for k in keys} for r in rows]


def insert_ignore_duplicates(table, rows, conflict_column):
    if not rows:
        return
    _request("POST", table, params={"on_conflict": conflict_column},
             body=_normalise_keys(rows), prefer="resolution=ignore-duplicates,return=minimal")


def insert(table, row):
    """Insert one row and return it (needed for identity columns)."""
    result = _request("POST", table, body=row, prefer="return=representation")
    return result[0] if isinstance(result, list) and result else None


def upsert(table, rows, conflict_column):
    if not rows:
        return
    _request("POST", table, params={"on_conflict": conflict_column},
             body=_normalise_keys(rows), prefer="resolution=merge-duplicates,return=minimal")


def update(table, filters, patch):
    _request("PATCH", table, params=filters, body=patch, prefer="return=minimal")


# --- pipeline_runs logging (shared table with the drone monitor) -----------

def start_run(script_name):
    try:
        return insert("pipeline_runs", {"script_name": script_name, "status": "running"})
    except Exception as e:  # noqa: BLE001
        print("  [warn] pipeline_runs start failed: {}".format(e))
        return None


def finish_run(run, status, items_processed=None, error_message=None, details=None):
    if not run or not run.get("run_id"):
        return
    patch = {"status": status, "finished_at": datetime.now(timezone.utc).isoformat()}
    if items_processed is not None:
        patch["items_processed"] = items_processed
    if error_message is not None:
        patch["error_message"] = error_message[:4000]
    if details is not None:
        patch["details"] = details
    try:
        update("pipeline_runs", {"run_id": "eq.{}".format(run["run_id"])}, patch)
    except Exception as e:  # noqa: BLE001
        print("  [warn] pipeline_runs finish failed: {}".format(e))
