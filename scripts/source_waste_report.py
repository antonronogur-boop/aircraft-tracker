# -*- coding: utf-8 -*-
"""
source_waste_report.py — MELYIK FORRAS EGETI A PENZT?

Forrasonkent megmutatja, hany cikk erkezett, es abbol hanyat minositett a
modell irrelevansnak. Minden ilyen cikkert EGY TELJES modellhivast fizettunk
ki — a dontes ugyanis a draga hivason BELUL szuletik.

MIERT FORRAS-SZINTEN: a 2026-10-03-i drónos meres szerint a pazarlas 86%-a
tizenhet forrasbol jott. Kulcsszavas szures ugyanebbol legfeljebb 5%-ot fog
meg, es minden egyes mintaval no az eselye, hogy relevans anyagot dob el. Egy
forras viszont stabil, merheto, es a dontes visszavonhato.

Ez a script HAROM projektben ugyanaz (Drone_UAV Monitor, Balkan_Monitor,
Aircraft_Tracker): mindharom ugyanazt a statusz-szokincset hasznalja
(raw / processed / irrelevant / failed), es mindharom a sajat Supabase-ebol
dolgozik. Nem ir semmit.

HASZNALAT:
    python scripts\\source_waste_report.py
    python scripts\\source_waste_report.py --min-articles 20

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (a .env-bol).
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import supabase_client as db  # noqa: E402

IRRELEVANT = "irrelevant"
# A 'raw' nem szamit: azt a modell meg nem latta, tehat nem tudjuk rola,
# mi lett volna. Beleszamitva alulbecsulnenk minden forras aranyat.
NOT_YET_SEEN = {"raw", None, ""}


def arg_value(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def main():
    min_articles = int(arg_value("--min-articles", 10))

    print("source_waste_report.py — forrasonkenti pazarlas")
    print("=" * 74)

    articles = db.select("articles", {"select": "source_id,status"})
    sources = db.select("sources", {"select": "source_id,source_name,status"})
    names = {s["source_id"]: (s.get("source_name") or s["source_id"]) for s in sources}
    src_status = {s["source_id"]: (s.get("status") or "active") for s in sources}

    print("  cikk: {}   forras: {}".format(len(articles), len(sources)))

    seen = Counter()
    irr = Counter()
    raw = Counter()
    status_mix = defaultdict(Counter)

    for a in articles:
        sid = a.get("source_id") or "(nincs forras)"
        st = a.get("status")
        status_mix[sid][st or "(ures)"] += 1
        if st in NOT_YET_SEEN:
            raw[sid] += 1
            continue
        seen[sid] += 1
        if st == IRRELEVANT:
            irr[sid] += 1

    rows = []
    for sid, total in seen.items():
        rows.append({
            "sid": sid,
            "name": names.get(sid, sid),
            "seen": total,
            "irr": irr[sid],
            "raw": raw[sid],
            "share": irr[sid] / float(total),
            "src_status": src_status.get(sid, "?"),
        })
    rows.sort(key=lambda r: (-r["irr"], -r["share"]))

    print("\n{:<42} {:>7} {:>7} {:>7} {:>6}  {}".format(
        "forras", "feldolg", "irrel.", "raw", "arany", "allapot"))
    print("-" * 90)
    total_irr = 0
    for r in rows:
        if r["seen"] < min_articles:
            continue
        total_irr += r["irr"]
        print("{:<42} {:>7} {:>7} {:>7} {:>5.0f}%  {}".format(
            r["name"][:42], r["seen"], r["irr"], r["raw"],
            100 * r["share"], r["src_status"]))

    heavy = [r for r in rows if r["share"] >= 0.5 and r["seen"] >= min_articles
             and r["src_status"] != "archived"]
    all_irr = sum(irr.values())

    print("\nOSSZEGZES")
    print("-" * 74)
    print("  modell altal latott cikk:        {}".format(sum(seen.values())))
    print("  ebbol irrelevans (kifizetve):    {} ({:.0f}%)".format(
        all_irr, 100.0 * all_irr / max(1, sum(seen.values()))))
    print("  meg feldolgozatlan (raw):        {}".format(sum(raw.values())))

    if heavy:
        hv = sum(r["irr"] for r in heavy)
        print("\n  {} AKTIV forras legalabb 50%-ban irrelevans.".format(len(heavy)))
        print("  Egyutt {} felesleges feldolgozas ({:.0f}%-a az osszesnek):".format(
            hv, 100.0 * hv / max(1, all_irr)))
        for r in heavy:
            print("    - {:<40} {:>5} irrelevans / {:<5} ({:.0f}%)".format(
                r["name"][:40], r["irr"], r["seen"], 100 * r["share"]))
        print("\n  Ezek archivalhatok (sources.status='archived'), amivel a")
        print("  gyujtes is leall. A mar begyujtott cikkek maradnak.")
    else:
        print("\n  Nincs olyan AKTIV forras, amelynek a fele irrelevans lenne.")

    archived = [r for r in rows if r["src_status"] == "archived"]
    if archived:
        print("\n  Mar archivalt forras: {} (osszesen {} korabbi irrelevans cikk)".format(
            len(archived), sum(r["irr"] for r in archived)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
