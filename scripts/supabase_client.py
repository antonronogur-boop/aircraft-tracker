# -*- coding: utf-8 -*-
"""Shared Supabase PostgREST client for the Aircraft Tracker pipeline.

Stdlib-only (urllib), Python 3.9+. All writes use the SERVICE_ROLE key.

Env vars:
    SUPABASE_URL                e.g. https://uqjhgdclaagfkopdfjlq.supabase.co
    SUPABASE_SERVICE_ROLE_KEY   Supabase Dashboard -> Settings -> API -> service_role
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SUPABASE_URL = os.environ["SUPABASE_URL"].strip().rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()

_PAGE_SIZE = 1000
_MAX_PAGES = 50


def _request(method, path, params=None, body=None, prefer=None):
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def select(table, params=None):
    # type: (str, Optional[Dict[str, str]]) -> List[Dict[str, Any]]
    """Paginated SELECT — always returns the full result set."""
    params = dict(params or {})
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


def insert_ignore_duplicates(table, rows, conflict_column):
    if not rows:
        return
    _request("POST", table, params={"on_conflict": conflict_column},
             body=rows, prefer="resolution=ignore-duplicates,return=minimal")


def insert(table, row):
    """Insert one row and return it (needed for identity columns)."""
    result = _request("POST", table, body=row, prefer="return=representation")
    return result[0] if isinstance(result, list) and result else None


def upsert(table, rows, conflict_column):
    if not rows:
        return
    _request("POST", table, params={"on_conflict": conflict_column},
             body=rows, prefer="resolution=merge-duplicates,return=minimal")


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
