# -*- coding: utf-8 -*-
"""split_mixed_fleet_rows.py — ket kulonbozo eszkoz egy rekordban.

MIERT: a kulso ellenorzes ket olyan sort talalt, ahol NEM az adat rossz,
hanem a SZERKEZET. Egy rekord ket kulonbozo repuloeszkozt kever, amelyeknek
mas az eletciklusa, mas a kepessege es mas a beszerzesi utja. Ilyenkor
barmilyen szamot irunk be, az hamis lesz — nem azert, mert rosszul szamoltuk,
hanem mert a kerdes maga ertelmetlen ezen a soron.

  1. Egyesult Kiralysag — "MQ-9 Reaper / Protector RG Mk1"
     Az MQ-9A Reaper 2025-ben kivonasra kerult. A Protector RG Mk1 (MQ-9B)
     ettol fuggetlen, uj program. Egy sorban tartva ugy nezne ki, mintha a
     brit flotta folyamatosan uzemelne ugyanazzal az eszkozzel — holott
     kepessegtorés volt kozottuk.

  2. Del-Korea — "E-7 Peace Eye"
     A negy meglevo E-7 helyes. A tovabbi negy beszerzendo AEW&C viszont NEM
     E-7, hanem Global 6500-alapu rendszer (L3Harris). Ha csak nullazzuk az
     on_order sort, a negy gep ELTUNIK a nyilvantartasbol — egy valos
     beszerzes veszne el a kepbol. Uj tipusrekord kell hozza.

MUKODES: SEMMIT NEM TOROL. A regi sor 'retired' vagy nulla mennyiseget kap
indoklassal, az uj tipus es az uj flotta-sor letrejon, es minden erintett sor
megkapja, hogy MIERT valtozott.

Hasznalat:
    python scripts\\split_mixed_fleet_rows.py           (dry-run)
    python scripts\\split_mixed_fleet_rows.py --apply

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

# Minden szetvalasztas EXPLICIT. Nincs heurisztika: ezek elemzoi dontesek,
# amiket a kulso ellenorzes indokolt, es igy is kell dokumentalni oket.
SPLITS = [
    {
        "country": "United Kingdom",
        "old_type_match": "MQ-9",
        "reason": "Az MQ-9A Reaper 2025-ben kivonasra kerult; a Protector "
                  "RG Mk1 (MQ-9B) onallo, uj program — kepessegtores van a "
                  "ketto kozott.",
        # A megmarado (regi) sor sorsa. A DARABSZAM MEGMARAD: egy kivont
        # tipusnal az, hogy HANY gepe volt az orszagnak, tortenelmi adat, es
        # a kepesseg-idosorhoz kell. Nullazni annyi lenne, mintha sosem lett
        # volna Reaperjuk.
        "old_action": {"fleet_status": "retired", "keep_quantity": True,
                       "note": "MQ-9A Reaper kivonva 2025-ben; a Protector "
                               "RG Mk1 kulon rekordba kerult"},
        # Uj tipus, ha meg nem letezik
        "new_type": {
            "type_id": "mq-9b-protector",
            "name": "MQ-9B Protector RG Mk1",
            "designation": "Protector RG Mk1",
            "category": "uav",
            "manufacturer": "General Atomics Aeronautical Systems",
            "origin_country": "United States",
            "role": "Certifiable MALE ISR/strike UAV",
            "production_status": "in_production",
            "notes": "A brit MQ-9A Reaper utodja. Kulon rekord: elteroe "
                     "tanusitas, elteroe eletciklus.",
            "aliases": ["Protector RG Mk1", "MQ-9B", "Protector"],
        },
        # Uj flotta-sorok
        "new_fleets": [
            # SZAM NELKUL. Az ellenorzes "legfeljebb 16"-ot mondott, ami
            # felso korlat, nem darabszam. A sajat szabalyunk szerint ilyenkor
            # nem irunk szamot — kulonben ugyanazt a hamis pontossagot
            # gyartanank, ami miatt az egesz ellenorzes indult.
            {"fleet_status": "on_order", "quantity": None,
             "source_note": "Kulso ellenorzes 2026-08: felso korlat 16; "
                            "az atvett mennyiseg kulon ellenorzendo",
             "verification_verdict": "unverifiable",
             "verification_confidence": "low",
             "quantity_range_note": "legfeljebb 16 — az atvett mennyiseg "
                                    "nyilt forrasbol nem egyertelmu"},
        ],
    },
    {
        "country": "South Korea",
        "old_type_match": "E-7",
        "reason": "A meglevo negy E-7 Peace Eye helyes. A tovabbi negy "
                  "AEW&C NEM E-7, hanem Global 6500-alapu (L3Harris) — "
                  "kulon tipus, kulon program.",
        "old_action": None,   # a meglevo 4 aktiv E-7 valtozatlan marad
        "new_type": {
            "type_id": "global-6500-aewc",
            "name": "Global 6500 AEW&C",
            "designation": "Global 6500 AEW&C (L3Harris)",
            "category": "special_mission",
            "manufacturer": "L3Harris / Bombardier",
            "origin_country": "United States",
            "role": "Airborne early warning and control",
            "production_status": "in_development",
            "notes": "Del-koreai AEW&C-II program. NEM E-7 — kulon "
                     "platform, kulon rendszer.",
            "aliases": ["AEW&C-II", "Global 6500 AEWC"],
        },
        "new_fleets": [
            {"fleet_status": "on_order", "quantity": 4,
             "source_note": "Kulso ellenorzes 2026-08: L3Harris kivalasztva "
                            "(2025-10), Global 6500 alapon",
             "verification_verdict": "corrected",
             "verification_confidence": "medium"},
        ],
    },
]


def fold(s):
    t = unicodedata.normalize("NFKD", (s or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def main():
    apply_mode = "--apply" in sys.argv
    now = datetime.now(timezone.utc).isoformat()

    countries = db.select("ac_countries", {"select": "*", "limit": "1000"})
    types = db.select("ac_aircraft_types", {"select": "*", "limit": "3000"})
    fleets = db.select("ac_fleets", {"select": "*", "limit": "10000"})
    by_country = {fold(c["name"]): c["country_id"] for c in countries}
    existing_types = {t["type_id"] for t in types}
    type_name = {t["type_id"]: t.get("name") for t in types}

    actions = []
    for sp in SPLITS:
        cid = by_country.get(fold(sp["country"]))
        print("\n" + "=" * 74)
        print("{} — {}".format(sp["country"], sp["old_type_match"]))
        print("=" * 74)
        print("INDOK: {}".format(sp["reason"]))
        if not cid:
            print("  [HIBA] nincs ilyen orszag a torzsadatban — kihagyva")
            continue

        # Erintett meglevo sorok
        hit_types = [t["type_id"] for t in types
                     if fold(sp["old_type_match"]) in fold(t.get("name"))]
        old_rows = [f for f in fleets
                    if f["country_id"] == cid and f["type_id"] in hit_types]
        print("\n  Jelenlegi sorok:")
        for f in old_rows:
            print("    fleet_id {:<5} {:<28} {:<10} {}".format(
                f["fleet_id"], (type_name.get(f["type_id"]) or "")[:28],
                f.get("fleet_status"), f.get("quantity")))
        if not old_rows:
            print("    (nincs)")

        # Uj tipus
        nt = sp["new_type"]
        if nt["type_id"] in existing_types:
            print("\n  Uj tipus: {} — MAR LETEZIK, nem hozzuk letre ujra"
                  .format(nt["type_id"]))
        else:
            print("\n  Uj tipus letrehozasa: {} ({})".format(
                nt["type_id"], nt["name"]))
            actions.append(("create_type", nt))

        # Regi sor kezelese.
        #
        # KULCSFONTOSSAGU KORLAT: az ac_fleets tablan unique(country_id,
        # type_id, fleet_status) all. Ha ket meglevo sort UGYANARRA a
        # statuszra allitanank (pl. mindkettot 'retired'-re), a masodik
        # beszurasa utkozne, es a szkript felig vegzett allapotban allna meg.
        # Ezert statuszonkent legfeljebb EGY sort mozgatunk, es az ures
        # (0 vagy null mennyisegu) sorokat egyaltalan nem bantjuk — azokban
        # nincs informacio, amit at kellene menteni.
        if sp["old_action"]:
            target = sp["old_action"]["fleet_status"]
            taken = {f.get("fleet_status") for f in old_rows} - {target}
            already = [f for f in old_rows if f.get("fleet_status") == target]
            moved = False
            for f in sorted(old_rows,
                            key=lambda r: -(r.get("quantity") or 0)):
                if f.get("fleet_status") == target:
                    continue
                if not (f.get("quantity") or 0):
                    print("  Regi sor {} ({}, mennyiseg {}): ERINTETLEN — "
                          "ures sor, nincs mit atmenteni".format(
                              f["fleet_id"], f.get("fleet_status"),
                              f.get("quantity")))
                    continue
                if moved or already:
                    print("  Regi sor {} ({}): KIHAGYVA — mar van '{}' sor "
                          "erre a par-ra, az unique megszorítas miatt kezi "
                          "dontes kell".format(
                              f["fleet_id"], f.get("fleet_status"), target))
                    continue
                print("  Regi sor {}: {} -> {} (mennyiseg {} MEGMARAD)".format(
                    f["fleet_id"], f.get("fleet_status"), target,
                    f.get("quantity")))
                patch = {
                    "fleet_status": target,
                    "verification_note": sp["old_action"]["note"],
                    "verification_verdict": "corrected",
                    "verified_at": now,
                }
                if not sp["old_action"].get("keep_quantity"):
                    patch["quantity"] = None
                actions.append(("update_fleet", f["fleet_id"], patch))
                moved = True
            _ = taken
        else:
            print("  Regi sor: VALTOZATLAN (a meglevo allomany helyes)")

        # Utkozes-ellenorzes az UJ sorokra is: ha mar letezik ilyen
        # (orszag, tipus, statusz) harmas, ne probaljunk masodikat beszurni.
        existing_new = {(f["country_id"], f["type_id"], f.get("fleet_status"))
                        for f in fleets}

        # Uj flotta-sorok
        for nf in sp["new_fleets"]:
            key = (cid, nt["type_id"], nf["fleet_status"])
            if key in existing_new:
                print("  Uj flotta-sor {} / {}: MAR LETEZIK — kihagyva".format(
                    nt["type_id"], nf["fleet_status"]))
                continue
            print("  Uj flotta-sor: {} / {} / {} = {}".format(
                sp["country"], nt["type_id"], nf["fleet_status"],
                nf.get("quantity") if nf.get("quantity") is not None
                else nf.get("quantity_range_note", "(szam nelkul)")))
            row = {k: v for k, v in nf.items() if v is not None}
            row.update({"country_id": cid, "type_id": nt["type_id"],
                        "as_of": now[:10], "verified_at": now})
            actions.append(("create_fleet", row))

    print("\n" + "=" * 74)
    if not apply_mode:
        print("DRY-RUN — semmi nem valtozott. Az --apply {} muveletet "
              "hajtana vegre.".format(len(actions)))
        print("Semmi nem torlodne: a regi sor statuszt es indoklast kap, "
              "nem tunik el.")
        return

    done = 0
    for act in actions:
        try:
            if act[0] == "create_type":
                db.insert("ac_aircraft_types", act[1])
            elif act[0] == "update_fleet":
                db.update("ac_fleets", {"fleet_id": "eq." + str(act[1])},
                          act[2])
            elif act[0] == "create_fleet":
                db.insert("ac_fleets", act[1])
            done += 1
        except Exception as exc:  # noqa: BLE001
            print("  [warn] {}: {}".format(act[0], str(exc)[:110]))
    print("KESZ. {}/{} muvelet vegrehajtva. Sor nem torlodott."
          .format(done, len(actions)))


if __name__ == "__main__":
    main()
