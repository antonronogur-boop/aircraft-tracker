# -*- coding: utf-8 -*-
"""List unresolved aircraft/country names from extracted events.

Shows which names the pipeline could NOT match to the catalogue, with
counts — the shopping list for new aliases or new catalogue entries.
Run it every few weeks; feed the frequent ones back into
data/aircraft_catalogue.json aliases, then re-run seed_database.py.

Usage: python scripts\\list_unresolved.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402


def main():
    events = db.select("ac_events", {
        "select": "unresolved_type_name,unresolved_country_name,review_status",
        "review_status": "neq.rejected"})

    types = Counter(e["unresolved_type_name"] for e in events
                    if e.get("unresolved_type_name"))
    countries = Counter(e["unresolved_country_name"] for e in events
                        if e.get("unresolved_country_name"))

    print("=== Unresolved AIRCRAFT names ({} distinct) ===".format(len(types)))
    for name, n in types.most_common(40):
        print("  {:>3}x  {}".format(n, name))
    print("\n=== Unresolved COUNTRY names ({} distinct) ===".format(len(countries)))
    for name, n in countries.most_common(20):
        print("  {:>3}x  {}".format(n, name))
    if not types and not countries:
        print("Everything resolved — nothing to do.")


if __name__ == "__main__":
    main()
