# -*- coding: utf-8 -*-
"""import_fleet_verification.py — kulso flotta-ellenorzes visszatoltese.

BEMENET: a ChatGPT-ellenorzes CSV-je (flotta_ellenorzes_reszletes.csv),
pontosvesszovel tagolva.

A LEGFONTOSABB SZABALY: ez a szkript NEM ir be szamot ott, ahol az ellenorzes
nem adott egyertelmu szamot. Az ellenorzott ertekek jelentos resze szoveges
tartomany — "kb. 160-165 leltari allomany", "legalabb 4-5", "kb. 18 legacy
C/D; hadrafoghatosag ismeretlen". Ezeket szamma alakitani annyi, mint hamis
pontossagot gyartani egy olyan sorbol, amirol az ellenorzes kifejezetten azt
mondta, hogy bizonytalan. Ilyenkor a szoveg a quantity_range_note-ba kerul, a
quantity valtozatlan marad, es a sor 'unverifiable' iteletet kap.

NEGY ITELET, NEGY KULONBOZO KOVETKEZMENY:

  MEGERŐSÍTVE       -> a szam marad, de nyomot kap (ki, mikor, mi alapjan)
  HELYESBÍTVE       -> a szam frissul, HA egyertelmu egesz szam
  NEM ELLENŐRIZHETŐ -> a szam NEM valtozik; a tudasunk a jegyzetbe kerul
  TÖRLENDŐ          -> SEMMIT nem torlunk. 'needs_split' jelolest kap, mert
                       a sor ket kulonbozo dolgot kever (MQ-9A Reaper es
                       MQ-9B Protector), es a szetvalasztas elemzoi dontes.

A PROGRAMKERET SOHA NEM LESZ DARABSZAM. Kulon mezobe (program_total) megy.
Pontosan ez volt az ellenorzes fo talalata: a 29 gepes Apache-program nem 29
uzemelo helikopter.

NEV-ILLESZTES: a CSV csak orszag- es tipusnevet tartalmaz, azonositot nem.
Az illesztes normalizalt neven es aliason megy. Ha egy nev TOBB rekordra is
illik, a szkript NEM valaszt — jelenti es kihagyja. Egy rossz sorra irt
ellenorzes rosszabb, mint egy elmaradt frissites.

Hasznalat:
    python scripts\\import_fleet_verification.py <csv>            (dry-run)
    python scripts\\import_fleet_verification.py <csv> --apply

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import csv
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "data"

VERDICT_MAP = {
    "MEGERŐSÍTVE": "confirmed",
    "HELYESBÍTVE": "corrected",
    "NEM ELLENŐRIZHETŐ": "unverifiable",
    "TÖRLENDŐ": "needs_split",
}
CONF_MAP = {"magas": "high", "közepes": "medium", "alacsony": "low"}


def fold(s):
    t = unicodedata.normalize("NFKD", (s or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ı", "i").replace("ø", "o").replace("ł", "l")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def parse_qty(raw):
    """Visszaad: (szam vagy None, szoveges_alak vagy None).

    CSAK akkor ad szamot, ha a mezo EGYETLEN egesz szam. Minden mas —
    tartomany, "kb.", "legalabb", magyarazo szoveg — a szoveges againba
    kerul. Ez a szkript legfontosabb dontese: inkabb ne frissitsunk, mint
    hogy egy "kb. 160-165" ertekbol 160 legyen az adatbazisban, amirol
    ket het mulva mar senki nem tudja, hogy becsles volt."""
    s = (raw or "").strip()
    if not s:
        return None, None
    if re.match(r"^\d+$", s):
        return int(s), None
    return None, s


def load_master():
    countries = db.select("ac_countries", {"select": "*", "limit": "1000"})
    types = db.select("ac_aircraft_types", {"select": "*", "limit": "3000"})
    fleets = db.select("ac_fleets", {"select": "*", "limit": "10000"})
    return countries, types, fleets


# Tipusjel: betu(k) + szam, opcionalis kotojellel. A VALTOZAT-BETUT levagjuk,
# mert a katalogus alapnevet hasznal ("F-35 Lightning II"), a kulso ellenorzes
# viszont valtozatot ("F-35A Lightning II"). Igy lesz mindkettobol "f35".
#
# A valtozatot NEM dobjuk el veglegesen — a fleet-sor `variant` mezoje orzi,
# es az ellenorzes megjegyzese is tartalmazza. Csak az ILLESZTESHEZ hagyjuk
# figyelmen kivul; enelkul a 52 sorbol 40 sosem talalna gazdat.
DESIG_RX = re.compile(r"\b([a-z]{1,3})\s*-?\s*(\d{1,3})([a-z]{0,2})\b")


# A "Mk1", "Block 70" nem tipusjel, hanem valtozatjeloles — ha ezeket
# tipusjelkent kezelnenk, az "MQ-9 ... Mk1" barmely masik "Mk1"-re rallna.
VARIANT_PREFIX = {"mk", "blk", "block", "batch", "tranche", "lot"}


def designators(name):
    """Visszaadja a nevben talalhato tipusjeleket alap-alakban: 'F-35A' ->
    'f35', 'AH-64E' -> 'ah64', 'C-130J-30' -> 'c130'."""
    out = set()
    for m in DESIG_RX.finditer(fold(name)):
        if m.group(1) in VARIANT_PREFIX:
            continue
        out.add(m.group(1) + m.group(2))
    return out


def name_words(name):
    """Ertelmes szavak a tipusjeleken kivul: 'lightning', 'apache', 'gripen'.
    A rovid toredekeket ('ii', 'c', 'd') es a valtozatjeloloket ('block',
    'tranche') kihagyjuk — azok nem azonositjak a tipust."""
    stop = {"ii", "iii", "iv", "es", "and", "or", "valtozatok", "csalad",
            "katonai", "family", "block", "tranche", "batch", "variants"}
    out = set()
    for w in fold(name).split():
        if len(w) > 3 and not any(c.isdigit() for c in w) and w not in stop:
            out.add(w)
    return out


def build_index(rows, id_col, name_col):
    """nev -> [id, ...]  (a nevbol tobb is lehet: ezt jelezni kell)"""
    idx = defaultdict(list)
    meta = {}
    for r in rows:
        names = [r.get(name_col)]
        raw = r.get("aliases")
        aliases = raw if isinstance(raw, list) else (
            json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("[")
            else [])
        names += [a for a in aliases if isinstance(a, str)]
        for n in names:
            if fold(n):
                idx[fold(n)].append(r[id_col])
        d, w = set(), set()
        for n in names:
            d |= designators(n)
            w |= name_words(n)
        prev = meta.get(r[id_col], (set(), set(), r.get(name_col)))
        meta[r[id_col]] = (prev[0] | d, prev[1] | w, r.get(name_col))
    return {k: sorted(set(v)) for k, v in idx.items() if k}, meta


def resolve(idx, name, meta=None):
    """Visszaad: ([id, ...], mod, [javasolt nevek])"""
    key = fold(name)
    if key in idx:
        return idx[key], "pontos", []

    words = key.split()
    cands = {k: v for k, v in idx.items()
             if words and all(w in k.split() for w in words)}
    if len(cands) == 1:
        return list(cands.values())[0], "reszleges", []

    if meta is None:
        return [], ("tobbertelmu" if cands else "nincs"), []

    # TIPUSJEL-ALAPU ILLESZTES. Ez fogja meg az "F-35A" <-> "F-35" esetet.
    # KOVETELMENY: a tipusjel egyezzen, ES ha a nevben van beszelo szo
    # (Apache, Gripen, Lightning), az is. Csak igy kerulheto el, hogy a
    # "F-16C/D Block 70" barmelyik F-16 rekordra ralljon.
    d, w = designators(name), name_words(name)
    hits = []
    for tid, (td, tw, tname) in meta.items():
        if d and td:
            # Mindketto oldalon van tipusjel: az EGYEZES kotelezo. Ha ezen
            # felul mindket oldalon van beszelo nev is, annak is egyeznie
            # kell — kulonben az "F-16C/D Block 70" barmelyik F-16-ra rallna.
            if not (d & td):
                continue
            if w and tw and not (w & tw):
                continue
        else:
            # Legalabb az egyik oldalon nincs tipusjel (pl. "Rafale B/C/M",
            # "GlobalEye"). Ilyenkor a nev donthet — de csak akkor, ha van
            # mit osszehasonlitani.
            if not (w and tw and (w & tw)):
                continue
        hits.append((tid, tname))
    if len(hits) == 1:
        return [hits[0][0]], "tipusjel", []
    if len(hits) > 1:
        # TOBB TALALAT: nem valasztunk. Egy rossz sorra irt ellenorzes
        # rosszabb, mint egy elmaradt frissites — de megmutatjuk, mik a
        # jeloltek, hogy kezzel egy perc alatt rendezheto legyen.
        return [], "tobbertelmu", [n for _i, n in hits][:6]
    return [], "nincs", []


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_mode = "--apply" in sys.argv
    # Alapertelmezett bemenet: a projektbe bemasolt ellenorzesi CSV. Igy a
    # szkript utvonal nelkul is fut — egy elgepelt vagy sortorott utvonal
    # miatt ne legyen ujabb kor.
    csv_path = Path(args[0]) if args else (
        OUT_DIR / "verification" / "flotta_ellenorzes_reszletes.csv")
    if not csv_path.exists():
        print("Nem talalhato: {}\n".format(csv_path))
        print("Add meg a CSV utvonalat argumentumkent, EGY sorban:")
        print("  python scripts\\import_fleet_verification.py "
              "data\\verification\\flotta_ellenorzes_reszletes.csv")
        return
    print("Bemenet: {}".format(csv_path))

    with io.open(str(csv_path), "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    print("Ellenorzesi sorok: {}".format(len(rows)))

    countries, types, fleets = load_master()
    cidx, _cmeta = build_index(countries, "country_id", "name")
    tidx, tmeta = build_index(types, "type_id", "name")
    print("Torzsadat: {} orszag, {} tipus, {} flotta-sor".format(
        len(countries), len(types), len(fleets)))

    # Kezi megfeleltetes. Ha egy tipusnevet a szkript nem tud egyertelmuen
    # feloldani, ide beirva egyszer s mindenkorra rendezheto — a kovetkezo
    # ellenorzesi kornel is ervenyes marad.
    overrides = {}
    omap = OUT_DIR / "verification" / "type_name_map.csv"
    if omap.exists():
        with io.open(str(omap), "r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                src = fold(row.get("csv_tipusnev"))
                tid = (row.get("type_id") or "").strip()
                if src and tid:
                    overrides[src] = tid
        print("Kezi megfeleltetes: {} sor ({})".format(len(overrides), omap.name))
    print("")

    by_pair = defaultdict(list)
    for f in fleets:
        by_pair[(f["country_id"], f["type_id"])].append(f)

    plans, problems = [], []
    now = datetime.now(timezone.utc).isoformat()

    for r in rows:
        verdict = VERDICT_MAP.get((r.get("itelet") or "").strip())
        cids, cway, _ = resolve(cidx, r.get("orszag"))
        ov = overrides.get(fold(r.get("tipus")))
        if ov:
            tids, tway, tsug = [ov], "kezi", []
        else:
            tids, tway, tsug = resolve(tidx, r.get("tipus"), tmeta)

        if len(cids) != 1 or len(tids) != 1:
            problems.append({
                "sor_id": r.get("sor_id"), "orszag": r.get("orszag"),
                "tipus": r.get("tipus"),
                "ok": "orszag: {} ({}), tipus: {} ({})".format(
                    len(cids), cway, len(tids), tway),
                "javasolt_katalogus_nevek": " | ".join(tsug),
            })
            continue
        cid, tid = cids[0], tids[0]
        targets = by_pair.get((cid, tid), [])
        if not targets:
            problems.append({
                "sor_id": r.get("sor_id"), "orszag": r.get("orszag"),
                "tipus": r.get("tipus"),
                "ok": "nincs flotta-sor erre a par-ra ({} / {})".format(cid, tid),
            })
            continue

        act_n, act_txt = parse_qty(r.get("ellenorzott_active"))
        ord_n, ord_txt = parse_qty(r.get("firm_on_order"))
        prog_n, _prog_txt = parse_qty(
            r.get("programkeret_vagy_korrigalt_osszes"))
        date_raw = (r.get("ervenyes_datum") or "").strip()
        vdate = date_raw if re.match(r"^\d{4}-\d{2}-\d{2}$", date_raw) else None

        for fl in targets:
            st = fl.get("fleet_status")
            if st in ("active", "retiring"):
                num, txt = act_n, act_txt
            elif st == "on_order":
                num, txt = ord_n, ord_txt
            else:
                num, txt = None, None

            patch = {
                "verification_verdict": verdict,
                "verification_confidence": CONF_MAP.get(
                    (r.get("megbizhatosag") or "").strip()),
                "verification_source": (r.get("forras_1") or "")[:400] or None,
                "verification_source_url": (r.get("forras_url_1") or "")[:400] or None,
                "verification_note": (r.get("reszletes_megjegyzes") or "")[:1000] or None,
                "verified_as_of": vdate,
                "verified_at": now,
                "program_total": prog_n,
                "quantity_range_note": txt,
            }
            # SZAMOT CSAK akkor irunk, ha egyertelmu ES az itelet engedi.
            change = None
            if verdict in ("confirmed", "corrected") and num is not None:
                patch["verified_quantity"] = num
                if num != fl.get("quantity"):
                    patch["quantity"] = num
                    change = "{} -> {}".format(fl.get("quantity"), num)
            plans.append({"fleet": fl, "row": r, "patch": patch,
                          "verdict": verdict, "status": st,
                          "change": change, "range": txt})

    # ---- riport ----------------------------------------------------------
    per_verdict = defaultdict(int)
    for p in plans:
        per_verdict[p["verdict"]] += 1
    changed = [p for p in plans if p["change"]]
    ranged = [p for p in plans if p["range"] and not p["change"]]

    print("=" * 76)
    print("ILLESZTETT FLOTTA-SOROK: {}".format(len(plans)))
    print("=" * 76)
    for k in ("confirmed", "corrected", "unverifiable", "needs_split"):
        if per_verdict[k]:
            print("  {:<14} {}".format(k, per_verdict[k]))

    print("\nDARABSZAM-VALTOZAS ({} sor):".format(len(changed)))
    for p in changed:
        print("  {:<16} {:<26} {:<9} {}".format(
            p["row"]["orszag"][:16], p["row"]["tipus"][:26],
            p["status"], p["change"]))

    print("\nSZAM HELYETT TARTOMANY ({} sor) — a quantity NEM valtozik:"
          .format(len(ranged)))
    for p in ranged[:20]:
        print("  {:<16} {:<24} {:<9} {}".format(
            p["row"]["orszag"][:16], p["row"]["tipus"][:24],
            p["status"], p["range"][:46]))

    if problems:
        print("\n" + "=" * 76)
        print("NEM ILLESZTHETO SOROK ({}) — ezeket kezzel kell rendezni"
              .format(len(problems)))
        print("=" * 76)
        for p in problems:
            print("  [{}] {:<16} {:<28} {}".format(
                p["sor_id"], p["orszag"][:16], p["tipus"][:28], p["ok"]))
            if p.get("javasolt_katalogus_nevek"):
                print("       jeloltek: {}".format(
                    p["javasolt_katalogus_nevek"]))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        pp = OUT_DIR / "fleet_verification_unmatched.csv"
        with io.open(str(pp), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(problems[0].keys()),
                               delimiter=";")
            w.writeheader()
            w.writerows(problems)
        print("\n  CSV: {}".format(pp))

        # Kitoltendo megfeleltetesi sablon — a "tipus: 0 (nincs)" eseteknel
        # ez az egyetlen tisztesseges megoldas: nem talalgatunk, hanem
        # egyszer kezzel rogzitjuk, es utana orokre ervenyes.
        tmpl = OUT_DIR / "verification" / "type_name_map.csv"
        if not tmpl.exists():
            tmpl.parent.mkdir(parents=True, exist_ok=True)
            with io.open(str(tmpl), "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["csv_tipusnev", "type_id", "javasolt_nevek"])
                for p in problems:
                    w.writerow([p["tipus"], "",
                                p.get("javasolt_katalogus_nevek", "")])
            print("  Megfeleltetesi sablon: {}".format(tmpl))
            print("  Toltsd ki a type_id oszlopot, es futtasd ujra — a "
                  "szkript automatikusan hasznalja.")

    splits = [p for p in plans if p["verdict"] == "needs_split"]
    if splits:
        print("\nSZERKEZETI HIBA — szetvalasztando sor ({}):".format(len(splits)))
        for p in splits:
            print("  {} {} — {}".format(
                p["row"]["orszag"], p["row"]["tipus"],
                p["row"]["reszletes_megjegyzes"][:110]))
        print("  Ezekbol SEMMIT nem torlunk: a 'needs_split' jeloles marad, a "
              "szetvalasztas elemzoi dontes.")

    if not apply_mode:
        print("\nDRY-RUN — semmi nem valtozott. Az --apply {} sort jelolne "
              "meg, ebbol {} darabszamot is frissitene.".format(
                  len(plans), len(changed)))
        return

    ok = 0
    for p in plans:
        patch = {k: v for k, v in p["patch"].items() if v is not None}
        try:
            db.update("ac_fleets",
                      {"fleet_id": "eq." + str(p["fleet"]["fleet_id"])}, patch)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print("  [warn] fleet_id {}: {}".format(
                p["fleet"]["fleet_id"], str(exc)[:80]))
    print("\nKESZ. {} sor kapott hitelesitesi nyomot, ebbol {} darabszam "
          "frissult. Sor nem torlodott.".format(ok, len(changed)))


if __name__ == "__main__":
    main()
