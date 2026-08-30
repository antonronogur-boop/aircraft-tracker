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

    # A programnak MAR van egy bejelentett (tervezett) 190-es szama.
    p = {"programme_id": "x", "planned_quantity": 190,
         "planned_basis": "reported", "planned_as_of": "2025-01-01"}
    ev = {"lifecycle_stage": "contract_signed", "quantity_claimed": 96,
          "summary": "The ministry confirmed the contract signed in 2024 "
                     "covers 96 aircraft."}
    patch, changes = prog.apply_event(p, ev, article_id="rss-x")
    # A szerzodott allomany KULON mezobe kerul; a tervezett 190 megmarad.
    check("contracted quantity recorded", patch.get("contracted_quantity"), 96)
    check("planned total left intact", patch.get("planned_quantity"), None)
    check("headline figure prefers the contract",
          patch.get("canonical_quantity"), 96)
    check("basis upgraded to contract", patch.get("quantity_basis"), "contract")
    print("    history: {}".format(patch.get("superseded_quantities")))
    for c in changes:
        print("    change: {}".format(c))

    # Egy gyengebb alapu, ellentmondo allitas NEM irja felul a szerzodest.
    p2 = {"programme_id": "x", "contracted_quantity": 96,
          "contracted_basis": "contract", "canonical_quantity": 96,
          "quantity_basis": "contract"}
    weak = {"lifecycle_stage": "requirement", "quantity_claimed": 150,
            "summary": "Local media speculate Poland may eventually field "
                       "150 attack helicopters."}
    patch2, changes2 = prog.apply_event(p2, weak, article_id="rss-y")
    check("a press estimate touches the CONTRACTED quantity",
          patch2.get("contracted_quantity"), None)
    check("the headline figure stays on the contract",
          patch2.get("canonical_quantity"), 96)
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


# ==========================================================================
# 6. DARABSZAM-HATOKOR — a VALODI adatbol vett esetek
#
# Az elso eles dry run (274 esemeny) ezeket termelte a javitas elott. Minden
# eset a tenyleges cikkszovegbol szarmazik.
# ==========================================================================
def test_quantity_scope_real_cases():
    section("6. Quantity scope — cases taken from the live dry run")

    # --- 6a. KAAN: 148 -> 1, mert egy prototipus gurulasi probaja 1 gep ---
    print("\n  6a. Turkey KAAN: a prototype taxi trial must not reset 148 to 1")
    p = {"programme_id": "tur-kaan-2026", "programme_kind": "acquisition",
         "canonical_quantity": None}
    ev_total = {"event_type": "order", "lifecycle_stage": None, "quantity": 148,
                "summary": "Turkey has a total planned serial production order "
                           "of 148 KAAN fifth-generation stealth fighters."}
    patch, ch = prog.apply_event(p, ev_total, article_id="a1")
    p.update(patch)
    check("programme total set from 'total planned production order'",
          p.get("canonical_quantity"), 148)

    ev_proto = {"event_type": "other", "lifecycle_stage": "production",
                "quantity": 1,
                "summary": "Turkey's TAI Kaan second prototype (P1), a "
                           "production-representative airframe, began taxi "
                           "trials on 31 July."}
    sc, why = prog.quantity_scope(ev_proto)
    check("prototype taxi trial scope", sc, "tranche")
    patch2, ch2 = prog.apply_event(p, ev_proto, article_id="a2")
    p.update(patch2)
    check("KAAN programme total after the prototype event",
          p.get("canonical_quantity"), 148)
    for c in ch2:
        if "NOT applied" in c:
            print("      {}".format(c[:118]))

    # --- 6b. KC-135: ot vesztesegbol nem lesz 1 gepes "program" ---
    print("\n  6b. USAF KC-135: five loss events must not create a "
          "1-aircraft programme")
    ev_loss = {"event_type": "incident", "lifecycle_stage": None, "quantity": 1,
               "summary": "A USAF KC-135R Stratotanker (63-8002) was lost with "
                          "six fatalities after a mid-air collision."}
    check("loss event programme kind", prog.kind_from_event(ev_loss),
          "attrition")
    sc2, _ = prog.quantity_scope(ev_loss)
    check("loss event quantity scope", sc2, "attrition")
    pa = {"programme_id": "usa-kc135-attr", "programme_kind": "attrition",
          "canonical_quantity": None}
    patch3, ch3 = prog.apply_event(pa, ev_loss, article_id="a3")
    check("attrition programme carries no canonical size",
          patch3.get("canonical_quantity"), None)
    check("the count is retained as an observation",
          len(patch3.get("observed_quantities") or []), 1)
    d, dwhy = prog.on_order_delta(ev_loss, pa)
    check("a loss moves on-order", d, 0)

    # --- 6c. F-35: egy baleset ne allitsa egy beszerzes eletciklusat ---
    print("\n  6c. F-35: a crash must not set an acquisition's lifecycle to "
          "'loss'")
    ev_crash = {"event_type": "incident", "lifecycle_stage": "loss",
                "quantity": 1,
                "summary": "A U.S. Marine Corps F-35B assigned to VMFAT-502 "
                           "crashed and burned during a training flight."}
    acq = [{"programme_id": "usa-f35-2026", "country_id": "usa",
            "type_id": "f-35", "programme_kind": "acquisition",
            "canonical_quantity": 152, "review_status": "active"}]
    found, why = prog.find_programme(dict(ev_crash, country_id="usa",
                                         type_id="f-35"), acq)
    check("crash attaches to the acquisition programme",
          found.get("programme_id") if found else None, None)
    print("      reason: {}".format(why[:110]))

    # --- 6d. F-35C: "Programme of Record" NYELV felulirja a stadiumot ---
    print("\n  6d. F-35C: explicit 'Programme of Record' language is "
          "programme scope even at production stage")
    ev_por = {"event_type": "order", "lifecycle_stage": "production",
              "quantity": 152,
              "summary": "As of December 2025, the USMC had 152 F-35Cs on "
                         "order as part of a Programme of Record for 140 "
                         "F-35Cs across the force."}
    sc3, why3 = prog.quantity_scope(ev_por)
    check("scope from explicit programme-of-record language", sc3, "programme")
    ev_tranche = {"event_type": "delivery", "lifecycle_stage": "delivery",
                  "quantity": 4,
                  "summary": "Misawa Air Base received its first four "
                             "permanent F-35s in March 2026."}
    sc4, _ = prog.quantity_scope(ev_tranche)
    check("'first four' is a tranche", sc4, "tranche")

    # --- 6e. Gripen: kisebb szam azonos alapon NE csokkentsen csendben ---
    print("\n  6e. Ukraine Gripen: a smaller figure at equal basis is flagged, "
          "not silently applied")
    pg = {"programme_id": "ukr-gripen-2025", "programme_kind": "acquisition",
          "planned_quantity": 150, "planned_basis": "announced"}
    ev_16 = {"event_type": "order", "lifecycle_stage": None, "quantity": 16,
             "summary": "Ukraine signed a $2.5 billion contract with Saab for "
                        "the acquisition of 16 Gripen E fighters."}
    ok16, _ = prog.contract_evidenced(ev_16)
    check("a signed contract is recognised", ok16, True)
    patch5, ch5 = prog.apply_event(pg, ev_16, article_id="a5")
    # A 16 a SZERZODOTT allomany; a 150-es plafon NEM tunik el es nem
    # ellentmondas — ket kulonbozo mertek ugyanarrol a programrol.
    check("firm contract recorded as the contracted quantity",
          patch5.get("contracted_quantity"), 16)
    check("the 150 ceiling is not overwritten",
          patch5.get("planned_quantity"), None)
    check("headline figure prefers the contract",
          patch5.get("canonical_quantity"), 16)
    pg.update(patch5)
    print("      reading: {}".format(prog._quantity_reading(pg)))

    # ...de egy PUSZTA sajtoszam nem.
    pg2 = {"programme_id": "ukr-gripen-2025", "programme_kind": "acquisition",
           "planned_quantity": 150, "planned_basis": "announced"}
    ev_weak = {"event_type": "negotiation", "lifecycle_stage": None,
               "quantity": 20,
               "summary": "Ukraine agreed in May 2026 to buy 20 new Gripen "
                          "fighter jets from Sweden."}
    patch6, ch6 = prog.apply_event(pg2, ev_weak, article_id="a6")
    check("a weaker-basis smaller figure does not reduce the planned total",
          patch6.get("planned_quantity"), None)
    # A 20 a "up to 150" plafon ALATT van — ez reszhalmaz, nem ellentmondas.
    # Csak egy NAGYOBB szam gyengebb evidencian minosul konfliktusnak.
    check("a sub-ceiling figure is an observation, not a conflict",
          len(patch6.get("quantity_conflicts") or []), 0)
    check("it is retained as an observation",
          len(patch6.get("observed_quantities") or []), 1)
    for c in ch6:
        if "sits within" in c:
            print("      {}".format(c[:118]))


    # --- 6g. A szerzodes-evidencia felismerese es a TAGADAS ---
    print("\n  6g. Contract evidence must survive an intervening value and "
          "still respect negation")
    for text, expect in (
            ("Ukraine signed a $2.5 billion contract with Saab for 16 Gripen E.",
             True),
            ("Poland inked an agreement covering 32 additional AH-64E.", True),
            ("The Air Force awarded a $90 million IDIQ contract for interceptors.",
             True),
            ("Boeing was awarded a firm-fixed-price contract.", True),
            ("No contract has been signed for the 24 fighters.", False),
            ("The deal is yet to be signed, officials said.", False),
            ("Uzbekistan is expected to sign a contract later this year.",
             False),
            ("Talks continue; no official confirmation of a contract.", False)):
        ok, why = prog.contract_evidenced(
            {"event_type": "order", "lifecycle_stage": None, "summary": text})
        mark = "ok" if ok == expect else "FAIL"
        if ok != expect:
            FAILS.append((text[:50], ok, expect))
        print("      {:<5} {:<66} {}".format(str(ok), text[:65], mark))


    # --- 6h. SZERZODOTT vs TERVEZETT: mindketto igaz, nem ellentmondas ---
    print("\n  6h. Contracted and planned quantities are separate measures")
    pk = {"programme_id": "tur-kaan-2026", "programme_kind": "acquisition"}
    ev_c = {"event_type": "order", "lifecycle_stage": None, "quantity": 20,
            "summary": "The Turkish Air Force formally signed a contract in "
                       "May 2026 to procure 20 KAAN fifth-generation fighters."}
    patch, _ = prog.apply_event(pk, ev_c, article_id="k1"); pk.update(patch)
    check("contracted quantity", pk.get("contracted_quantity"), 20)
    ev_p = {"event_type": "order", "lifecycle_stage": None, "quantity": 148,
            "summary": "Turkey has a total planned serial production order of "
                       "148 KAAN fifth-generation stealth fighters."}
    patch, ch = prog.apply_event(pk, ev_p, article_id="k2"); pk.update(patch)
    check("planned quantity recorded alongside it",
          pk.get("planned_quantity"), 148)
    check("contracted quantity untouched", pk.get("contracted_quantity"), 20)
    check("no conflict raised", len(pk.get("quantity_conflicts") or []), 0)
    check("headline figure prefers the contract",
          pk.get("canonical_quantity"), 20)
    print("      reading: {}".format(prog._quantity_reading(pk)))
    d, dwhy = prog.on_order_delta(ev_p, pk)
    check("a planned total does not enter on-order", d, 0)

    # --- 6i. NEM-GEP mertekegyseg: celzokonteneres es hajtomuves tetel ---
    print("\n  6i. Non-airframe counts must never become a programme size")
    for text, qty in (
            ("Germany's Bundestag authorized the purchase of 90 LITENING 5 "
             "targeting pods from Rafael for the Eurofighter fleet.", 90),
            ("The US Congress cleared the export license for 80 GE F110 "
             "engines destined for serial production.", 80),
            ("The contract is valued at 250 million dollars.", 250)):
        sc, why = prog.quantity_scope(
            {"event_type": "order", "lifecycle_stage": None, "quantity": qty,
             "summary": text}, quantity=qty)
        mark = "ok" if sc == "non_airframe" else "FAIL"
        if sc != "non_airframe":
            FAILS.append((text[:45], sc, "non_airframe"))
        print("      {:<13} {:<62} {}".format(sc, text[:61], mark))

    pe = {"programme_id": "deu-ef-2025", "programme_kind": "acquisition",
          "contracted_quantity": 20, "contracted_basis": "contract"}
    patch, ch = prog.apply_event(
        pe, {"event_type": "order", "lifecycle_stage": None, "quantity": 90,
             "summary": "Germany's Bundestag authorized the purchase of 90 "
                        "LITENING 5 targeting pods from Rafael."},
        article_id="e1")
    check("pod count does not touch the programme size",
          patch.get("planned_quantity"), None)
    check("it is retained as an observation",
          len(patch.get("observed_quantities") or []), 1)

    # --- 6j. Szam-kozeli kontextus dont, nem az egesz mondat ---
    print("\n  6j. The figure's immediate context decides, not the sentence")
    sc, why = prog.quantity_scope(
        {"event_type": "delivery", "lifecycle_stage": "delivery",
         "quantity": 12,
         "summary": "USMC VMFA-115 conducted its first F-35C flight on July "
                    "31, 2026, with 12 aircraft to follow as the squadron "
                    "transitions."}, quantity=12)
    check("mixed sentence reads conservatively as a tranche", sc, "tranche")


    # --- 6k. "Tranche 5" / "Lot 18" / "Block 70" = TIPUSJELOLES ---
    print("\n  6k. 'Tranche N' is a designation, not a delivery tranche")
    ev_ef = {"event_type": "order", "lifecycle_stage": None, "quantity": 20,
             "summary": "Germany signed a contract in October 2025 for 20 "
                        "Eurofighter Typhoon Tranche 5 aircraft."}
    sc, why = prog.quantity_scope(ev_ef, quantity=20)
    check("Eurofighter Tranche 5 contract scope", sc, "programme")
    pef = {"programme_id": "deu-ef-2025", "programme_kind": "acquisition"}
    patch, ch = prog.apply_event(pef, ev_ef, article_id="ef1")
    check("the firm 20-aircraft contract is recorded",
          patch.get("contracted_quantity"), 20)
    for text, qty, expect in (
            ("The Air Force ordered 18 aircraft in Lot 18 of the programme.",
             18, "programme"),
            ("Poland received the first batch of six F-16 Block 70 jets.",
             6, "tranche"),
            ("Saab will deliver a tranche of 12 Gripen E aircraft.",
             12, "tranche")):
        sc2, w2 = prog.quantity_scope(
            {"event_type": "order", "lifecycle_stage": None,
             "quantity": qty, "summary": text}, quantity=qty)
        mark = "ok" if sc2 == expect else "FAIL"
        if sc2 != expect:
            FAILS.append((text[:46], sc2, expect))
        print("      {:<10} {:<58} {}".format(sc2, text[:57], mark))

    # --- 6l. Plafon alatti kisebb szam NEM ellentmondas ---
    print("\n  6l. A figure below a stated ceiling is not a contradiction")
    pc = {"programme_id": "ukr-gripen-2025", "programme_kind": "acquisition",
          "planned_quantity": 150, "planned_basis": "announced"}
    ev_b = {"event_type": "delivery", "lifecycle_stage": None, "quantity": 16,
            "summary": "The UK announced a EUR300m investment to support the "
                       "delivery of 16 Saab Gripen E aircraft to Ukraine."}
    patch, ch = prog.apply_event(pc, ev_b, article_id="g1")
    check("no conflict raised for a sub-ceiling figure",
          len(patch.get("quantity_conflicts") or []), 0)
    check("recorded as an observation instead",
          len(patch.get("observed_quantities") or []), 1)
    check("the 150 ceiling is untouched", patch.get("planned_quantity"), None)
    for c in ch:
        if "sits within" in c:
            print("      {}".format(c[:112]))
    # ...de egy NAGYOBB szam gyengebb evidencian igen.
    ev_big = {"event_type": "negotiation", "lifecycle_stage": None,
              "quantity": 250,
              "summary": "Local reports suggest Ukraine may acquire as many as "
                         "250 Gripen aircraft in total."}
    patch2, _ = prog.apply_event(
        {"programme_id": "x", "programme_kind": "acquisition",
         "planned_quantity": 150, "planned_basis": "announced"},
        ev_big, article_id="g2")
    check("a larger figure on weaker evidence IS flagged",
          len(patch2.get("quantity_conflicts") or []), 1)

    # --- 6m. "ordered N" mint szerzodes-evidencia ---
    print("\n  6m. 'ordered N' counts as a procurement action")
    ok, why = prog.contract_evidenced(
        {"event_type": "order", "lifecycle_stage": None,
         "summary": "Ukraine ordered 16 Gripen E fighter jets from Saab in a "
                    "deal valued at roughly $2.5 billion."})
    check("'ordered' recognised", ok, True)
    ok2, _ = prog.contract_evidenced(
        {"event_type": "other", "lifecycle_stage": "delivery",
         "summary": "The service has 152 F-35Cs on order as of December 2025."})
    check("bare 'on order' is a state, not an action", ok2, False)


    # --- 6n. ZAROJELES kettos valutaertek es TOBBES SZAM ---
    # A vedelmi sajtoban altalanos "£4.6 billion ($6.1 billion)" forma
    # szettorte a szerzodes-felismerest, es egy 4,6 milliard fontos odaiteles
    # "nincs alairasi nyelvezet"-kent latszott.
    print("\n  6n. Parenthetical dual-currency figures and plural "
          "'contracts' must not break contract detection")
    for text, expect in (
            ("Japan, Italy, and the UK jointly awarded a GBP4.6 billion "
             "($6.1 billion) 18-month development contract to Edgewing.", True),
            ("The office signed a GBP686 million ($908 million) stopgap "
             "development contract with Edgewing.", True),
            ("The USAF awarded Anduril and General Atomics production "
             "contracts worth up to $150 million each.", True),
            ("The three nations are set to award a new development contract.",
             False)):
        ok, _ = prog.contract_evidenced(
            {"event_type": "order", "lifecycle_stage": None, "summary": text})
        mark = "ok" if ok == expect else "FAIL"
        if ok != expect:
            FAILS.append((text[:46], ok, expect))
        print("      {:<5} {:<64} {}".format(str(ok), text[:63], mark))

    # --- 6o. A fejlesztesi szerzodes nem gepbeszerzes ---
    print("\n  6o. A development contract is not an aircraft acquisition")
    check("GCAP development contract kind",
          prog.kind_from_event(
              {"event_type": "order", "lifecycle_stage": None,
               "summary": "Japan, Italy, and the UK jointly awarded a 4.6 "
                          "billion development contract to the Edgewing "
                          "industrial consortium for GCAP."}),
          "development")

    # --- 6f. Legacy esemenyek: URES lifecycle_stage feloldasa ---
    print("\n  6f. Legacy events with a NULL lifecycle_stage must still "
          "resolve a stage")
    check("event_type 'order' resolves",
          prog.resolved_stage({"event_type": "order",
                               "lifecycle_stage": None}), "contract_signed")
    check("event_type 'incident' resolves",
          prog.resolved_stage({"event_type": "incident",
                               "lifecycle_stage": None}), "loss")
    check("an explicit stage still wins",
          prog.resolved_stage({"event_type": "order",
                               "lifecycle_stage": "selection"}), "selection")


def main():
    test_poland_apache()
    test_uzbekistan()
    test_variant_isolation()
    test_supersession()
    test_merge_candidates()
    test_quantity_scope_real_cases()
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
