# -*- coding: utf-8 -*-
"""audit_event_dates.py — a meglevo esemenyek datumfegyelmenek atvizsgalasa.

MIERT: a W31-es jelentesben egy 2020 januarjaban alairt lengyel F-35-szerzodes
es egy 2025-os nemet parlamenti jovahagyas szerepelt a HET fo uzletei kozott,
mert a heti tagsagot a gyujtes ideje dontotte el. Az uj generator mar
event_date szerint valogat — de a mar adatbazisban levo soroknal az event_date
gyakran hianyzik vagy a cikk megjelenesenek napja.

Ez a szkript a summary SZOVEGEBOL olvas ki datumot ("signed in January 2020",
"approval in 2025", "on 24 July 2026"), es osszeveti a mezovel:

  MISSING     — nincs event_date, de a szoveg tartalmaz datumot
  CONTRADICT  — a szovegbeli ev korabbi, mint az event_date eve (a klasszikus
                hiba: regi esemeny a beolvasas napjaval datumozva)

Alapertelmezes a DRY-RUN. Az --apply csak azokat irja at, ahol a szovegbeli
datum egyertelmu (pontosan egy evjelolt talalat).

Hasznalat:
    python scripts\\audit_event_dates.py                (dry-run, 180 nap)
    python scripts\\audit_event_dates.py --days 400
    python scripts\\audit_event_dates.py --apply

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
MONTHS.update({m[:3].lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])})

# "on 24 July 2026" / "24 July 2026" / "July 24, 2026" / "in January 2020"
DMY_RX = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b")
MDY_RX = re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b")
MY_RX = re.compile(r"\b(?:in|since|during|from)\s+([A-Za-z]{3,9})\s+(\d{4})\b",
                   re.I)
Y_RX = re.compile(r"\b(?:in|back in|during)\s+(19\d{2}|20\d{2})\b", re.I)


def dates_in(text):
    """Minden ertelmes datumjelolt a szovegbol, (date, precision) parban."""
    out = []
    t = text or ""
    for m in DMY_RX.finditer(t):
        mo = MONTHS.get(m.group(2).lower())
        if mo:
            try:
                out.append((datetime(int(m.group(3)), mo, int(m.group(1))), "day"))
            except ValueError:
                pass
    for m in MDY_RX.finditer(t):
        mo = MONTHS.get(m.group(1).lower())
        if mo:
            try:
                out.append((datetime(int(m.group(3)), mo, int(m.group(2))), "day"))
            except ValueError:
                pass
    for m in MY_RX.finditer(t):
        mo = MONTHS.get(m.group(1).lower())
        if mo:
            out.append((datetime(int(m.group(2)), mo, 1), "month"))
    for m in Y_RX.finditer(t):
        out.append((datetime(int(m.group(1)), 1, 1), "year"))
    return out


def main():
    apply_mode = "--apply" in sys.argv
    days = 180
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except (IndexError, ValueError):
            pass

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.select("ac_events", {
        "select": "event_id,summary,event_date,created_at,event_type",
        "review_status": "neq.rejected",
        "created_at": "gte." + since, "order": "created_at.desc"})
    print("Loaded {} event(s) from the last {} day(s).".format(len(rows), days))

    missing, contradict, ambiguous = [], [], []
    for r in rows:
        found = dates_in(r.get("summary"))
        if not found:
            continue
        # A legkorabbi talalat a mervado: egy cikk tipikusan az esemenyt
        # datalja, majd a mai napra hivatkozik.
        found.sort(key=lambda x: x[0])
        cand, prec = found[0]
        distinct_years = {d.year for d, _ in found}
        cur = None
        if r.get("event_date"):
            try:
                cur = datetime.strptime(str(r["event_date"])[:10], "%Y-%m-%d")
            except ValueError:
                cur = None
        if cur is None:
            (missing if len(distinct_years) == 1 else ambiguous).append(
                (r, cand, prec, found))
        elif cand.year < cur.year:
            (contradict if len(distinct_years) == 1 else ambiguous).append(
                (r, cand, prec, found))

    def show(title, items, limit=40):
        if not items:
            return
        print("\n{} ({}):".format(title, len(items)))
        for r, cand, prec, found in items[:limit]:
            print("  #{:>6} [{}] {} -> {} ({})".format(
                r["event_id"], r.get("event_date") or "no date",
                str(r.get("summary") or "")[:78],
                cand.strftime("%Y-%m-%d"), prec))
        if len(items) > limit:
            print("  ... and {} more".format(len(items) - limit))

    show("MISSING event_date but a date is stated in the text", missing)
    show("CONTRADICTION — text describes an OLDER event than event_date",
         contradict)
    show("AMBIGUOUS — several different years in the text (manual review)",
         ambiguous)

    fixable = missing + contradict
    if not fixable:
        print("\nNothing to fix.")
        return
    if not apply_mode:
        print("\nDRY-RUN — nothing changed. {} event(s) would be re-dated. "
              "Re-run with --apply.".format(len(fixable)))
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    for r, cand, prec, _ in fixable:
        patch = {"event_date": cand.strftime("%Y-%m-%d")}
        try:
            db.update("ac_events", {"event_id": "eq." + str(r["event_id"])},
                      dict(patch, updated_at=now_iso))
        except Exception:  # noqa: BLE001 — updated_at may not exist yet
            db.update("ac_events", {"event_id": "eq." + str(r["event_id"])},
                      patch)
        print("  #{} -> {}".format(r["event_id"], patch["event_date"]))
    print("\nDone. {} event(s) re-dated from their own text.".format(
        len(fixable)))


if __name__ == "__main__":
    main()
