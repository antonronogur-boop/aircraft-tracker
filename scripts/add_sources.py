# -*- coding: utf-8 -*-
"""Celzott forrasbovites — CSAK az uj forrasokat veszi fel.

A config/source_expansion.json forrasai kozul azokat szurja be az
ac_sources-ba, amelyek meg nincsenek ott. Meglevo forrast (a source policy
altal kikapcsoltat sem) NEM modosit — ezert nem a seed_database.py-t
hasznaljuk, ami minden forrast ujra enabled=true-ra allitana.

Usage: python scripts/add_sources.py [--dry-run]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

CFG = Path(__file__).resolve().parent.parent / "config" / \
    "source_expansion.json"


def main():
    dry = "--dry-run" in sys.argv
    wanted = json.loads(CFG.read_text(encoding="utf-8"))["sources"]
    have = {s["source_id"] for s in db.select(
        "ac_sources", {"select": "source_id"})}
    new = [{k: v for k, v in s.items() if not k.startswith("_")}
           for s in wanted if s["source_id"] not in have]
    for s in wanted:
        print("  {} {:<32} {}".format(
            "NEW " if s["source_id"] not in have else "have",
            s["source_name"], s.get("rss_url")))
    if not new:
        print("Nothing to add.")
        return
    if dry:
        print("DRY RUN — {} source(s) would be added.".format(len(new)))
        return
    db.insert_ignore_duplicates("ac_sources", new, "source_id")
    print("Added {} source(s). They are collected from the next daily "
          "run.".format(len(new)))


if __name__ == "__main__":
    main()
