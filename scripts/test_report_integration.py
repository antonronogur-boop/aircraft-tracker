# -*- coding: utf-8 -*-
"""Vegponti teszt: a W33/W34 forgatokonyv ujrajatszasa a teljes lancon.

Adatbazis nelkul fut. Azt ellenorzi, hogy a KET JELENTESBEN AZONOSITOTT
HIBAK a szarmaztatott nezetekben (ORBAT, timeline, statisztika) sem tudnak
visszaterni — nem csak a segedfuggvenyek szintjen.

Futtatas:  python scripts/test_report_integration.py
"""
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ac_intel as I  # noqa: E402
import ac_programmes as P  # noqa: E402

NOW = datetime(2026, 8, 17)
FAILS = []


def check(label, got, expected):
    ok = got == expected
    print("  {:<64} {!s:<18} {}".format(
        label, got, "ok" if ok else "FAIL (expected {!r})".format(expected)))
    if not ok:
        FAILS.append((label, got, expected))


def section(t):
    print("\n" + t)
    print("-" * 86)


# --------------------------------------------------------------------------
# Kozos vilag: katalogus, orszagok, flottak, programok
# --------------------------------------------------------------------------
TYPES = {
    "ah-64": {"type_id": "ah-64", "name": "AH-64 Apache",
              "category": "helicopter"},
    "uh-60": {"type_id": "uh-60", "name": "UH-60 Black Hawk",
              "category": "helicopter"},
    "a-10":  {"type_id": "a-10", "name": "A-10 Thunderbolt II",
              "category": "attack"},
    "j-10":  {"type_id": "j-10", "name": "J-10", "category": "fighter"},
    "vc-25": {"type_id": "vc-25", "name": "VC-25", "category": "transport"},
}
COUNTRIES = {
    "pol": {"country_id": "pol", "name": "Poland", "region": "Central Europe"},
    "usa": {"country_id": "usa", "name": "United States", "region": "N America"},
    "uzb": {"country_id": "uzb", "name": "Uzbekistan", "region": "Central Asia"},
    "rus": {"country_id": "rus", "name": "Russia", "region": "Eurasia"},
}
FLEETS = [
    # Lengyel Apache: a katalogus 190-et mutat (a hibas, felhalmozott ertek).
    {"country_id": "pol", "type_id": "ah-64", "fleet_status": "on_order",
     "quantity": 190, "variant": None, "service": None,
     "baseline_scope": "national_family"},
    # US UH-60 csalad: 2000 aktiv — csalad-szintu baseline.
    {"country_id": "usa", "type_id": "uh-60", "fleet_status": "active",
     "quantity": 2000, "variant": None, "service": None,
     "baseline_scope": "national_family"},
]
PROGRAMMES = {
    "pol-ah64e-2024": {
        "programme_id": "pol-ah64e-2024", "country_id": "pol",
        "type_id": "ah-64", "variant": "AH-64E", "service": None,
        "programme_kind": "acquisition", "title": "Poland AH-64E acquisition",
        "canonical_quantity": 96, "quantity_basis": "contract",
        "lifecycle_stage": "contract_signed", "contract_date": "2024-08-13",
        "review_status": "active", "evidence_count": 4,
    },
}


# ==========================================================================
def test_orbat_poland():
    section("A. ORBAT — Poland AH-64E must not read as 190 + 96")
    ev = {
        "event_id": 101, "country_id": "pol", "type_id": "ah-64",
        "variant_raw": "AH-64E", "lifecycle_stage": "contract_signed",
        "quantity": 96, "quantity_claimed": 96, "programme_id": "pol-ah64e-2024",
        "summary": ("Boeing signed an offset agreement establishing an MRO "
                    "centre supporting Poland's 96 AH-64E helicopters."),
        "event_date": "2026-08-11",
    }
    ev["on_order_delta"] = P.on_order_delta(ev, PROGRAMMES["pol-ah64e-2024"],
                                           ev["summary"])[0]
    rows = I.orbat_delta([ev], FLEETS, TYPES, COUNTRIES,
                         programmes_by_id=PROGRAMMES)
    e = rows[0]["entries"][0]
    check("on_order_delta from a restatement", e["on_order_delta"], 0)
    check("baseline_moved", e["baseline_moved"], False)
    check("programme of record shown", e["canonical_quantity"], 96)
    print("    period reading: {}".format(e["period_reading"]))
    # A varians-szintu esemenynek nincs varians-baseline -> a szam VISSZATARTVA,
    # nem a 190-es csalad-ertek jelenik meg.
    check("family figure substituted for the variant",
          e["baseline_shown"], False)
    check("scope flagged", e["baseline_scope_match"],
          "variant_without_baseline")
    print("    baseline note : {}".format((e["baseline_note"] or "")[:100]))


def test_orbat_hh60w():
    section("B. ORBAT — a 26-aircraft HH-60W event must not show UH-60 "
            "Active 2000")
    ev = {
        "event_id": 201, "country_id": "usa", "type_id": "uh-60",
        "variant_raw": "HH-60W Jolly Green II", "service": "USAF",
        "lifecycle_stage": "contract_signed", "quantity": 26,
        "quantity_claimed": 26, "on_order_delta": 0,
        "summary": "The USAF awarded a contract for 26 HH-60W helicopters.",
        "expected_ioc_year": 2029, "foc_year": 2030,
    }
    rows = I.orbat_delta([ev], FLEETS, TYPES, COUNTRIES,
                         programmes_by_id=PROGRAMMES)
    e = rows[0]["entries"][0]
    check("active baseline shown", e["active"], None)
    check("scope mismatch detected", e["baseline_scope_match"],
          "variant_without_baseline")
    check("reported variant preserved", e["variant_reported"],
          "HH-60W Jolly Green II")
    check("canonical family name used for the row", e["type"],
          "UH-60 Black Hawk")
    print("    baseline note : {}".format((e["baseline_note"] or "")[:110]))
    # A QA-nak jelezni kell a hatokor-eltérest.
    issues = I.run_self_checks([], None, NOW, NOW, orbat=rows)
    hits = [c for c in issues
            if c["check"].startswith("variant-level action has no")]
    check("self-check raises the scope mismatch", len(hits), 1)


def test_orbat_uzbekistan():
    section("C. ORBAT — Uzbekistan must not show 'Contract signed x24'")
    ev = {
        "event_id": 301, "country_id": "uzb", "type_id": "j-10",
        "variant_raw": "J-10C", "lifecycle_stage": "contract_signed",
        "quantity": 24, "quantity_claimed": 24,
        "summary": ("Reports indicate Uzbekistan is negotiating for 24 J-10C "
                    "fighters; there has been no official confirmation and "
                    "contract details are unconfirmed."),
    }
    ev["on_order_delta"] = P.on_order_delta(ev, None, ev["summary"])[0]
    rows = I.orbat_delta([ev], FLEETS, TYPES, COUNTRIES,
                         programmes_by_id=PROGRAMMES)
    e = rows[0]["entries"][0]
    check("ORBAT stage", e["this_period_stage"], "selection")
    check("quantity still visible as a claim",
          e["this_period_quantity_claimed"], 24)
    check("baseline moved", e["baseline_moved"], False)
    print("    downgrade note: {}".format(
        (e["this_period_stage_note"] or "")[:110]))
    issues = I.run_self_checks([], None, NOW, NOW, orbat=rows)
    hits = [c for c in issues if c["check"].startswith("ORBAT stage downgraded")]
    check("self-check records the downgrade", len(hits), 1)


def test_stage_propagation():
    section("D. Analyst downgrade propagates to the events (one state, not two)")
    ev = {"event_id": 401, "lifecycle_stage": "contract_signed",
          "quantity": 24, "quantity_claimed": 24, "on_order_delta": 24,
          "summary": "Uzbekistan is negotiating for 24 J-10C; unconfirmed."}
    dev = {"display_label": "UZ J-10C", "event_ids": [401],
           "lifecycle_stage": "selection",
           "auto_adjustment": "lifecycle downgraded to selection"}
    applied = I.propagate_stage_corrections([dev], [ev])
    check("corrections applied", len(applied), 1)
    check("event stage now", ev["lifecycle_stage"], "selection")
    check("original label retained", ev["lifecycle_stage_reported"],
          "contract_signed")
    check("on-order delta reset", ev["on_order_delta"], 0)
    print("    note: {}".format(ev["stage_correction_note"][:120]))


def test_timeline():
    section("E. Timeline — one row per programme + milestone; a delay is not "
            "an arrival")
    devs = [
        # W34: "2028 Poland AH-64E MRO deal (first delivery)" — hibas volt.
        {"display_label": "PL AH-64E MRO", "programme_id": "pol-ah64e-mro-2026",
         "programme_kind": "sustainment_mro", "lifecycle_stage": "contract_signed",
         "capability_domain": "attack_helicopter", "confidence": "moderate",
         "first_delivery_year": 2028,
         "fact": "Boeing signed an offset agreement establishing an MRO centre.",
         "capability_delta": "x", "so_what": "y"},
        # W34: "2029 US VC-25B delay (meaningful capability)" — egy keses.
        {"display_label": "US VC-25B", "programme_kind": "acquisition",
         "lifecycle_stage": "production", "capability_domain": "air_mobility_fixed",
         "confidence": "high", "first_delivery_year": 2028, "ioc_year": 2028,
         "meaningful_capability_year": 2029,
         "fact": "The programme slipped again; first delivery now mid-2028.",
         "capability_delta": "x", "so_what": "y"},
        # Rendes beszerzes: harom kulon milestone -> harom kulon sor.
        {"display_label": "PL AH-64E", "programme_id": "pol-ah64e-2024",
         "programme_kind": "acquisition", "lifecycle_stage": "delivery",
         "capability_domain": "attack_helicopter", "confidence": "moderate",
         "first_delivery_year": 2028, "ioc_year": 2029,
         "meaningful_capability_year": 2031,
         "fact": "Deliveries begin in 2028.", "capability_delta": "x",
         "so_what": "y"},
    ]
    tl = I.capability_timeline(devs, [], TYPES, COUNTRIES,
                              programmes_by_id={
                                  "pol-ah64e-mro-2026": {
                                      "programme_id": "pol-ah64e-mro-2026",
                                      "programme_kind": "sustainment_mro",
                                      "title": "Poland AH-64E MRO centre"},
                                  "pol-ah64e-2024": PROGRAMMES["pol-ah64e-2024"],
                              })
    print("    {:<6} {:<34} {:<32} {}".format("year", "programme", "milestone",
                                              "arrival kind"))
    for t in tl:
        print("    {:<6} {:<34} {:<32} {}".format(
            t["year_label"], (t["programme"] or "")[:33], t["milestone"][:31],
            t["arrival_kind"]))

    mro = [t for t in tl if "MRO" in (t["programme"] or "")]
    check("MRO row count", len(mro), 1)
    check("MRO milestone is not a first delivery",
          mro[0]["milestone_kind"], "mro_standup")
    # A LENYEG: az MRO-sor NEM veszi at a beszerzes 2028-as gepatadasi evet.
    check("MRO row does not borrow the acquisition's delivery year",
          mro[0]["year"], None)
    check("MRO row shows TBD", mro[0]["year_label"], "TBD")
    check("MRO is a support arrival, not an airframe arrival",
          mro[0]["arrival_kind"], "support")
    check("MRO is not an airframe arrival", mro[0]["is_airframe_arrival"], False)

    vc = [t for t in tl if "VC-25B" in (t["programme"] or "")]
    check("VC-25B produces exactly one row (the slip)", len(vc), 1)
    check("VC-25B milestone", vc[0]["milestone_kind"], "schedule_slip")
    check("VC-25B not counted as an arrival", vc[0]["is_arrival"], False)

    apache = [t for t in tl if t["programme"] == "Poland AH-64E acquisition"]
    check("a normal acquisition yields 3 separate milestone rows",
          len(apache), 3)
    check("each row has its own milestone kind",
          len({t["milestone_kind"] for t in apache}), 3)


def test_horizons():
    section("F. Effect horizons — VC-25B is not '>3 years'")
    d = {"lifecycle_stage": "production", "first_delivery_year": 2028,
         "ioc_year": 2028, "meaningful_capability_year": 2029,
         "effect_timing": ">3 years",
         "effect_timing_basis": "first delivery mid-2028, IOC 2028, usable 2029",
         "fact": "Delivery is expected mid-2028."}
    I._enforce_effect_timing(d, NOW)
    check("earliest operational effect", d["effect_timing"], "1-3 years")
    check("meaningful scale", d["full_capability_timing"], ">3 years")
    check("months to earliest effect", d["effect_timing_months"], 22)

    h = {"lifecycle_stage": "delivery", "first_delivery_year": 2027,
         "ioc_year": 2029, "foc_year": 2030, "effect_timing": ">3 years",
         "effect_timing_basis": "IOC early 2029, FOC 2030"}
    I._enforce_effect_timing(h, NOW)
    check("HH-60W earliest effect", h["effect_timing"], "1-3 years")
    check("HH-60W meaningful scale", h["full_capability_timing"], ">3 years")


def test_wow_and_confirmation():
    section("G. Statistics — WoW basis and the A-100LL confirmation framing")
    # A W34 "22 (+0 WoW)"-t irt, mert az elozo hetet ujraszamolta.
    published_prev, this_week = 18, 22
    wow = this_week - published_prev
    check("WoW against the published previous figure", wow, 4)

    # Az A-100LL: 2025-os veszteseg, 2026-W34-es vizualis megerosites.
    ev = {"event_id": 501, "country_id": "rus", "type_id": None,
          "unresolved_type_name": "Beriev A-100LL",
          "event_date": "2025-06-01", "new_evidence_at": "2026-08-15",
          "lifecycle_stage": "loss",
          "summary": "Oryx visually confirmed the loss of the A-100LL testbed."}
    occurred = I.parse_day(ev["event_date"])
    fresh = I.parse_day(ev["new_evidence_at"])
    wk_start = datetime(2026, 8, 10)
    is_confirmation = occurred < wk_start <= fresh
    check("classified as a confirmation rather than a new event",
          is_confirmation, True)
    check("occurrence year preserved", occurred.year, 2025)

    dev = {"display_label": "RU A-100LL loss", "event_ids": [501],
           "lifecycle_stage": "loss", "confidence": "high",
           "fact": "Oryx visually confirmed the 2025 loss.",
           "capability_delta": "x", "so_what": "y", "significance": 3}
    ev["evidence_kind"] = "new_confirmation"
    devs, _ = [dev], None
    # A lineage-korlat is hat: egyetlen forras -> nem lehet high.
    lin, rep, note = I.count_lineages([ev])
    capped, why = I.cap_confidence_by_lineage("high", lin)
    check("single-chain confidence capped", capped, "moderate")
    print("    {}".format(why))


def test_briefing():
    section("H. Briefing view — built only from QA-passed content")
    devs = [
        {"display_label": "PL AH-64E", "title": "Poland AH-64E deliveries",
         "capability_delta": "First airframes arrive 2028.",
         "confidence": "moderate", "effect_timing": "1-3 years",
         "full_capability_timing": ">3 years", "significance": 5,
         "baseline_moved": False, "event_ids": [101],
         "capability_domain": "attack_helicopter", "ioc_year": 2029,
         "fact": "f", "so_what": "s", "independent_lineages": 1,
         "lineage_basis": "one chain"},
        {"display_label": "US VC-25B", "title": "VC-25B slip",
         "capability_delta": "Programme slipped.", "confidence": "high",
         "effect_timing": ">3 years", "significance": 3,
         "baseline_moved": False, "event_ids": [102],
         "capability_domain": "air_mobility_fixed", "fact": "f", "so_what": "s"},
    ]
    j = {"bottom_line": "A quiet period.",
         "key_judgements": [{"id": "KJ-01", "judgement": "j",
                             "supporting_event_ids": [101]}],
         "judgements_requiring_review": [{"id": "KJ-09"}],
         "priority_watch": [{"issue": "Apache MRO certification",
                             "impact_if_confirmed": "high",
                             "next_observable": "certification notice"}],
         "intelligence_gaps": ["No IOC date published."]}
    stats = {"events_this_week": 22, "wow": 4,
             "wow_basis": "published figure from 2026-W33",
             "collection_health": {"wow_comparable": True}}
    diff = {"programmes": [{"programme": "PL AH-64E", "change": "advanced",
                            "moved": True}],
            "watch": [{"issue": "old watch", "state": "dropped"}]}
    b = I.build_briefing("2026-W34", j, devs, [], diff, stats)
    check("slide count", len(b["slides"]), 4)
    s1 = b["slides"][0]["body"]
    check("headline changes", len(s1["headline_changes"]), 2)
    check("withheld judgements surfaced", s1["withheld"], 1)
    check("WoW carried through honestly", s1["volume"]["wow"], 4)
    s2 = b["slides"][1]["body"]
    cols = {c["key"]: len(c["items"]) for c in s2["columns"]}
    check("horizon columns populated", cols, {"now": 0, "near": 1, "far": 1})
    s3 = b["slides"][2]["body"]
    check("deep dive picks the most significant item", s3["title"],
          "Poland AH-64E deliveries")
    check("'what we don't know' is populated",
          len(s3["what_we_dont_know"]) >= 2, True)
    s4 = b["slides"][3]["body"]
    check("watch items", len(s4["watch"]), 1)
    check("previous watch status carried", len(s4["previous_watch"]), 1)


def main():
    test_orbat_poland()
    test_orbat_hh60w()
    test_orbat_uzbekistan()
    test_stage_propagation()
    test_timeline()
    test_horizons()
    test_wow_and_confirmation()
    test_briefing()
    print("\n" + "=" * 86)
    if FAILS:
        print("FAILURES: {}".format(len(FAILS)))
        for f in FAILS:
            print("  {}".format(f))
        return 1
    print("All integration checks passed — the W33/W34 defects cannot recur in "
          "the derived views.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
