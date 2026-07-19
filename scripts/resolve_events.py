# -*- coding: utf-8 -*-
"""Retroactively resolve events whose aircraft/country name failed to match
at extraction time. Re-runs the (now enriched) alias matcher over every
event with an unresolved name and fills in type_id / country_id where a
match is found now.

Usage:
    python scripts\\resolve_events.py            (dry run)
    python scripts\\resolve_events.py --apply
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402


def build_indexes():
    type_idx, country_idx = {}, {}
    for t in db.select("ac_aircraft_types", {"select": "type_id,name,designation,aliases"}):
        for v in [t["type_id"], t.get("name"), t.get("designation")] + list(t.get("aliases") or []):
            if v:
                type_idx[str(v).lower()] = t["type_id"]
    for c in db.select("ac_countries", {"select": "country_id,name,aliases"}):
        for v in [c["country_id"], c.get("name")] + list(c.get("aliases") or []):
            if v:
                country_idx[str(v).lower()] = c["country_id"]
    return type_idx, country_idx


def match(value, index):
    if not value:
        return None
    v = value.strip().lower()
    if v in index:
        return index[v]
    for alias, ident in sorted(index.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 4 and alias in v:
            return ident
    return None


def main():
    apply = "--apply" in sys.argv
    type_idx, country_idx = build_indexes()
    events = db.select("ac_events", {
        "select": "event_id,unresolved_type_name,unresolved_country_name",
        "review_status": "neq.rejected",
        "or": "(unresolved_type_name.not.is.null,unresolved_country_name.not.is.null)"})

    fixes = []
    for e in events:
        patch = {}
        tid = match(e.get("unresolved_type_name"), type_idx)
        cid = match(e.get("unresolved_country_name"), country_idx)
        if tid:
            patch.update({"type_id": tid, "unresolved_type_name": None})
        if cid:
            patch.update({"country_id": cid, "unresolved_country_name": None})
        if patch:
            fixes.append((e, patch))
            print("#{}: '{}' -> {}".format(
                e["event_id"],
                e.get("unresolved_type_name") or e.get("unresolved_country_name"),
                patch.get("type_id") or patch.get("country_id")))

    print("\nResolvable events: {} / {}".format(len(fixes), len(events)))
    if not apply:
        print("DRY RUN — re-run with --apply to write.")
        return
    for e, patch in fixes:
        db.update("ac_events", {"event_id": "eq.{}".format(e["event_id"])}, patch)
    print("Done.")


if __name__ == "__main__":
    main()
