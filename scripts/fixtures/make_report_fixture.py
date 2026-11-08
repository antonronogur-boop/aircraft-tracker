# -*- coding: utf-8 -*-
"""SYNTHETIC test fixture for the Command Brief (not real reporting).

Builds an air_power_v3 report payload with the same shape the weekly
generator writes, covering every brief path: CEE neighbours, non-NATO
priority, Allied posture in CEE (US actor), Hungary itself, Middle East,
Africa, wider NATO, Indo-Pacific, a non-material item, a background item, a
withheld judgement, since_last_week rows and a previous-week watch list.

Usage: python scripts/fixtures/make_report_fixture.py  -> report_fixture.json
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def dev(i, title, label, dom, stage, fact, delta, so_what, sig, conf, timing,
        countries=None, events=None, prog=None, ind=None, lin=2,
        novelty="new"):
    d = {
        "event_ids": events or [100 + i],
        "title": title, "display_label": label, "capability_domain": dom,
        "lifecycle_stage": stage, "fact": fact, "capability_delta": delta,
        "so_what": so_what, "significance": sig, "confidence": conf,
        "effect_timing": timing, "novelty": novelty,
        "independent_lineages": lin, "reports_count": lin + 1,
        "indicators_to_watch": ind or ["Next official statement on the "
                                       "programme schedule."],
        "programme_id": prog,
    }
    if countries is not None:
        d["country_ids"] = countries
    return d


DEVS = [
    dev(1, "Serbia receives first two Rafale fighters", "RS Rafale delivery",
        "fighter_strike", "delivery",
        "The Serbian Ministry of Defence stated that the first two Rafale "
        "aircraft landed at Batajnica. Two further aircraft are expected "
        "before year end, according to the ministry.",
        "Introduces a Western 4.5-generation fighter into the Serbian Air "
        "Force alongside its MiG-29 fleet; meaningful scale depends on crew "
        "and weapons delivery.",
        "Changes the combat air balance on Hungary's southern border over "
        "the next 1-3 years.", 4, "moderate", "<12 months",
        countries=["srb"], prog="srb-rafale-2024",
        ind=["Delivery of the next two aircraft before year end."]),
    dev(2, "Romania signs Letter of Offer and Acceptance for 32 F-35A",
        "RO F-35A LOA", "fighter_strike", "contract_signed",
        "The Romanian Ministry of National Defence stated it signed the LOA "
        "for 32 F-35A. First deliveries are planned for 2032, per the "
        "ministry.",
        "Commits Romania to a fifth-generation fighter fleet; no operational "
        "effect before the 2030s.",
        "Establishes a second F-35 operator on NATO's south-eastern flank "
        "next to Hungary.", 4, "high", ">3 years", countries=["rou"],
        prog="rou-f35-2024", ind=["Romanian pilot training start in the US."]),
    dev(3, "Ukraine loses one F-16AM in combat", "UA F-16 loss",
        "fighter_strike", "loss",
        "The Ukrainian Air Force stated that one F-16AM was lost during a "
        "combat mission; the pilot was killed. The cause was not stated.",
        "Reduces Ukraine's small F-16 fleet by one airframe; mechanism "
        "unknown.",
        "Attrition of a scarce Western fighter fleet next to Hungary's "
        "north-eastern border.", 3, "moderate", "immediate",
        events=[103, 113], prog="ukr-f16-2023",
        ind=["Ukrainian Air Force statement on the cause of the loss."]),
    dev(4, "USAF rotates F-35A squadron to Łask, Poland, for eastern flank "
        "air policing", "US F-35A Łask rotation", "fighter_strike", "other",
        "US Air Forces in Europe stated that a squadron of F-35A deployed to "
        "Łask Air Base, Poland, to support NATO air policing on the eastern "
        "flank.",
        "Temporarily adds fifth-generation fighters to Allied QRA capacity "
        "in Poland.",
        "Strengthens Allied air posture on the eastern flank during the "
        "rotation.", 3, "high", "immediate", countries=["usa"],
        ind=["Duration of the rotation and any follow-on deployment."]),
    dev(5, "Israel orders 25 additional F-15IA", "IL F-15IA +25",
        "fighter_strike", "contract_signed",
        "The Israeli Ministry of Defense stated it signed for 25 additional "
        "F-15IA aircraft. Deliveries begin in 2031, according to the "
        "ministry.",
        "Expands Israel's heavy strike fleet in the 2030s.",
        "Sustains Israeli long-range strike capacity; limited direct effect "
        "on Europe.", 4, "high", ">3 years", countries=["isr"],
        prog="isr-f15ia-2024"),
    dev(6, "Algeria reported to receive first Su-57E", "DZ Su-57E",
        "fighter_strike", "delivery",
        "A specialist outlet reported, citing imagery, that Algeria received "
        "its first Su-57E. Neither government confirmed.",
        "Would make Algeria the first export operator of the Su-57, if "
        "confirmed.",
        "First export of Russia's fifth-generation fighter; indicator of "
        "Russian production capacity.", 3, "low", "<12 months",
        countries=["dza"], lin=1, events=[106, 116],
        ind=["Official confirmation or imagery of Su-57E at an Algerian "
             "base."]),
    dev(7, "Japan declares IOC for first F-35B squadron at Nyutabaru",
        "JP F-35B IOC", "fighter_strike", "ioc",
        "The Japan Air Self-Defense Force stated that its first F-35B "
        "squadron reached initial operational capability at Nyutabaru.",
        "Adds short-take-off fifth-generation capability to Japan's "
        "south-western defence.",
        "Strengthens Allied air posture in the East China Sea.", 3, "high",
        "immediate", countries=["jpn"], prog="jpn-f35b-2019"),
    dev(8, "China displays J-35A in PLAAF service markings", "CN J-35A",
        "fighter_strike", "production",
        "State media showed J-35A aircraft in PLAAF markings at an air "
        "show. Unit and quantity were not stated.",
        "Indicates the J-35A is moving from test into service; scale "
        "unknown.",
        "A second Chinese fifth-generation type would broaden PLAAF "
        "modernisation.", 4, "moderate", "<12 months", countries=["chn"],
        ind=["Imagery of J-35A at an operational PLAAF base."]),
    dev(9, "Germany orders 15 additional F-35A", "DE F-35A +15",
        "fighter_strike", "contract_signed",
        "The German Ministry of Defence stated that parliament approved and "
        "it signed for 15 additional F-35A. Deliveries begin in 2029, per "
        "the ministry.",
        "Raises Germany's F-35A programme of record from 35 to 50.",
        "Grows the European F-35 user base the Alliance's nuclear sharing "
        "and strike planning depends on.", 4, "high", ">3 years",
        countries=["deu"], prog="deu-f35-2022"),
    dev(10, "Czech Republic opens Gripen lease extension talks",
        "CZ Gripen extension", "fighter_strike", "requirement",
        "The Czech Ministry of Defence said talks on extending the Gripen "
        "lease have begun.",
        "No capability change at this stage.",
        "Routine sustainment of an existing fleet.", 2, "moderate",
        "unknown", countries=["cze"]),
    dev(11, "Hungary accepts first KC-390 transport", "HU KC-390",
        "air_mobility_fixed", "delivery",
        "The Hungarian Defence Forces stated that the first KC-390 was "
        "accepted at Kecskemét.",
        "Begins replacing Hungary's tactical airlift capacity; IOC depends "
        "on crew training.",
        "Restores national tactical airlift and air-to-air refuelling "
        "options for MH.", 3, "high", "<12 months", countries=["hun"],
        prog="hun-c390-2020"),
]

BACKGROUND = [
    dev(12, "Slovakia completes F-16 simulator training block",
        "SK F-16 sim", "fighter_strike", "other",
        "The Slovak MoD reported completion of a simulator training block.",
        "No capability change at this stage.", "Routine.", 2, "high",
        "unknown", countries=["svk"]),
]

KJS = [
    {"id": "KJ-01", "domain": "fighter_strike",
     "judgement": "Israel's additional F-15IA order indicates sustained "
                  "investment in long-range strike, with no operational "
                  "effect before 2031.",
     "confidence": "high", "basis": "Ministry statement; two lineages.",
     "assessment": "Expands Israeli heavy strike capacity in the 2030s; "
                   "near-term operational effect is zero.",
     "effect_timing": ">3 years",
     "alternative_explanation": "The order may replace attrition rather "
                                "than grow the fleet.",
     "indicators": ["US production slot allocation for the additional "
                    "F-15IA."], "supporting_event_ids": [105]},
    {"id": "KJ-02", "domain": "fighter_strike",
     "judgement": "Serbia's first Rafale deliveries indicate the start of a "
                  "Western fighter capability on Hungary's southern border, "
                  "with meaningful scale 1-3 years away.",
     "confidence": "moderate", "basis": "MoD statement; deliveries "
                                        "observed.",
     "assessment": "Two aircraft do not yet change Serbia's operational "
                   "capability; crews, weapons and sustainment determine "
                   "the pace.",
     "effect_timing": "<12 months", "alternative_explanation": None,
     "indicators": ["Delivery of the next two aircraft before year end."],
     "supporting_event_ids": [101]},
    {"id": "KJ-03", "domain": "fighter_strike",
     "judgement": "The J-35A in PLAAF markings suggests a second Chinese "
                  "fifth-generation type is entering service.",
     "confidence": "moderate", "basis": "State media imagery; single "
                                        "display.",
     "assessment": "Service entry broadens PLAAF modernisation; scale and "
                   "unit are unknown.",
     "effect_timing": "<12 months",
     "alternative_explanation": "The display may show test-unit aircraft "
                                "in service paint for publicity.",
     "indicators": ["Imagery at an operational base."],
     "supporting_event_ids": [108]},
    {"id": "KJ-04", "domain": "fighter_strike",
     "judgement": "Germany's additional F-35A order grows the European F-35 "
                  "user base, with first deliveries in 2029.",
     "confidence": "high", "basis": "Ministry and parliament statements.",
     "assessment": "No near-term effect; supports Alliance strike and "
                   "nuclear-sharing planning in the 2030s.",
     "effect_timing": ">3 years", "alternative_explanation": None,
     "indicators": ["Delivery schedule confirmation."],
     "supporting_event_ids": [109]},
]

WITHHELD = [
    {"id": "KJ-05", "domain": "fighter_strike",
     "judgement": "Russia demonstrated effective counter-air capability "
                  "against Ukrainian F-16 operations.",
     "confidence": "low", "supporting_event_ids": [103, 113],
     "withheld_reason": "mechanism claim without evidence"},
]

# Forrasok (SZINTETIKUS URL-ek). Benne: magyar ekezetes eredeti cim, egy
# allami ellenorzes alatti forras (egy lineage), es egy cikk, amely ket
# fejlemenyt is alatamaszt.
_ART = {
    101: ("Serbia receives first Rafale jets at Batajnica",
          "https://www.defensenews.com/fixture/serbia-rafale"),
    102: ("Romania signs F-35 Letter of Offer and Acceptance",
          "https://breakingdefense.com/fixture/romania-f35"),
    103: ("Ukraine loses F-16AM in combat mission",
          "https://mil.in.ua/en/fixture/f16-loss"),
    113: ("Ukrainian Air Force confirms F-16 loss",
          "https://www.defensenews.com/fixture/ukraine-f16"),
    104: ("USAFE F-35A squadron deploys to Łask",
          "https://www.airandspaceforces.com/fixture/lask"),
    105: ("Israel orders 25 more F-15IA",
          "https://breakingdefense.com/fixture/f15ia"),
    106: ("Алжир получил первые Су-57Э",
          "https://tass.ru/fixture/su57e"),
    116: ("Алжир получил Су-57Э — РИА Новости",
          "https://ria.ru/fixture/su57e"),
    107: ("JASDF F-35B squadron reaches IOC",
          "https://theaviationist.com/fixture/f35b-ioc"),
    108: ("J-35A appears in PLAAF markings",
          "https://theaviationist.com/fixture/j35a"),
    109: ("Germany signs for 15 more F-35A",
          "https://www.defensenews.com/fixture/germany-f35"),
    110: ("Czech Gripen lease talks begin",
          "https://www.airforce-technology.com/fixture/cz-gripen"),
    111: ("Kecskemétre érkezett az első KC-390 — Magyar Honvédség",
          "https://honvedelem.hu/fixture/kc-390-kecskemet"),
    112: ("Slovak F-16 simulator block completed",
          "https://www.airforce-technology.com/fixture/sk-sim"),
}
_COUNTRY = {101: "Serbia", 102: "Romania", 103: "Ukraine", 113: "Ukraine",
            104: "United States", 105: "Israel", 106: "Algeria",
            116: "Algeria",
            107: "Japan", 108: "China", 109: "Germany", 110: "Czechia",
            111: "Hungary", 112: "Slovakia"}
ANNEX = [{"event_id": k, "country": _COUNTRY[k], "article_title": v[0],
          "article_url": v[1], "event_date": "2026-11-0{}".format(4 + k % 6)}
         for k, v in _ART.items()]

PRIORITY_WATCH = [
    {"issue": "Serbian Rafale deliveries 3-4", "why_it_matters": "Pace of "
     "Serbia's fighter transition next to Hungary.",
     "next_observable": "Arrival of aircraft 3 and 4 at Batajnica.",
     "horizon": "weeks", "impact_if_confirmed": "high"},
    {"issue": "Cause of Ukrainian F-16 loss", "why_it_matters": "Indicates "
     "the threat to Western fighters operating near the front.",
     "next_observable": "Ukrainian Air Force statement on the cause.",
     "horizon": "days", "impact_if_confirmed": "medium"},
    {"issue": "J-35A operational basing", "why_it_matters": "Scale of the "
     "second PLAAF fifth-generation type.",
     "next_observable": "Imagery of J-35A at an operational base.",
     "horizon": "months", "impact_if_confirmed": "medium"},
]

GAPS = [
    "Whether Serbia's Rafale contract includes Meteor missiles is not "
    "established in reporting.",
    "The cause of the Ukrainian F-16 loss is not reported.",
]

SINCE = {
    "previous_week": "2026-W45",
    "programmes": [
        {"programme": "RS Rafale delivery", "programme_id": "srb-rafale-2024",
         "previous": "Production · moderate", "current": "Delivery · moderate",
         "change": "lifecycle Production -> Delivery", "moved": True},
        {"programme": "RO F-35A LOA", "programme_id": "rou-f35-2024",
         "previous": "Export approval · high",
         "current": "Contract signed · high",
         "change": "lifecycle Export approval -> Contract signed",
         "moved": True},
        {"programme": "DE F-35A +15", "programme_id": "deu-f35-2022",
         "previous": "not reported", "current": "Contract signed · high",
         "change": "new to the reporting this period", "moved": True},
        {"programme": "PL AH-64E", "programme_id": "pol-ah64e-2024",
         "previous": "Contract signed · high", "current": "not reported",
         "change": "no new evidence this period", "moved": False},
    ],
    "watch": [{"issue": "Serbian Rafale deliveries 3-4", "state": "unchanged",
               "state_label": "unchanged — no new evidence this period",
               "next_observable": "Arrival of aircraft 3 and 4."}],
    "note": "Programme-level comparison against the previous published "
            "report.",
}


def build():
    return {
        "schema": "air_power_v3",
        "week_label": "2026-W46",
        "_fixture": "SYNTHETIC TEST DATA — not real reporting",
        "report_meta": {
            "week_label": "2026-W46", "period_start": "2026-11-04",
            "period_end": "2026-11-10", "timezone": "Europe/Budapest",
            "window_label": "2026-11-04 00:00:00 -> 2026-11-10 23:59:59 "
                            "(Europe/Budapest)",
            "generated_utc": "2026-11-11 05:20 UTC",
            "status": "auto-generated, QA clean", "version": "v3.1",
            "methodology_version": "v3.1",
        },
        "stats": {"events_this_week": 24, "wow": None,
                  "wow_basis": "not comparable — collection methodology "
                               "changed (v3.0 -> v3.1)",
                  "baseline_movement": {"events_moving_baseline": 0,
                                        "total_on_order_delta": 0},
                  "collection_health": {"wow_comparable": False}},
        "bottom_line": "Fixture bottom line.",
        "key_judgements": KJS,
        "judgements_requiring_review": WITHHELD,
        "developments": DEVS,
        "background_items": BACKGROUND,
        "priority_watch": PRIORITY_WATCH,
        "intelligence_gaps": GAPS,
        "since_last_week": SINCE,
        "annex_events": ANNEX,
        "orbat_delta": [], "capability_timeline": [],
        "self_checks": [],
    }


if __name__ == "__main__":
    out = HERE / "report_fixture.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("wrote", out)
