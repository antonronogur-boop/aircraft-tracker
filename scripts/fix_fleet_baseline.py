# -*- coding: utf-8 -*-
"""fix_fleet_baseline.py — az ac_fleets baseline egyeztetese a programme-regiszterrel.

MIERT KELL EZ
-------------
A programme-reteg megszunteti a TOVABBI halmozodast, de a MAR FELHALMOZOTT
hibat nem javitja ki magatol — az elemzoi dontes. A W34-es jelentesben ez ket
sorban latszik:

    Poland   AH-64 Apache    Active 0     On order 286   <- a valosag: 96
    Germany  F-35 Lightning  Active 35    On order 0     <- a valosag: 0 aktiv,
                                                            35 rendelesben

A 286 a duplikacio maradvanya (190 + 96). A nemet 35 pedig ROSSZ OSZLOPBAN van:
a jelentes ugyanezen oldalan all, hogy az elso gep most kerul vegso gyartasi
fazisba — vagyis egyetlen aktiv nemet F-35 sincs.

MIT TESZ
--------
Osszevetni a programme-regiszter SZERZODOTT darabszamait az ac_fleets
allomanyaval, es javaslatot tenni. ALAPERTELMEZESBEN DRY RUN.

    python scripts\\fix_fleet_baseline.py             # javaslatok
    python scripts\\fix_fleet_baseline.py --write     # alkalmazas

Harom eltérés-tipust jelez:

  1. ON-ORDER TULLOTT  — a flotta on_order tobb, mint a program szerzodott
     darabszama, es a kulonbseg nem magyarazhato masik programmal
  2. ROSSZ OSZLOP      — aktiv allomany szerepel ott, ahol a program meg
     szallitas elott all (nincs delivery/ioc/foc evidencia)
  3. HIANYZO SOR       — van szerzodott program, de nincs hozza flotta-sor

A --write CSAK az 1. es 2. tipust javitja, es MINDEN valtoztatast kiir a
source_note mezobe, hogy visszakovethetó legyen.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import supabase_client as db  # noqa: E402
import ac_programmes as acprog  # noqa: E402

# Azok a stadiumok, amelyekben mar LEHET aktiv gep.
FIELDED_STAGES = {"delivery", "ioc", "foc"}


def main(argv):
    write = "--write" in argv
    print("=" * 78)
    print("FLEET BASELINE RECONCILIATION — {}".format(
        "WRITE MODE" if write else "DRY RUN (nothing will be written)"))
    print("=" * 78)

    try:
        programmes = db.select("ac_programmes", {"select": "*"})
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("ac_programmes not available ({}). Run "
                         "supabase/add_programme_layer.sql and "
                         "scripts/reconcile_programmes.py --write first."
                         .format(str(exc)[:120]))
    if not programmes:
        raise SystemExit("The programme register is empty. Run "
                         "scripts/reconcile_programmes.py --write first.")

    fleets = db.select("ac_fleets", {"select": "*"})
    types = {t["type_id"]: t.get("name")
             for t in db.select("ac_aircraft_types",
                                {"select": "type_id,name"})}
    countries = {c["country_id"]: c.get("name")
                 for c in db.select("ac_countries",
                                    {"select": "country_id,name"})}
    print("\n{} programme(s), {} fleet row(s)".format(
        len(programmes), len(fleets)))

    # A szerzodott allomany programonkent, orszag+tipus szerint osszesitve.
    # FIGYELEM: itt SZABAD osszegezni — kulonbozo programok kulonbozo
    # rendelesek. A tilalom az UGYANAZON program ujramondasara vonatkozik.
    contracted = {}
    fielded = {}
    for p in programmes:
        if (p.get("programme_kind") or "acquisition") != "acquisition":
            continue
        if p.get("review_status") not in (None, "active"):
            continue
        cid, tid = p.get("country_id"), p.get("type_id")
        if not (cid and tid):
            continue
        q = p.get("contracted_quantity")
        try:
            q = int(q) if q not in (None, "") else None
        except (TypeError, ValueError):
            q = None
        if q:
            contracted[(cid, tid)] = contracted.get((cid, tid), 0) + q
        if (p.get("lifecycle_stage") or "") in FIELDED_STAGES:
            fielded.setdefault((cid, tid), []).append(p.get("programme_id"))

    idx = {}
    for f in fleets:
        idx.setdefault((f.get("country_id"), f.get("type_id")), {})[
            f.get("fleet_status")] = f

    overshoot, wrong_column, missing = [], [], []
    for (cid, tid), q in sorted(contracted.items()):
        rows = idx.get((cid, tid)) or {}
        oo_row = rows.get("on_order")
        act_row = rows.get("active")
        label = "{} {}".format(countries.get(cid, cid), types.get(tid, tid))

        oo = (oo_row or {}).get("quantity") or 0
        act = (act_row or {}).get("quantity") or 0

        if oo_row is None and act_row is None:
            missing.append({"country_id": cid, "type_id": tid, "label": label,
                            "contracted": q})
            continue

        # 1. on-order tullott
        if oo > q:
            overshoot.append({
                "fleet_id": oo_row.get("fleet_id"), "label": label,
                "country_id": cid, "type_id": tid,
                "current": oo, "proposed": q,
                "reason": ("on-order {} exceeds the {} contracted across all "
                           "active programmes for this type".format(oo, q))})

        # 2. rossz oszlop: aktiv allomany szallitas elott
        if act > 0 and (cid, tid) not in fielded:
            wrong_column.append({
                "fleet_id": act_row.get("fleet_id"), "label": label,
                "country_id": cid, "type_id": tid,
                "current_active": act, "proposed_active": 0,
                "proposed_on_order": max(oo, q),
                "reason": ("{} shown as active, but no programme for this type "
                           "has reached delivery, IOC or FOC — this is an "
                           "order, not an in-service fleet".format(act))})

    def block(title, rows, fmt):
        print("\n" + "-" * 78)
        print(title)
        print("-" * 78)
        if not rows:
            print("  none")
        for r in rows:
            print(fmt(r))

    block("1. ON-ORDER OVERSHOOT — the accumulated duplication", overshoot,
          lambda r: "  {:<34} on_order {} -> {}\n      {}".format(
              r["label"][:33], r["current"], r["proposed"], r["reason"]))
    block("2. WRONG COLUMN — counted as in service before any delivery",
          wrong_column,
          lambda r: "  {:<34} active {} -> {}, on_order -> {}\n      {}".format(
              r["label"][:33], r["current_active"], r["proposed_active"],
              r["proposed_on_order"], r["reason"]))
    block("3. MISSING ROW — contracted programme with no fleet baseline "
          "(reported only, never written automatically)", missing,
          lambda r: "  {:<34} {} contracted, no ac_fleets row".format(
              r["label"][:33], r["contracted"]))

    out = HERE.parent / "data" / "fleet_baseline_proposals.json"
    out.write_text(json.dumps(
        {"generated_utc": datetime.utcnow().isoformat(),
         "overshoot": overshoot, "wrong_column": wrong_column,
         "missing": missing}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    print("\nFull proposals: {}".format(out))

    if not write:
        print("\n" + "=" * 78)
        print("DRY RUN — nothing written. Re-run with --write to apply "
              "types 1 and 2.")
        print("Type 3 is never written automatically: a missing baseline is an")
        print("analyst decision, not an inference.")
        print("=" * 78)
        return 0

    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    n = 0
    for r in overshoot:
        db.update("ac_fleets", {"fleet_id": "eq.{}".format(r["fleet_id"])},
                  {"quantity": r["proposed"], "as_of": stamp,
                   "source_note": ("corrected {} -> {} against the programme "
                                   "register on {} (accumulated duplication)"
                                   .format(r["current"], r["proposed"], stamp))})
        n += 1
    for r in wrong_column:
        db.update("ac_fleets", {"fleet_id": "eq.{}".format(r["fleet_id"])},
                  {"quantity": r["proposed_active"], "as_of": stamp,
                   "source_note": ("active set to 0 on {}: no programme for "
                                   "this type has reached delivery/IOC/FOC"
                                   .format(stamp))})
        n += 1
        # A rendelesi allomanyt is helyre tesszuk, ha van hova.
        oo_row = (idx.get((r["country_id"], r["type_id"])) or {}).get("on_order")
        if oo_row is not None:
            db.update("ac_fleets",
                      {"fleet_id": "eq.{}".format(oo_row.get("fleet_id"))},
                      {"quantity": r["proposed_on_order"], "as_of": stamp,
                       "source_note": ("set from the programme register on {}"
                                       .format(stamp))})
            n += 1
    print("\n{} fleet row(s) updated. Regenerate the weekly report to see the "
          "corrected ORBAT.".format(n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
