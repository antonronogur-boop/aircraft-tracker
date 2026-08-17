# -*- coding: utf-8 -*-
"""Regresszios tesztek az entitas-illesztesre.

A W34 jelentesben a Beriev A-100LL veszteseget "A-10 Thunderbolt II — Loss x1"
sorkent jelenitette meg a rendszer. Ez a teszt azt a hibaosztalyt zarja le, es
egyben rogziti, hogy a valodi variansok TOVABBRA IS illeszkedjenek.

Futtatas:  python scripts/test_ac_match.py
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ac_match  # noqa: E402

CATALOGUE = HERE.parent / "data" / "aircraft_catalogue.json"


def load_catalogue():
    raw = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        for key in ("aircraft_types", "types", "aircraft"):
            if key in raw:
                return raw[key]
        raise SystemExit("unexpected catalogue shape: {}".format(list(raw)[:5]))
    return raw


def legacy_match(value, index):
    """A KORABBI implementacio — csak osszehasonlitasi alapkent."""
    if not value:
        return None
    v = value.strip().lower()
    if v in index:
        return index[v]
    for alias, ident in sorted(index.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 4 and alias in v:
            return ident
    return None


# (bemenet, elvart type_id vagy None, elvart match_kind-halmaz)
# None = nem szabad illeszteni; a hivo unresolved_type_name-be teszi es
# review-ba kerul. Ez MINDIG jobb, mint egy csendben rossz FK.
CASES = [
    # --- a hibaosztaly, ami miatt a modul letezik ---
    ("A-100LL",                     None,      {"none"}),
    ("Beriev A-100LL",              None,      {"none"}),
    ("A-100",                       None,      {"none"}),
    ("Beriev A-100 Premier",        None,      {"none"}),
    # --- valodi variansok: TOVABBRA IS illeszkedniuk kell ---
    ("A-10C Thunderbolt II",        "a-10",    {"variant"}),
    ("A-10",                        "a-10",    {"exact", "family"}),
    # A katalogus kanonikus DESIGNATIONJE variansszintu ("F-15EX Eagle II"),
    # de a forras ettol meg variansot figyelt meg — a match_kind ezt tukrozze,
    # kulonben az ORBAT csalad-baseline-t rendel egy varians-esemenyhez.
    ("F-15EX Eagle II",             "f-15",    {"variant"}),
    ("F-16V",                       "f-16",    {"variant"}),
    ("F-16C/D Block 70",            "f-16",    {"variant"}),
    ("C-130J-30 Super Hercules",    "c-130",   {"variant"}),
    ("AH-64E Apache Guardian",      "ah-64",   {"variant"}),
    ("KC-46A Pegasus",              "kc-46",   {"variant"}),
    ("MQ-9B SeaGuardian",           "mq-9",    {"variant"}),
    # --- nev szerinti tipusok ---
    ("Gripen E",                    "gripen",  {"variant", "family", "exact"}),
    # --- unicode kotojel (sajtó-szovegek) ---
    ("F‑35A Lightning II",     "f-35",    {"variant", "exact", "family"}),
]

# A varians-tudatossag: a HH-60W a katalogus szerint a uh-60 CSALAD tagja
# (aliases: [..., 'HH-60', ...]), tehat az illesztes helyes. A hiba nem itt
# van, hanem ott, hogy az ORBAT ezutan a TELJES csalad-baseline-t (UH-60
# Active 2000) mutatja egy 26 gepes HH-60W esemeny melle.
#
# Amit a matchernek garantalnia kell: a varians-szintu megfigyeles VARIANS-
# kent legyen jelolve, es a variant_raw meg legyen orizve — kulonben az ORBAT
# nem tudja, hogy nem szabad csalad-szintu szamot mutatnia.
VARIANT_MARKING = [
    ("HH-60W Jolly Green II", "uh-60"),
    ("UH-60M",                "uh-60"),
    ("F-15EX Eagle II",       "f-15"),
    ("A-10C Thunderbolt II",  "a-10"),
]


def main():
    rows = load_catalogue()
    index = ac_match.build_index(
        rows, "type_id", name_keys=("name", "designation"))
    print("catalogue entries: {}  aliases indexed: {}".format(
        len(rows), len(index)))

    # A legacy index ugyanugy epul, mint a regi process_articles-ben.
    legacy_index = {}
    for t in rows:
        for v in [t["type_id"], t.get("name"), t.get("designation")] \
                + list(t.get("aliases") or []):
            if v:
                legacy_index[str(v).lower()] = t["type_id"]

    failures, regressions = [], []
    print("\n{:<30} {:<10} {:<10} {:<10}".format(
        "input", "expected", "got", "kind"))
    print("-" * 64)
    for text, expected, kinds in CASES:
        tid, variant, kind = ac_match.match_type(text, index)
        ok = (tid == expected) and (kind in kinds)
        legacy = legacy_match(text, legacy_index)
        flag = "ok " if ok else "FAIL"
        note = ""
        if legacy != expected and tid == expected:
            note = "  <- legacy gave {!r}".format(legacy)
        print("{:<30} {:<10} {:<10} {:<10} {}{}".format(
            text[:29], str(expected), str(tid), kind, flag, note))
        if not ok:
            failures.append((text, expected, tid, kind))

    print("\nVariant marking — a variant-level observation must be labelled as"
          " such and keep its raw designation, so ORBAT cannot attach a"
          " family-wide baseline to it:")
    for text, family in VARIANT_MARKING:
        tid, variant, kind = ac_match.match_type(text, index)
        ok = (tid == family) and kind == "variant" and bool(variant)
        print("  {:<26} -> {!s:<8} kind={:<8} variant_raw={!r} {}".format(
            text[:25], tid, kind, variant, "ok" if ok else "FAIL"))
        if not ok:
            failures.append((text, "{} + variant".format(family), tid, kind))

    # Kereszt-ellenorzes: a teljes katalogus MINDEN tipusjele illeszkedjen
    # onmagara, es SOHA ne illeszkedjen egy masik tipus szamjegy-kiterjesztesere.
    print("\nSelf-consistency across the full catalogue:")
    self_fail = 0
    for t in rows:
        tid = t["type_id"]
        got, _, kind = ac_match.match_type(tid, index)
        if got != tid:
            self_fail += 1
            print("  FAIL self-match {!r} -> {!r}".format(tid, got))
    print("  {} / {} type_ids match themselves".format(
        len(rows) - self_fail, len(rows)))
    if self_fail:
        failures.append(("self-match", len(rows), len(rows) - self_fail, ""))

    # Szamjegy-prefix utkozesek felderitese a katalogusban: melyik tipusjel
    # prefixe egy masiknak? Ezek a jovobeli A-100LL-esetek.
    print("\nDigit-prefix collision pairs in the catalogue (the A-10/A-100 "
          "class):")
    ids = [t["type_id"] for t in rows]
    pairs = 0
    for a in ids:
        for b in ids:
            if a != b and b.startswith(a) and len(b) > len(a) \
                    and b[len(a)].isdigit():
                got, _, _ = ac_match.match_type(b, index)
                print("  {!r} is a digit-prefix of {!r} -> resolves to {!r} "
                      "{}".format(a, b, got, "ok" if got == b else "FAIL"))
                pairs += 1
                if got != b:
                    failures.append((b, b, got, ""))
    if not pairs:
        print("  none present today — the boundary rule guards future ones")

    print("\n" + "=" * 64)
    if regressions:
        print("Legacy behaviour reproduced the reported defect for: {}".format(
            ", ".join(t for t, _ in regressions)))
    if failures:
        print("FAILURES: {}".format(len(failures)))
        for f in failures:
            print("  {}".format(f))
        return 1
    print("All matcher checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
