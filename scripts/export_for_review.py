# -*- coding: utf-8 -*-
"""export_for_review.py — egyszeri adatkimentes offline elemzeshez.

MIERT: a programme-reteg finomhangolasa a VALODI cikkszovegeken dol el. Ha
minden iteracio egy eles futtatast igenyel, az lassu es idegesito. Ez a script
egyszer kimenti a szukseges tablakat egy JSON fajlba, amin a logika kesobb
korlatlanul ujrajatszhato — adatbazis nelkul.

Nem ir semmit. Csak olvas.

    python scripts\\export_for_review.py

Kimenet: data\\events_export.json

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import supabase_client as db  # noqa: E402

OUT = HERE.parent / "data" / "events_export.json"


def main():
    print("Exporting for offline review (read-only)...")
    payload = {"exported_utc": datetime.utcnow().isoformat()}

    tables = [
        ("ac_events", "*", {"order": "event_id.asc"}),
        ("ac_aircraft_types", "type_id,name,designation,category,aliases", {}),
        ("ac_countries", "country_id,name,region,aliases", {}),
        ("ac_fleets", "*", {}),
        ("ac_articles", "article_id,title,url,source_id,publish_date", {}),
    ]
    for table, select, extra in tables:
        try:
            rows = db.select(table, dict({"select": select}, **extra))
        except Exception as exc:  # noqa: BLE001
            print("  [warn] {}: {}".format(table, str(exc)[:120]))
            rows = []
        payload[table] = rows
        print("  {:<20} {} row(s)".format(table, len(rows)))

    try:
        payload["ac_programmes"] = db.select("ac_programmes", {"select": "*"})
        print("  {:<20} {} row(s)".format("ac_programmes",
                                          len(payload["ac_programmes"])))
    except Exception:  # noqa: BLE001
        payload["ac_programmes"] = []

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    size = OUT.stat().st_size / 1024.0
    print("\nWritten: {}  ({:.0f} KB)".format(OUT, size))
    print("Nothing was modified.")


if __name__ == "__main__":
    main()
