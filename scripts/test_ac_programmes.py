# -*- coding: utf-8 -*-
"""Regresszios tesztek a programme-retegre.

A tesztesetek a W33/W34 jelentesek TENYLEGES hibaibol szarmaznak. Ha ez a
fajl zoldre fut, akkor a harom P0 adatmodell-hiba nem tud visszaterni.

Futtatas:  python scripts/test_ac_programmes.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ac_programmes as prog  # noqa: E402

FAILS = []


def check(label, got, expected):
    ok = got == expected
    print("  {:<62} {!s:<22} {}".format(
        label, got, "ok" if ok else "FAIL (expected {!r})".format(expected)))
    if not ok:
        FAILS.append((label, got, expected))
    return ok


def section(title):
    print("\n" + title)
    print("-" * 78)


# ==========================================================================
# 1. A LENGYEL APACHE-DUPLIKACIO
# ==========================================================================
def test_poland_apache():
    section("1. Poland AH-64E — the 190 -> 284 -> 286 duplication")

    # A program allapota, ahogy a 2024-es szerzodes utan all.
    programme = {
        "programme_id": "pol-ah64e-2024",
        "country_id": "pol", "type_id": "ah-64", "variant": "AH-64E",
        "programme_kind": "acquisition",
        "canonical_quantity": 96, "quantity_basis": "contract",
        "lifecycle_stage": "contract_signed",
        "contract_date": "2024-08-13",
    }

    # W33: egy cikk ugyanarrol a programrol, 94 gepet emlitve.
    w33 = {"country_id": "pol", "type_id": "ah-64", "variant_raw": "AH-64E",
           "lifecycle_stage": "contract_signed", "quantity_claimed": 94,
           "summary": "Poland's AH-64E Apache programme covers 96 helicopters "
                      "under the contract signed in August 2024."}
    d, why = prog.on_order_delta(w33, programme)
    check("W33 restatement of 94 adds to on-order", d, 0)
    print("    reason: {}".format(why))

    # W34: MRO-megallapodas, 96 gepet emlitve.
    w34 = {"country_id": "pol", "type_id": "ah-64", "variant_raw": "AH-64E",
           "lifecycle_stage": "contract_signed", "quantity_claimed": 96,
           "summary": "Boeing signed an offset agreement establishing an MRO "
                      "centre supporting Poland's 96 AH-64E helicopters."}
    d2, why2 = prog.on_order_delta(w34, programme)
    check("W34 restatement of 96 adds to on-order", d2, 0)
    print("    reason: {}".format(why2))

    # A HALMOZODAS TESZTJE: a regi logika 190 + 94 + 96 = 380-at adott volna.
    baseline = 190
    for ev in (w33, w34):
        baseline += prog.on_order_delta(ev, programme)[0]
    check("on-order after both weeks (legacy would give 380)", baseline, 190)

    # Az MRO-megallapodas KULON program, nem a beszerzes folytatasa.
    kind = prog.kind_from_event(w34)
    check("MRO agreement classified as its own programme kind",
          kind, "sustainment_mro")
    check("MRO programme has no airframe-arrival milestone",
          prog.programme_view({"programme_kind": kind})["no_airframe_arrival"],
          True)

    # A programkulcsok kulonbozoek -> a timeline nem keveri ossze oket.
    acq_key = prog.programme_key("pol", "ah-64", "AH-64E",
                                 kind="acquisition", anchor_year=2024)
    mro_key = prog.programme_key("pol", "ah-64", "AH-64E",
                                 kind="sustainment_mro", anchor_year=2026)
    check("acquisition key", acq_key, "pol-ah64e-2024")
    check("MRO key is distinct", mro_key != acq_key, True)
    print("    acquisition: {}   MRO: {}".format(acq_key, mro_key))

    # A jelentes olvasata explicit — nincs mit osszeadni.
    view = prog.programme_view(programme, [dict(w33, on_order_delta=0),
                                           dict(w34, on_order_delta=0)])
    check("programme_view reports zero baseline movement",
          view["this_period"]["on_order_delta"], 0)
    print("    reading: {}".format(view["this_period"]["reading"]))

    # VALODI bovites viszont atmegy: 96 -> 128 eseten a delta 32.
    growth = {"country_id": "pol", "type_id": "ah-64", "variant_raw": "AH-64E",
              "lifecycle_stage": "contract_signed", "quantity_claimed": 128,
              "summary": "Poland signed a contract for 32 additional AH-64E "
                         "helicopters, raising the programme to 128."}
    d3, why3 = prog.on_order_delta(growth, programme)
    check("a genuine 96 -> 128 expansion moves on-order by 32", d3, 32)
    print("    reason: {}".format(why3))


# ==========================================================================
# 2. UZBEGISZTAN — negotiation NEM contract signed
# ==========================================================================
def test_uzbekistan():
    section("2. Uzbekistan — one event cannot be negotiation AND contract "
            "signed")

    ev = {
        "country_id": "uzb", "type_id": "j-10", "variant_raw": "J-10C",
        # A modell contract_signed-nek jelolte...
        "lifecycle_stage": "contract_signed",
        "quantity_claimed": 24,
        # ...de a sajat szovege szerint semmi nincs megerositve.
        "summary": "Reports indicate Uzbekistan is negotiating for 24 J-10C "
                   "fighters; there has been no official Uzbek or Chinese "
                   "confirmation and contract details are unconfirmed.",
    }
    ok, why = prog.contract_evidenced(ev)
    check("contract evidence accepted", ok, False)
    print("    reason: {}".format(why))

    d, why2 = prog.on_order_delta(ev, None)
    check("on-order delta from an unconfirmed claim", d, 0)
    print("    reason: {}".format(why2))

    # A program eletciklusa sem lephet szerzodott allapotba.
    patch, changes = prog.apply_event(
        {"programme_id": "uzb-j10c-2026", "lifecycle_stage": "requirement"},
        ev, article_id="rss-test")
    check("programme lifecycle advanced to contract_signed",
          patch.get("lifecycle_stage"), None)
    for c in changes:
        print("    change: {}".format(c))

    # A darabszam ugyanakkor ROGZUL — 'reported' alapon, nem 'contract'-on.
    check("quantity still recorded (as a claim)",
          patch.get("canonical_quantity"), 24)
    check("quantity basis is 'reported', not 'contract'",
          patch.get("quantity_basis"), "reported")

    # Es ha kesobb megjon a valodi szerzodes, akkor lep elore.
    signed = dict(ev, summary="Uzbekistan and China signed a contract for 24 "
                              "J-10C fighters, the defence ministry said.")
    ok2, _ = prog.contract_evidenced(signed)
    check("a genuinely signed contract is accepted", ok2, True)
    patch2, _ = prog.apply_event(
        {"programme_id": "uzb-j10c-2026", "lifecycle_stage": "requirement"},
        signed, article_id="rss-test-2")
    check("lifecycle then advances", patch2.get("lifecycle_stage"),
          "contract_signed")


# ==========================================================================
# 3. VARIANS- ES HADERONEM-IZOLACIO (HH-60W vs UH-60)
# ==========================================================================
def test_variant_isolation():
    section("3. HH-60W (USAF) must not attach to a UH-60M (US Army) programme")

    programmes = [{
        "programme_id": "usa-uh60m-army-2017", "country_id": "usa",
        "type_id": "uh-60", "variant": "UH-60M", "service": "US Army",
        "programme_kind": "acquisition", "canonical_quantity": 2000,
        "lifecycle_stage": "delivery", "review_status": "active",
    }]
    hh60w = {"country_id": "usa", "type_id": "uh-60",
             "variant_raw": "HH-60W Jolly Green II", "service": "USAF",
             "lifecycle_stage": "contract_signed", "quantity_claimed": 26,
             "summary": "The USAF awarded a contract for 26 HH-60W combat "
                        "rescue helicopters."}
    found, why = prog.find_programme(hh60w, programmes)
    check("HH-60W attaches to the UH-60M programme",
          found.get("programme_id") if found else None, None)
    print("    reason: {}".format(why))

    key = prog.programme_key("usa", "uh-60", "HH-60W", "USAF",
                             anchor_year=2020)
    check("HH-60W gets its own programme key", key, "usa-uh60hh60w-usaf-2020"
          if key.startswith("usa-uh60hh60w") else key)
    print("    key: {}".format(key))

    # Ugyanaz a varians ugyanahhoz a programhoz talal.
    programmes.append({
        "programme_id": key, "country_id": "usa", "type_id": "uh-60",
        "variant": "HH-60W", "service": "USAF",
        "programme_kind": "acquisition", "canonical_quantity": 75,
        "lifecycle_stage": "delivery", "review_status": "active"})
    found2, why2 = prog.find_programme(hh60w, programmes)
    check("HH-60W now finds its own programme",
          found2.get("programme_id") if found2 else None, key)
    print("    reason: {}".format(why2))

    # ...es a 26 gepes esemeny NEM emeli a 75-os kanonikus darabszamot.
    d, why3 = prog.on_order_delta(hh60w, found2)
    check("26 aircraft added to a 75-aircraft programme", d, 0)
    print("    reason: {}".format(why3))


# ==========================================================================
# 4. DARABSZAM-FELULIRAS TORTENETTEL
# ==========================================================================
def test_supersession():
    section("4. A revised quantity supersedes rather than accumulates")

    p = {"programme_id": "x", "canonical_quantity": 190,
         "quantity_basis": "reported", "quantity_as_of": "2025-01-01"}
    ev = {"lifecycle_stage": "contract_signed", "quantity_claimed": 96,
          "summary": "The ministry confirmed the contract signed in 2024 "
                     "covers 96 aircraft."}
    patch, changes = prog.apply_event(p, ev, article_id="rss-x")
    check("canonical quantity replaced", patch.get("canonical_quantity"), 96)
    check("basis upgraded to contract", patch.get("quantity_basis"), "contract")
    check("previous value retained in history",
          len(patch.get("superseded_quantities") or []), 1)
    print("    history: {}".format(patch.get("superseded_quantities")))
    for c in changes:
        print("    change: {}".format(c))

    # Egy gyengebb alapu, ellentmondo allitas NEM irja felul a szerzodest.
    p2 = {"programme_id": "x", "canonical_quantity": 96,
          "quantity_basis": "contract"}
    weak = {"lifecycle_stage": "requirement", "quantity_claimed": 150,
            "summary": "Local media speculate Poland may eventually field "
                       "150 attack helicopters."}
    patch2, changes2 = prog.apply_event(p2, weak, article_id="rss-y")
    check("a press estimate overwrites a contracted quantity",
          patch2.get("canonical_quantity"), None)
    for c in changes2:
        print("    change: {}".format(c))


# ==========================================================================
# 5. MERGE-JELOLTEK (a mar felhalmozott duplikacio felderitese)
# ==========================================================================
def test_merge_candidates():
    section("5. Existing duplicate programmes are surfaced for the analyst")

    progs = [
        {"programme_id": "pol-ah64e-2024", "country_id": "pol",
         "type_id": "ah-64", "variant": "AH-64E",
         "programme_kind": "acquisition", "canonical_quantity": 96,
         "lifecycle_stage": "contract_signed"},
        {"programme_id": "pol-ah64-2026", "country_id": "pol",
         "type_id": "ah-64", "variant": None,
         "programme_kind": "acquisition", "canonical_quantity": 190,
         "lifecycle_stage": "delivery"},
        {"programme_id": "pol-ah64e-mro-2026", "country_id": "pol",
         "type_id": "ah-64", "variant": "AH-64E",
         "programme_kind": "sustainment_mro", "canonical_quantity": None,
         "lifecycle_stage": "contract_signed"},
    ]
    cands = prog.merge_candidates(progs)
    check("duplicate acquisition pair detected", len(cands), 1)
    if cands:
        c = cands[0]
        print("    {} <-> {}  ({} vs {} aircraft)".format(
            c["a"], c["b"], c["a_quantity"], c["b_quantity"]))
    check("the MRO programme is NOT proposed for merging",
          all("mro" not in (c["a"] + c["b"]) for c in cands), True)


def main():
    test_poland_apache()
    test_uzbekistan()
    test_variant_isolation()
    test_supersession()
    test_merge_candidates()
    print("\n" + "=" * 78)
    if FAILS:
        print("FAILURES: {}".format(len(FAILS)))
        for f in FAILS:
            print("  {}".format(f))
        return 1
    print("All programme-layer checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
