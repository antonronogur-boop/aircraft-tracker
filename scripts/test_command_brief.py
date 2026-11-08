# -*- coding: utf-8 -*-
"""Command Brief + Wednesday window + HU relevance — offline tests.

No database, no API key, no network. Five blocks:
  A. reporting window (Budapest, Wed 00:00 -> Tue 23:59:59, DST, transition)
  B. Hungary-relevance model (separate from significance; distance is not all)
  C. brief built from the report fixture: single truth, no filler, limits
  D. executive-synthesis validation (no new numbers/countries, withheld leak)
  E. the REAL generate_weekly_report.main() against an in-memory database:
     rejected events excluded, future-dated excluded, late-arriving flagged,
     no silent overwrite, controlled restatement, brief embedded in payload.

Run: python scripts/test_command_brief.py
"""
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ac_window as W  # noqa: E402
import ac_hungary as H  # noqa: E402
import ac_command_brief as B  # noqa: E402
import coverage_audit as C  # noqa: E402

FAILS = []
COUNTRIES = {c["country_id"]: c for c in json.loads(
    (HERE.parent / "data" / "countries.json").read_text(encoding="utf-8"))}


def check(label, got, expected):
    ok = got == expected
    print("  {:<66} {!s:<16} {}".format(
        label[:66], str(got)[:16],
        "ok" if ok else "FAIL (expected {!r})".format(expected)))
    if not ok:
        FAILS.append((label, got, expected))


def section(t):
    print("\n" + t)
    print("-" * 92)


def fixture():
    sys.path.insert(0, str(HERE / "fixtures"))
    import make_report_fixture as F  # noqa: E402
    return json.loads(json.dumps(F.build()))


def coverage_for(payload_like=None):
    ev, arts, n = [], {}, 0
    plan = [("srb", 5, ["ACS-0001", "ACS-0003"]), ("rou", 3, ["ACS-0001"]),
            ("ukr", 9, ["ACS-0009", "ACS-0002"]),
            ("pol", 6, ["ACS-0002", "ACS-0005"]),
            ("usa", 20, ["ACS-0005", "ACS-0002"]), ("hun", 1, ["ACS-0003"]),
            ("aut", 1, ["ACS-0004"]), ("svk", 2, ["ACS-0004"]),
            ("rus", 4, ["ACS-0007", "ACS-0009"]), ("isr", 3, ["ACS-0002"]),
            ("cze", 1, ["ACS-0004"])]
    for cid, k, srcs in plan:
        for i in range(k):
            n += 1
            arts["a%d" % n] = {"source_id": srcs[i % len(srcs)]}
            ev.append({"event_id": n, "country_id": cid, "article_id": "a%d" % n,
                       "event_date": "2026-11-0%d" % (4 + i % 6),
                       "review_status": "pending" if i % 2 else "approved"})
    ev.append({"event_id": 999, "country_id": "blr", "article_id": None,
               "event_date": "2026-11-05", "review_status": "rejected"})
    win = W.reporting_window(datetime(2026, 11, 11, 5, 15))
    return C.audit(ev, arts, COUNTRIES, H.load_config(), window=win,
                   now=datetime(2026, 11, 11))


# --------------------------------------------------------------------------
def test_window():
    section("A. Reporting window — Europe/Budapest, Wednesday 00:00 -> Tuesday "
            "23:59:59")
    w = W.reporting_window(datetime(2026, 11, 11, 5, 15))   # Wed 06:15 CET
    check("Wed morning run: start = previous Wednesday", w["start_date"],
          date(2026, 11, 4))
    check("Wed morning run: end = yesterday (Tuesday)", w["end_date"],
          date(2026, 11, 10))
    check("week label = ISO week of the Tuesday", w["week_label"], "2026-W46")
    check("start 00:00 CET = 23:00 UTC previous day",
          w["start_utc"].isoformat(), "2026-11-03T23:00:00")
    check("end 23:59:59 CET = 22:59:59 UTC", w["end_utc"].isoformat(),
          "2026-11-10T22:59:59")
    # Kedd 23:30 helyi ido: az aktualis ablak meg NEM zart le.
    w2 = W.reporting_window(datetime(2026, 11, 10, 22, 30))  # Tue 23:30 CET
    check("Tue 23:30 local: last CLOSED window ends previous Tuesday",
          w2["end_date"], date(2026, 11, 3))
    # Kedd 22:30 UTC = szerda 00:30 CEST nyaron -> mar az uj ablak zart.
    w3 = W.reporting_window(datetime(2026, 7, 14, 22, 30))   # Wed 00:30 CEST
    check("summer: Tue 22:30 UTC is Wed 00:30 CEST -> window closed",
          w3["end_date"], date(2026, 7, 14))
    check("summer offset +2h", W.budapest_offset(datetime(2026, 7, 1)).seconds
          // 3600, 2)
    check("winter offset +1h", W.budapest_offset(datetime(2026, 1, 1)).seconds
          // 3600, 1)
    check("DST starts last Sunday of March 01:00 UTC",
          W.budapest_offset(datetime(2026, 3, 29, 1, 0)).seconds // 3600, 2)
    check("DST ends last Sunday of October 01:00 UTC",
          W.budapest_offset(datetime(2026, 10, 25, 1, 0)).seconds // 3600, 1)
    wt = W.reporting_window(datetime(2026, 11, 11, 5, 15),
                            prior_period_end="2026-11-02")
    check("transition from Monday rhythm: no day lost (start Nov 3)",
          wt["start_date"], date(2026, 11, 3))
    check("transition is stated, not silent", bool(wt["transition"]), True)
    wn = W.reporting_window(datetime(2026, 11, 18, 5, 15),
                            prior_period_end="2026-11-10")
    check("steady state: no transition", wn["transition"], None)
    check("created_at 2026-11-10T23:30Z is Wednesday local -> next window",
          W.local_day_of_timestamp("2026-11-10T23:30:00+00:00"),
          date(2026, 11, 11))


# --------------------------------------------------------------------------
def test_hu_model():
    section("B. Hungary relevance — separate from significance; not distance")
    cfg = H.load_config()
    srb = H.score_item({"title": "Serbia receives first two Rafale fighters",
                        "capability_domain": "fighter_strike",
                        "significance": 4, "effect_timing": "<12 months"},
                       ["srb"], COUNTRIES, cfg)
    jpn = H.score_item({"title": "Japan orders 40 more F-35A",
                        "capability_domain": "fighter_strike",
                        "significance": 5, "effect_timing": ">3 years"},
                       ["jpn"], COUNTRIES, cfg)
    usa = H.score_item({
        "title": "USAF deploys F-16s to Romania for enhanced Air Policing "
                 "after a drone airspace violation",
        "fact": "The F-16s will fly QRA from Câmpia Turzii.",
        "capability_domain": "fighter_strike", "significance": 3,
        "effect_timing": "immediate"}, ["usa"], COUNTRIES, cfg)
    check("Serbia Rafale (neighbour, sig 4) -> HIGH", srb["level"], "HIGH")
    check("Japan F-35 (sig 5, distant) -> MINIMAL", jpn["level"], "MINIMAL")
    check("significance and HU relevance are independent",
          jpn["level"] != "HIGH" and srb["level"] == "HIGH", True)
    check("US deployment to Romania: distant actor, HIGH relevance",
          usa["level"], "HIGH")
    fids = {f["id"] for f in usa["factors"]}
    check("…via eastern-flank posture factor", "eastern_flank_posture" in fids,
          True)
    check("…via air policing / QRA factor", "air_policing" in fids, True)
    check("…via airspace incident factor", "airspace_incident" in fids, True)
    gri = H.score_item({"title": "Thailand orders four Gripen E",
                        "capability_domain": "fighter_strike",
                        "significance": 3}, ["tha"], COUNTRIES, cfg)
    check("MH platform (Gripen) lifts a distant item", any(
        f["id"] == "mh_platform" for f in gri["factors"]), True)
    own = H.score_item({"title": "Analysis", "so_what": "Matters for Hungary's "
                        "southern border", "capability_domain": "other"},
                       ["jpn"], COUNTRIES, cfg)
    check("our own so_what does not raise HU relevance (no self-proof)",
          any(f["id"] == "hungary_named" for f in own["factors"]), False)
    check("every applied factor carries points and a reason",
          all("points" in f and f.get("why") for f in usa["factors"]), True)
    # v2 finomitas (W45 tanulsagai)
    eth = H.score_item({"title": "Ethiopia first delivery of Su-35SE "
                                 "fighters from Russia",
                        "fact": "Two Su-35SE were delivered by Russia.",
                        "capability_domain": "fighter_strike",
                        "lifecycle_stage": "delivery", "significance": 4,
                        "effect_timing": "<12 months"}, ["eth"], COUNTRIES,
                       cfg)
    check("Ethiopia + Russian supplier ≠ Hungary relevance (MINIMAL)",
          eth["level"], "MINIMAL")
    check("supplier link is at most one small factor", sum(
        f["points"] for f in eth["factors"] if f["id"] == "cee_named") <= 6,
        True)
    ukr = H.score_item({"title": "France to begin Rafale pilot training for "
                                 "Ukraine", "capability_domain":
                        "fighter_strike", "lifecycle_stage": "ioc",
                        "significance": 3, "effect_timing": "unknown"},
                       ["ukr"], COUNTRIES, cfg)
    check("Ukrainian air capability milestone can reach HIGH", ukr["level"],
          "HIGH")
    pol = H.score_item({"title": "Poland FA-50 reach FOC; assume QRA duties",
                        "fact": "The FA-50s took over quick reaction alert.",
                        "capability_domain": "fighter_strike",
                        "lifecycle_stage": "foc", "significance": 3,
                        "effect_timing": "immediate"}, ["pol"], COUNTRIES,
                       cfg)
    check("eastern-flank QRA change can reach HIGH", pol["level"], "HIGH")
    gj = H.score_item({"title": "China GJ-21 UCAV deck operations",
                       "capability_domain": "uncrewed_cca",
                       "lifecycle_stage": "ioc", "significance": 5,
                       "effect_timing": "<12 months"}, ["chn"], COUNTRIES,
                      cfg)
    check("distant UCAV milestone: doctrinal relevance only (LOW)",
          gj["level"], "LOW")
    check("rationale is whole sentences", ukr["rationale"].endswith("."),
          True)
    check("rank: HU before significance",
          H.rank_key(srb, 4, "moderate", "<12 months")
          < H.rank_key(jpn, 5, "high", "immediate"), True)


# --------------------------------------------------------------------------
def _all_exec_text(b):
    """Minden vezetoi szoveg a briefbol (a csonkitas-ellenorzeshez)."""
    out = [s["text"] for s in b["page1"]["bottom_line"]["sentences"]]
    for k in b["page1"]["primary"]:
        out += [k[f] for f in ("statement", "what_changed", "assessment",
                               "why_hungary", "next_observable",
                               "alternative_explanation")]
    out += [x["line"] for x in b["page1"]["secondary_watch"]]
    for r in b["page2"]["rows"]:
        out += [r["what_changed"], r["effect"], r["next_observable"],
                r["hu_why"]]
    for q in b["page2"]["collection_requirements"]:
        out += [q["question"], q["observable"]]
    for sec in b["page3"]["sections"]:
        out += [i["assessment"] for i in sec["items"]]
    out += [i["assessment"] for i in b["page4"]["global"]["items"]]
    for w in b["page4"]["priority_watch"]:
        out += [w["why"], w["next_observable"]]
    out += [g["text"] for g in b["page4"]["intelligence_gaps"]]
    out += [o["expected_observable"] for o in b["page4"]["outlook"]]
    return [x for x in out if x]


def test_brief():
    section("C. Command brief v2 — standalone, sourced, no truncation")
    p = fixture()
    cov = coverage_for()
    b = B.build_command_brief(p, COUNTRIES, coverage=cov)
    devs = {d["ref"]: d for d in p["developments"]}
    kj_ids = {k["id"] for k in p["key_judgements"]}
    tr = b["traceability"]

    check("schema", b["schema"], "command_brief_v2")
    check("status line for exports", b["status_line"],
          "EDITABLE EXPORT — GENERATED FROM AIRCRAFT TRACKER")
    check("country derived from annex (D-03 Ukraine)",
          devs["D-03"]["country_ids"], ["ukr"])
    check("HU relevance written back into the DETAILED layer",
          all("hu_relevance" in d for d in p["developments"]), True)
    check("no unresolved analyst refs", tr["unresolved_refs"], [])
    check("no unresolved sources", tr["unresolved_sources"], [])
    check("every executive item has an original source",
          tr["items_without_source"], [])
    prim = b["page1"]["primary"]
    check("at most 3 primary KJs", 1 <= len(prim) <= 3, True)
    check("no LOW/MINIMAL primary without exception", all(
        k["hu_relevance"]["level"] in ("HIGH", "MEDIUM")
        or k["primary_reason"].startswith("strategic exception")
        for k in prim), True)
    ranks = [H.LEVEL_RANK[k["hu_relevance"]["level"]] for k in prim]
    check("primary ranked by HU relevance first", ranks == sorted(ranks),
          True)
    check("primary items: full KJ structure + sources", all(
        k["statement"] and k["what_changed"] and k["assessment"]
        and k["why_hungary"] and k["next_observable"]
        and k["alternative_explanation"] and k["sources"] for k in prim),
        True)
    for k in prim:
        for r in k["refs"]:
            if not (r in devs or r in kj_ids):
                FAILS.append(("ref resolves", r, "known"))
    sec = b["page1"]["secondary_watch"]
    check("secondary watch ≤3 and only low-HU global items",
          len(sec) <= 3 and all(x["hu_level"] in ("LOW", "MINIMAL")
                                for x in sec), True)
    texts = _all_exec_text(b)
    check("no ellipsis anywhere in executive text",
          [t for t in texts if "…" in t or t.endswith("...")], [])
    check("executive text is whole sentences", [
        t for t in texts if t[-1] not in ".!?"], [])
    check("withheld KJ-05 never appears", any(
        "KJ-05" in (k["refs"] or []) for k in prim), False)
    check("withheld KJ's development not promoted to synthesis", any(
        k["origin"] == "executive_synthesis" and "D-03" in k["refs"]
        for k in prim), False)
    check("…but still reported as a fact row on page 2",
          "D-03" in [r["ref"] for r in b["page2"]["rows"]], True)
    refs_p234 = ([r["ref"] for r in b["page2"]["rows"]]
                 + [i["ref"] for s in b["page3"]["sections"]
                    for i in s["items"]]
                 + [i["ref"] for i in b["page4"]["global"]["items"]])
    check("no development repeated across pages 2-4",
          len(refs_p234) == len(set(refs_p234)), True)
    check("non-material item (D-10) appears nowhere", "D-10" in refs_p234
          or any("D-10" in k["refs"] for k in prim), False)
    check("allied posture in CEE on page 2 (US → Poland)", any(
        r["ref"] == "D-04" and r["group"] == "extended_nato"
        for r in b["page2"]["rows"]), True)
    check("Belarus = collection gap (only a REJECTED event exists)",
          "Belarus" in b["page2"]["collection_gap"], True)
    reqs = b["page2"]["collection_requirements"]
    check("collection requirements: gap → question → observable", bool(
        reqs) and all(q["gap"] and q["question"] and q["observable"]
                      for q in reqs), True)
    check("collection requirements start with GAP countries",
          reqs[0]["status"], "GAP")
    check("no requirement for a country that already has a row", any(
        q["country"] in ("Serbia", "Ukraine", "Romania", "Hungary")
        for q in reqs), False)
    mat = b["page3"]["maturity"]
    check("maturity matrix columns", mat["columns"],
          ["Intent", "Committed", "Contracted", "Fielding", "IOC", "FOC"])
    mrows = {r["ref"]: r for r in mat["rows"]}
    check("maturity: Romania LOA = Contracted", mrows["D-02"]["column"],
          "Contracted")
    check("maturity: Japan IOC = IOC", mrows.get("D-07", {}).get("column"),
          "IOC")
    check("maturity: loss shown as withdrawal",
          mrows["D-03"]["withdrawal"], True)
    secs = {x["key"]: x for x in b["page3"]["sections"]}
    check("page-3 sections ≤3 items", all(
        len(x["items"]) <= 3 for x in b["page3"]["sections"]), True)
    check("Middle East holds Israel", [i["ref"] for i in
                                       secs["middle_east"]["items"]],
          ["D-05"])
    ct = b["page3"]["change_table"]
    check("change table from since_last_week", ct["previous_week"],
          "2026-W45")
    check("change table priorities 1..n", [r["priority"] for r in ct["rows"]],
          list(range(1, len(ct["rows"]) + 1)))
    out = b["page4"]["outlook"]
    check("outlook = expected observables (1-5)", 1 <= len(out) <= 5
          and all(o["expected_observable"] for o in out), True)
    check("outlook led by the primary items", out[0]["subject"] in [
        devs[r].get("display_label") for k in prim for r in k["refs"]
        if r in devs], True)
    check("priority watch ≤5", len(b["page4"]["priority_watch"]) <= 5, True)
    check("intelligence gaps ≤5", len(b["page4"]["intelligence_gaps"]) <= 5,
          True)
    reg = b["page5"]["sources"]
    check("source register: ids S-01.. in reading order",
          [e["id"] for e in reg][:3], ["S-01", "S-02", "S-03"])
    check("every source has an original URL",
          all(str(e["url"]).startswith("http") for e in reg), True)
    by_title = {e["title"]: e for e in reg}
    hu_src = by_title.get("Kecskemétre érkezett az első KC-390 — Magyar "
                          "Honvédség")
    check("original-language Hungarian title kept", bool(hu_src), True)
    check("MoD source ranked Tier 1", (hu_src or {}).get("tier"), "Tier 1")
    st = [e for e in reg if e["state_controlled"]]
    check("two state-controlled publications …", len(st), 2)
    check("… share ONE lineage", len({e["lineage"] for e in st}), 1)
    check("state-controlled labelled as not independent",
          "not independent" in st[0]["source_type"], True)
    check("legend is the full static legend", [x["title"] for x in
                                              b["page5"]["legend"]][:2],
          ["Hungary relevance (HU)", "Air-power significance (SIG)"])
    check("principles include delivery ≠ IOC", any(
        "delivery ≠ IOC" in x for x in b["page5"]["principles"]), True)
    check("micro-legend present", "no hotspot ≠ no activity"
          in b["micro_legend"], True)
    bl = b["page1"]["bottom_line"]
    check("bottom line 4-7 sentences", 4 <= len(bl["sentences"]) <= 7, True)
    check("bottom line names primary items with sources", all(
        s["sources"] for s in bl["sentences"] if s["items"]), True)
    check("CEE map: Hungary flagged as home", b["page1"]["map_cee"]["home"],
          "hun")
    check("global map coloured by significance, not HU", "not by Hungary"
          in b["page4"]["map_global"]["caption"], True)
    # Csendes het
    p2 = fixture()
    p2["developments"] = [d for d in p2["developments"]
                          if d["title"].startswith(("Hungary", "Serbia"))]
    p2["key_judgements"] = [k for k in p2["key_judgements"]
                            if k["id"] == "KJ-02"]
    b2 = B.build_command_brief(p2, COUNTRIES, coverage=cov)
    e = {x["key"]: x["empty"] for x in b2["page3"]["sections"]}
    check("quiet Middle East -> 'NO MATERIAL CHANGE IDENTIFIED'",
          e["middle_east"], "NO MATERIAL CHANGE IDENTIFIED")
    check("quiet global -> labelled, not filled",
          b2["page4"]["global"]["empty"], "NO MATERIAL CHANGE IDENTIFIED")
    check("quiet week: more collection requirements fill page 2",
          len(b2["page2"]["collection_requirements"])
          >= len(b["page2"]["collection_requirements"]), True)
    # fit(): soha nem vag mondatot
    long = ("This is a very long single sentence " + "with many words " * 30
            + "that ends here.")
    check("fit() keeps an over-long sentence whole", B.fit(long, 80, 1),
          long)
    check("fit() drops whole trailing sentences only",
          B.fit("One. Two two two two.", 6, 2), "One.")
    return b


# --------------------------------------------------------------------------
class _FakeClient(object):
    pass


def test_synthesis():
    section("D. Executive synthesis + executive editor — validated, with "
            "fallback")
    import ac_intel
    p = fixture()
    cov = coverage_for()
    probe = B.build_command_brief(json.loads(json.dumps(p)), COUNTRIES,
                                  coverage=cov)
    ids = [k["id"] for k in probe["page1"]["primary"]]
    long_key = "{}|statement".format(ids[0])
    good = {
        "bottom_line": [
            {"text": "Serbia's first two Rafale do not yet change its "
                     "operational capability on Hungary's southern border.",
             "refs": ["KJ-02"]},
            {"text": "Hungary's first KC-390 restores national tactical "
                     "airlift options for MH.", "refs": ["XS-01"]},
            {"text": "Romania committed to 32 F-35A with first deliveries in "
                     "2032.", "refs": ["XS-02"]},
            {"text": "Serbia will field 48 Rafale by 2027.",
             "refs": ["KJ-02"]},
            {"text": "Croatia's Rafale fleet is now combat ready.",
             "refs": ["KJ-02"]},
            {"text": "Russia demonstrated effective counter-air capability "
                     "against Ukrainian F-16 operations.", "refs": ["D-03"]},
            {"text": "Serbia's Rafale build-up continues…",
             "refs": ["KJ-02"]},
        ],
        "why_hungary": {"KJ-02": "Serbia borders Hungary, so its fighter "
                                 "transition shapes the southern air "
                                 "picture."},
        "condensed": {long_key: "Short."},
    }
    orig = ac_intel._call
    try:
        ac_intel._call = lambda c, s, pl, mt: json.loads(json.dumps(good))
        b = B.build_command_brief(p, COUNTRIES, coverage=cov,
                                  client=_FakeClient())
    finally:
        ac_intel._call = orig
    bl = b["page1"]["bottom_line"]
    check("valid synthesis used and labelled", bl["origin"],
          "executive_synthesis")
    texts = " ".join(s["text"] for s in bl["sentences"])
    check("invented number (48) dropped", "48" in texts, False)
    check("uncited country (Croatia) dropped", "Croatia" in texts, False)
    check("withheld judgement echo dropped", "counter-air" in texts, False)
    check("ellipsis sentence dropped", "…" in texts, False)
    check("drops recorded with a reason",
          len(bl["dropped_by_validation"]) >= 4, True)
    check("kept sentences carry sources", all(
        s["sources"] for s in bl["sentences"]), True)
    kj2 = [k for k in b["page1"]["primary"] if k["id"] == "KJ-02"][0]
    check("why-Hungary from synthesis, labelled", kj2["why_hungary_origin"],
          "executive_synthesis")
    bad = {"bottom_line": [{"text": "Something with 999 aircraft.",
                            "refs": ["KJ-02"]}], "why_hungary": {}}
    try:
        ac_intel._call = lambda c, s, pl, mt: bad
        b2 = B.build_command_brief(fixture(), COUNTRIES, coverage=cov,
                                   client=_FakeClient())
        ac_intel._call = lambda c, s, pl, mt: None
        b3 = B.build_command_brief(fixture(), COUNTRIES, coverage=cov,
                                   client=_FakeClient())
    finally:
        ac_intel._call = orig
    check("too few valid sentences -> deterministic fallback",
          b2["page1"]["bottom_line"]["origin"], "deterministic")
    check("model unavailable -> deterministic, brief complete",
          (b3["page1"]["bottom_line"]["origin"],
           len(b3["page1"]["primary"]) >= 1), ("deterministic", True))
    # Vezetoi szerkeszto: csak rovidebb, egesz mondat, uj szam/orszag nelkul,
    # es a hedge megmarad.
    over = {"KJ-02|assessment": {"text": "Two aircraft may not yet change "
                                         "Serbia's capability in 2026.",
                                 "max": 40}}
    p4 = fixture()
    probe = B.build_command_brief(json.loads(json.dumps(p4)), COUNTRIES,
                                  coverage=cov)
    orig_ob = B._over_budget
    try:
        B._over_budget = lambda brief: over
        cases = {"Two aircraft may not change Serbia.": True,
                 "Two aircraft change Serbia.": False,
                 "Two aircraft may not change Serbia in 2027.": False,
                 "Two aircraft may not change Croatia.": False}
        for txt, expect in cases.items():
            ac_intel._call = (lambda t: lambda c, s, pl, mt: {
                "bottom_line": [], "why_hungary": {},
                "condensed": {"KJ-02|assessment": t}})(txt)
            bx = B.build_command_brief(fixture(), COUNTRIES, coverage=cov,
                                       client=_FakeClient())
            got = [k for k in bx["page1"]["primary"]
                   if k["id"] == "KJ-02"][0]
            check("editor {}: {}".format("accepts" if expect else "rejects",
                                         txt[:44]),
                  got["assessment"] == txt, expect)
    finally:
        ac_intel._call = orig
        B._over_budget = orig_ob


# --------------------------------------------------------------------------
# E. A VALODI generate_weekly_report.main() memoria-adatbazison
# --------------------------------------------------------------------------
class MemDB(object):
    def __init__(self, tables):
        self.t = tables
        self.upserts = []
        self.calls = []

    def select(self, table, params=None):
        params = params or {}
        self.calls.append((table, dict(params)))
        rows = list(self.t.get(table, []))
        for k, v in params.items():
            if k in ("select", "order", "limit"):
                continue
            op, _, val = str(v).partition(".")
            if op == "neq":
                rows = [r for r in rows if str(r.get(k)) != val]
            elif op == "eq":
                rows = [r for r in rows if str(r.get(k)) == val]
            elif op == "gte":
                rows = [r for r in rows if str(r.get(k) or "") >= val[:19]]
        if params.get("order") == "period_end.desc":
            rows.sort(key=lambda r: r.get("period_end") or "", reverse=True)
        if params.get("limit"):
            rows = rows[:int(params["limit"])]
        return [json.loads(json.dumps(r)) for r in rows]

    def upsert(self, table, rows, conflict):
        self.upserts.append((table, rows))
        cur = self.t.setdefault(table, [])
        for r in rows:
            cur[:] = [x for x in cur if x.get(conflict) != r.get(conflict)]
            cur.append(json.loads(json.dumps(r, default=str)))

    def start_run(self, name):
        return {"run": name}

    def finish_run(self, run, status, **kw):
        self.last_finish = (status, kw)


def _canned_call(client, system, payload, max_tokens):
    import ac_intel
    if system == ac_intel.DEV_PROMPT:
        evs = payload["events"]
        by_c = {}
        for e in evs:
            by_c.setdefault(e["country"], []).append(e["event_id"])
        devs = []
        for country, ids in sorted(by_c.items()):
            devs.append({
                "event_ids": ids, "title": "{} takes delivery of Rafale "
                                          "fighters".format(country),
                "display_label": "{} Rafale".format(country[:2].upper()),
                "capability_domain": "fighter_strike",
                "lifecycle_stage": "delivery",
                "fact": "The {} ministry stated that aircraft were "
                        "delivered.".format(country),
                "capability_delta": "Adds fighters to the {} air "
                                    "force.".format(country),
                "so_what": "Changes the regional air balance.",
                "novelty": "new", "significance": 4, "confidence": "moderate",
                "effect_timing": "<12 months",
                "effect_timing_basis": "delivery reported",
                "independent_lineages": 1, "reports_count": 1,
                "indicators_to_watch": ["Next delivery."]})
        return {"developments": devs, "dropped_event_ids": []}
    if system == ac_intel.KJ_PROMPT:
        d = payload["developments"][0]
        return {"bottom_line": "Deliveries continued.",
                "key_judgements": [{
                    "id": "KJ-01", "domain": "fighter_strike",
                    "judgement": "Deliveries indicate a fighter transition "
                                 "in {}.".format(d["title"].split(" takes")[0]),
                    "confidence": "moderate", "basis": "Ministry statement.",
                    "assessment": "Scale depends on crews and weapons.",
                    "effect_timing": "<12 months",
                    "alternative_explanation": None,
                    "indicators": ["Next delivery."],
                    "supporting_event_ids": d["event_ids"]}],
                "priority_watch": [], "intelligence_gaps": [
                    "Weapons package not reported."]}
    return None


def test_pipeline():
    section("E. generate_weekly_report.main() on an in-memory database")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
    os.environ["AC_BRIEF_SYNTHESIS"] = "0"
    import supabase_client as db
    import ac_intel
    import generate_weekly_report as G

    def ev(eid, cid, day, created, status="approved", tid="rafale"):
        return {"event_id": eid, "country_id": cid, "type_id": tid,
                "event_type": "delivery", "lifecycle_stage": "delivery",
                "quantity": 2, "event_date": day, "created_at": created,
                "review_status": status, "article_id": "art%d" % eid,
                "summary": "Aircraft delivered to {}.".format(cid)}

    events = [
        ev(1, "srb", "2026-11-05", "2026-11-05T08:00:00+00:00"),
        ev(2, "hrv", "2026-11-06", "2026-11-06T08:00:00+00:00",
           status="pending"),
        ev(3, "aut", "2026-11-07", "2026-11-07T08:00:00+00:00",
           status="rejected"),
        # Szerdai datum (az ablak utan) -> a kovetkezo heti jelentesbe.
        ev(4, "rou", "2026-11-11", "2026-11-11T04:40:00+00:00"),
        # Kedd 23:50 helyi = 22:50 UTC: az ablakban van.
        ev(5, "svk", "2026-11-10", "2026-11-10T22:50:00+00:00"),
        # Elozo ablakra eso, az elozo jelentes UTAN beerkezett: late-arriving.
        ev(6, "pol", "2026-11-02", "2026-11-09T09:00:00+00:00"),
        # Elozo ablakra eso, de MEG az elozo jelentes ELOTT beerkezett:
        # mar az elozo jelentes resze volt, nem szamit ujra.
        ev(7, "cze", "2026-11-02", "2026-11-04T04:00:00+00:00"),
    ]
    prior = {"week_label": "2026-W45", "period_start": "2026-10-27",
             "period_end": "2026-11-03",
             "generated_at": "2026-11-04T05:20:00+00:00",
             "payload": {"week_label": "2026-W45", "developments": [],
                         "priority_watch": [], "report_meta": {
                             "week_label": "2026-W45"}}}
    mem = MemDB({
        "ac_events": events,
        "ac_countries": [dict(v, aliases=v.get("aliases") or [])
                         for v in COUNTRIES.values()],
        "ac_aircraft_types": [{"type_id": "rafale", "name": "Dassault "
                               "Rafale", "category": "fighter"}],
        "ac_articles": [{"article_id": "art%d" % i, "title": "t%d" % i,
                         "url": "https://example.org/%d" % i,
                         "source_id": "ACS-0001" if i % 2 else "ACS-0002",
                         "publish_date": None} for i in range(1, 8)],
        "ac_fleets": [], "ac_programmes": [],
        "ac_reports": [prior], "ac_report_metrics": [],
    })
    saved = {k: getattr(db, k) for k in ("select", "upsert", "start_run",
                                         "finish_run")}
    saved_call = ac_intel._call
    try:
        for k in saved:
            setattr(db, k, getattr(mem, k))
        ac_intel._call = _canned_call
        os.environ["AC_REPORT_NOW"] = "2026-11-11T05:15:00Z"
        G.main(dry_run=False)
        ev_calls = [c for t, c in mem.calls if t == "ac_events"]
        check("events loaded with review_status=neq.rejected",
              ev_calls[0].get("review_status"), "neq.rejected")
        rep = [r for t, rows in mem.upserts if t == "ac_reports"
               for r in rows]
        check("one report written", len(rep), 1)
        pl = rep[0]["payload"]
        meta = pl["report_meta"]
        check("week label W46", rep[0]["week_label"], "2026-W46")
        check("period = Wed 2026-11-04 .. Tue 2026-11-10",
              (rep[0]["period_start"], rep[0]["period_end"]),
              ("2026-11-04", "2026-11-10"))
        check("window timezone stated", meta.get("timezone"),
              "Europe/Budapest")
        annex = {a["event_id"]: a for a in pl["annex_events"]}
        check("rejected event (3) excluded", 3 in annex, False)
        check("pending event (2) included, flagged pending",
              annex.get(2, {}).get("pending"), True)
        check("Wednesday-dated event (4) not in this window", 4 in annex,
              False)
        check("Tue 23:50 local event (5) in window", 5 in annex, True)
        check("late-arriving event (6) included and flagged",
              annex.get(6, {}).get("late_arriving"), True)
        check("event already covered by prior report (7) not re-counted",
              7 in annex, False)
        check("late-arriving count in stats",
              pl["stats"]["collection_health"][
                  "late_arriving_from_previous_period"], 1)
        cb = pl.get("command_brief") or {}
        check("command brief embedded in the SAME payload", cb.get("schema"),
              "command_brief_v2")
        check("brief refs resolve against the payload",
              cb.get("traceability", {}).get("unresolved_refs"), [])
        dev_refs = {d["ref"] for d in pl["developments"]}
        check("brief cites only developments in the detailed layer",
              set(r for r in cb["traceability"]["analyst_refs_used"]
                  if r.startswith("D-")) <= dev_refs, True)
        check("sources resolve to ORIGINAL article URLs", all(
            e["url"].startswith("https://example.org/")
            for e in cb["page5"]["sources"]), True)
        check("every executive item has a source",
              cb["traceability"]["items_without_source"], [])
        check("coverage audit embedded",
              "priority" in (pl.get("coverage") or {}), True)
        check("Austria (only a rejected event) -> coverage GAP",
              pl["coverage"]["countries"]["aut"]["status"], "GAP")
        check("methodology version v3.1", meta["methodology_version"],
              "v3.1")

        # --- ujrafuttatas ugyanarra a hetre: NINCS csendes feluliras ---
        n_before = len(mem.upserts)
        G.main(dry_run=False)
        check("re-run without --restate writes nothing",
              len(mem.upserts), n_before)
        G.main(dry_run=False, restate_reason="late MoD confirmation")
        rep2 = [r for t, rows in mem.upserts[n_before:] if t == "ac_reports"
                for r in rows]
        check("--restate writes once", len(rep2), 1)
        rs = rep2[0]["payload"]["report_meta"].get("restatement") or {}
        check("restatement is visible with reason", rs.get("reason"),
              "late MoD confirmation")
        check("restatement keeps the previous generation time",
              bool(rs.get("previous_generated_utc")), True)
        check("brief carries the revision (small badge, not a banner)",
              (rep2[0]["payload"]["command_brief"]["meta"].get("revision")
               or {}).get("number"), 1)
    finally:
        for k, v in saved.items():
            setattr(db, k, v)
        ac_intel._call = saved_call
        os.environ.pop("AC_REPORT_NOW", None)
    out = HERE / "fixtures" / "pipeline_payload.json"
    out.write_text(json.dumps(pl, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")


def test_triage():
    section("F. Review triage — advisory only, approval semantics unchanged")
    import triage_events as TR
    cfg_src = json.loads((HERE.parent / "config" / "coverage_sources.json")
                         .read_text(encoding="utf-8"))
    types = {"rafale": {"type_id": "rafale", "name": "Dassault Rafale",
                        "category": "fighter"}}
    arts = {"a1": {"source_id": "ACS-0001", "url": "https://x.org/1"},
            "a2": {"source_id": "ACS-0007", "url": "https://tass.ru/2"}}
    srcs = {"ACS-0001": {"source_name": "Defense News"}}
    base = {"country_id": "srb", "type_id": "rafale", "event_type": "delivery",
            "lifecycle_stage": "delivery", "quantity": 2,
            "event_date": "2026-11-05", "summary": "Serbia received two "
            "Rafale fighters.", "confidence": 0.9, "article_id": "a1",
            "review_status": "pending"}
    e1 = dict(base, event_id=1)
    e2 = dict(base, event_id=2, event_date="2026-11-08", article_id="a2")
    e3 = {"event_id": 3, "country_id": None, "type_id": None,
          "unresolved_country_name": "?", "event_type": "other",
          "summary": "A drone was seen.", "event_date": "2026-11-05",
          "confidence": 0.3, "article_id": "a1"}
    ctx = (COUNTRIES, types, arts, srcs, {}, [e1, e2, e3], cfg_src,
           H.load_config())
    t1, t2, t3 = (TR.classify(e, ctx) for e in (e1, e2, e3))
    check("first report of a Serbian delivery: likely duplicate of #2",
          (t1["triage_class"], t1["duplicate_of"]), ("likely_duplicate", 2))
    check("state-controlled source flagged in rationale",
          "state-controlled" in t2["rationale"], True)
    check("unresolved, low-relevance extraction -> low_relevance",
          t3["triage_class"], "low_relevance")
    e4 = dict(base, event_id=4, country_id="pol", event_type="order",
              lifecycle_stage="contract_signed", quantity=None)
    t4 = TR.classify(e4, (COUNTRIES, types, arts, srcs, {}, [e4], cfg_src,
                          H.load_config()))
    check("Polish contract -> likely material", t4["triage_class"],
          "likely_material")
    check("triage carries every review field", all(k in t4 for k in (
        "country", "source", "source_tier", "domain", "hu_relevance",
        "relevance", "novelty", "duplicate_probability", "materiality",
        "rationale")), True)
    check("triage never sets review_status", "review_status" in t4, False)


if __name__ == "__main__":
    test_window()
    test_hu_model()
    b = test_brief()
    test_synthesis()
    test_pipeline()
    test_triage()
    print("\n" + "=" * 92)
    if FAILS:
        print("{} check(s) FAILED:".format(len(FAILS)))
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("All Command Brief checks passed.")
