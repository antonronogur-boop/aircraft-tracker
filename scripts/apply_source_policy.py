# -*- coding: utf-8 -*-
"""
apply_source_policy.py — a config/source_policy.json 'drop' forrasainak
kikapcsolasa: {SOURCES}.enabled=false (a gyujtes leall), es a mar begyujtott,
meg FELDOLGOZATLAN (raw) cikkeik 'irrelevant'-ra allitasa, modellhivas nelkul.

A feldolgozott cikkekhez nem nyul. Visszaallitas: --restore (enabled=true).

HASZNALAT:
    python scripts/apply_source_policy.py            (dry-run)
    python scripts/apply_source_policy.py --apply
    python scripts/apply_source_policy.py --restore --apply
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402
import source_policy  # noqa: E402

SOURCES = "ac_sources"
ARTICLES = "ac_articles"


def main():
    apply_mode = "--apply" in sys.argv
    restore = "--restore" in sys.argv
    cfg = source_policy.load()
    drops = {sid: e["name"] for sid, e in cfg["policies"].items()
             if e["policy"] == source_policy.DROP}

    print("apply_source_policy.py — {}{}  [{}]".format(
        "VISSZAALLITAS" if restore else "KIKAPCSOLAS",
        "" if apply_mode else " (DRY-RUN)", SOURCES))
    print("  policy: {}".format(cfg["path"]))

    rows = {r["source_id"]: r for r in db.select(
        SOURCES, {"select": "source_id,source_name,enabled"})}

    for sid, name in sorted(drops.items(), key=lambda kv: kv[1]):
        row = rows.get(sid)
        if not row:
            print("  [!] {} ({}) nincs a {} tablaban — kihagyva".format(name, sid, SOURCES))
            continue
        target = bool(restore)
        state = "enabled={} -> {}".format(row.get("enabled"), target)
        raw_n = 0
        if not restore:
            raw_n = len(db.select(ARTICLES, {"select": "article_id",
                                             "source_id": "eq." + sid, "status": "eq.raw"}))
        print("  {:<10} {:<34} {}{}".format(sid, name[:34], state,
              "" if restore else ", {} raw cikk -> irrelevant".format(raw_n)))
        if not apply_mode:
            continue
        db.update(SOURCES, {"source_id": "eq." + sid}, {"enabled": target})
        if not restore and raw_n:
            db.update(ARTICLES, {"source_id": "eq." + sid, "status": "eq.raw"},
                      {"status": "irrelevant"})

    print("Kesz." if apply_mode else "DRY-RUN — semmi nem valtozott. Vegrehajtas: --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
