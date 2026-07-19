# -*- coding: utf-8 -*-
"""FULL DATA RESET — clean recovery from the bad Wikipedia import.

One command does everything:
  1. deletes ALL fleet rows,
  2. deletes every auto-imported (junk) catalogue type — events that
     accidentally reference them are detached first,
  3. restores the curated 110-type catalogue (data/aircraft_catalogue.json),
  4. restores the curated, verified fleet baseline (data/fleets.json).

Articles, events, reports are NOT touched.

Usage:
    python scripts\\reset_data.py            (shows what it would do)
    python scripts\\reset_data.py --apply    (does it)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def chunks(lst, n=50):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def main():
    apply = "--apply" in sys.argv

    fleets_now = db.select("ac_fleets", {"select": "fleet_id"})
    junk = db.select("ac_aircraft_types", {
        "select": "type_id", "notes": "like.auto-imported*"})
    junk_ids = [t["type_id"] for t in junk]

    catalogue = json.loads((DATA_DIR / "aircraft_catalogue.json").read_text(encoding="utf-8"))
    baseline = json.loads((DATA_DIR / "fleets.json").read_text(encoding="utf-8"))

    print("Current fleet rows to DELETE:        {}".format(len(fleets_now)))
    print("Junk catalogue types to DELETE:      {}".format(len(junk_ids)))
    print("Curated catalogue types to restore:  {}".format(len(catalogue)))
    print("Curated fleet rows to restore:       {}".format(len(baseline["rows"])))

    if not apply:
        print("\nDRY RUN — re-run with --apply to execute.")
        return

    # 1. wipe fleets
    db._request("DELETE", "ac_fleets", params={"fleet_id": "gte.0"},  # noqa: SLF001
                prefer="return=minimal")
    print("fleets wiped")

    # 2. detach events from junk types, then delete the types
    for batch in chunks(junk_ids):
        in_list = "in.({})".format(",".join('"{}"'.format(t) for t in batch))
        db.update("ac_events", {"type_id": in_list}, {"type_id": None})
    for batch in chunks(junk_ids):
        in_list = "in.({})".format(",".join('"{}"'.format(t) for t in batch))
        db._request("DELETE", "ac_aircraft_types",  # noqa: SLF001
                    params={"type_id": in_list}, prefer="return=minimal")
    print("junk types deleted: {}".format(len(junk_ids)))

    # 3. restore curated catalogue
    db.upsert("ac_aircraft_types", catalogue, "type_id")
    print("catalogue restored: {}".format(len(catalogue)))

    # 4. restore curated baseline
    known_c = {c["country_id"] for c in db.select("ac_countries", {"select": "country_id"})}
    known_t = {t["type_id"] for t in db.select("ac_aircraft_types", {"select": "type_id"})}
    rows = []
    for cid, tid, status, qty, note in baseline["rows"]:
        if cid in known_c and tid in known_t:
            rows.append({
                "country_id": cid, "type_id": tid, "fleet_status": status,
                "quantity": qty, "as_of": baseline["as_of"],
                "source_note": ("[baseline] " + (note or baseline["source_note"]))[:500],
            })
    for batch in chunks(rows, 200):
        db._request("POST", "ac_fleets", body=batch, prefer="return=minimal")  # noqa: SLF001
    print("fleet baseline restored: {} rows".format(len(rows)))
    print("\nDONE — the site now shows the curated, verified data only.")


if __name__ == "__main__":
    main()
