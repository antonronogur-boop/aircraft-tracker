# -*- coding: utf-8 -*-
"""Deduplicate soft events (negotiation / selection / other).

Multiple outlets covering the same story create near-identical events
(e.g. 'Poland evaluating F-35' x3). For each (country, aircraft type,
event_type) group among NON-rejected soft events, keeps the best one
(longest summary = most informative, newest as tiebreak) and rejects
the rest. Hard events (order/delivery/etc.) are left untouched — those
can legitimately repeat over time.

Usage:
    python scripts\\dedupe_events.py            (dry run)
    python scripts\\dedupe_events.py --apply
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

SOFT_TYPES = ("negotiation", "selection", "other")


def main():
    apply = "--apply" in sys.argv
    events = db.select("ac_events", {
        "select": "event_id,event_type,country_id,type_id,summary,review_status,created_at",
        "review_status": "neq.rejected",
        "event_type": "in.({})".format(",".join(SOFT_TYPES)),
        "order": "created_at.asc"})

    groups = {}
    for e in events:
        key = (e.get("country_id"), e.get("type_id"), e["event_type"])
        if key[0] is None and key[1] is None:
            continue  # fully unresolved -> leave for manual review
        groups.setdefault(key, []).append(e)

    to_reject = []
    for key, evs in groups.items():
        if len(evs) < 2:
            continue
        # keep the most informative (longest summary), newest as tiebreak
        keep = max(evs, key=lambda e: (len(e.get("summary") or ""), e["created_at"]))
        dupes = [e for e in evs if e["event_id"] != keep["event_id"]]
        to_reject.extend(dupes)
        print("KEEP  #{} {} | {} | {}".format(
            keep["event_id"], key[2], key[0] or "?", key[1] or "?"))
        for d in dupes:
            print("  drop #{} — {}".format(d["event_id"], (d.get("summary") or "")[:70]))

    print("\nDuplicates to reject: {}".format(len(to_reject)))
    if not apply:
        print("DRY RUN — re-run with --apply to execute.")
        return
    for e in to_reject:
        db.update("ac_events", {"event_id": "eq.{}".format(e["event_id"])},
                  {"review_status": "rejected"})
    print("Done — {} duplicates rejected.".format(len(to_reject)))


if __name__ == "__main__":
    main()
