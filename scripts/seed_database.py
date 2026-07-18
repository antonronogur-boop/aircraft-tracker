# -*- coding: utf-8 -*-
"""Seed the Aircraft Tracker tables from data/*.json.

Idempotent: uses upsert, safe to run repeatedly (e.g. after editing the
catalogue). Run AFTER executing supabase/schema.sql in the SQL editor.

Usage (from aircraft_tracker/):
    set SUPABASE_URL=https://uqjhgdclaagfkopdfjlq.supabase.co
    set SUPABASE_SERVICE_ROLE_KEY=<key>
    python scripts\\seed_database.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load(name):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def main():
    countries = load("countries.json")
    catalogue = load("aircraft_catalogue.json")
    sources = load("sources.json")

    db.upsert("ac_countries", countries, "country_id")
    print("countries:      {} upserted".format(len(countries)))

    db.upsert("ac_aircraft_types", catalogue, "type_id")
    print("aircraft types: {} upserted".format(len(catalogue)))

    for s in sources:
        s.setdefault("enabled", True)
    db.upsert("ac_sources", sources, "source_id")
    print("sources:        {} upserted".format(len(sources)))

    print("\nDone. Next: run scripts\\collect_rss.py to pull the first articles.")


if __name__ == "__main__":
    main()
