# -*- coding: utf-8 -*-
"""Seed the ac_fleets baseline from data/fleets.json.

Idempotent: wipes and re-inserts all rows whose source_note marks them as
baseline (manual edits with a different source_note are preserved).

Usage (from Aircraft_Tracker/, with SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY set):
    python scripts\\seed_fleets.py
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "fleets.json")
                  .read_text(encoding="utf-8"))
BASELINE_TAG = "[baseline]"

VALID_STATUS = {"active", "on_order", "option", "selected", "retiring", "retired", "negotiation"}


def main():
    rows = []
    skipped = []
    known_types = {t["type_id"] for t in db.select("ac_aircraft_types", {"select": "type_id"})}
    known_countries = {c["country_id"] for c in db.select("ac_countries", {"select": "country_id"})}

    for cid, tid, status, qty, note in DATA["rows"]:
        if cid not in known_countries or tid not in known_types:
            skipped.append((cid, tid))
            continue
        if status not in VALID_STATUS:
            skipped.append((cid, tid))
            continue
        source_note = BASELINE_TAG + " " + (note or DATA["source_note"])
        rows.append({
            "country_id": cid, "type_id": tid, "fleet_status": status,
            "quantity": qty, "as_of": DATA["as_of"], "source_note": source_note[:500],
        })

    # Delete previous baseline rows, then insert fresh.
    # NOTE: PostgREST 'like' uses * as wildcard (translated to %), not %.
    db._request("DELETE", "ac_fleets",  # noqa: SLF001 — intentional low-level call
                params={"source_note": "like.{}*".format(BASELINE_TAG)},
                prefer="return=minimal")
    # Insert in chunks (PostgREST payload limits)
    for i in range(0, len(rows), 200):
        db._request("POST", "ac_fleets", body=rows[i:i + 200],  # noqa: SLF001
                    prefer="return=minimal")

    print("fleet baseline rows inserted: {}".format(len(rows)))
    if skipped:
        print("skipped (unknown country/type/status): {}".format(skipped))


if __name__ == "__main__":
    main()
