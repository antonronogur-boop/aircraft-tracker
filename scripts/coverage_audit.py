# -*- coding: utf-8 -*-
"""COVERAGE AUDIT — orszagonkent / regionkent ADEQUATE / PARTIAL / GAP.

Elobb meg kell nezni, HOL hianyos a gyujtes, es csak utana uj forrast
felvenni. A foldrajz gyujtesi prioritas, nem automatikus bekerules: ez az
audit azt mondja meg, hogy egy orszagrol azert nincs-e a briefben semmi,
mert NEM TORTENT semmi, vagy mert NEM LATUNK oda.

  ADEQUATE  >= 4 esemeny az utolso 60 napban, >= 2 kulonbozo forrasbol
  PARTIAL   legalabb 1 esemeny, de a fenti alatt
  GAP       0 esemeny 60 nap alatt — a hallgatas itt NEM bizonyitek

A szamolas az elutasitott (rejected) esemenyeket kizarja, a pending-et
beszamitja (ugyanaz a szemantika, mint a heti jelentesnel).

A heti jelentes ugyanezt a fuggvenyt hivja (audit()), igy a brief es a
kulon futtathato audit sosem mond mast.

Usage: python scripts/coverage_audit.py [--days 60] [--json data/coverage_audit.json]
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
SOURCES_CFG = ROOT / "config" / "coverage_sources.json"

ADEQUATE_EVENTS = 4
ADEQUATE_SOURCES = 2


def load_sources_config():
    try:
        return json.loads(SOURCES_CFG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"existing_source_tiers": {}, "candidates": [],
                "default_tier": "specialist_defence", "tier_labels": {}}


def status_for(n_events, n_sources):
    if n_events >= ADEQUATE_EVENTS and n_sources >= ADEQUATE_SOURCES:
        return "ADEQUATE"
    if n_events >= 1:
        return "PARTIAL"
    return "GAP"


def audit(events, articles_by_id, countries_by_id, hu_cfg, window=None,
          src_cfg=None, days=60, now=None):
    """events: nem-elutasitott esemenyek (legalabb az utolso `days` nap).

    window: ac_window.reporting_window() eredmenye — az e heti darabszamhoz.
    Visszaad: {"countries": {cid: {...}}, "regions": {...},
               "priority": [...], "summary": {...}}
    """
    from ac_intel import effective_day  # noqa: E402  (lusta import)
    src_cfg = src_cfg or load_sources_config()
    tiers = src_cfg.get("existing_source_tiers") or {}
    default_tier = src_cfg.get("default_tier") or "specialist_defence"
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    horizon = now - timedelta(days=days)

    per = defaultdict(lambda: {"events_60d": 0, "events_window": 0,
                               "sources": set(), "tiers": set()})
    for e in events or []:
        cid = e.get("country_id")
        if not cid or e.get("review_status") == "rejected":
            continue
        d = effective_day(e)
        if d is None or d < horizon:
            continue
        row = per[cid]
        row["events_60d"] += 1
        if window is not None:
            dd = d.date()
            if window["start_date"] <= dd <= window["end_date"]:
                row["events_window"] += 1
        art = (articles_by_id or {}).get(e.get("article_id") or "") or {}
        sid = art.get("source_id")
        if sid:
            row["sources"].add(sid)
            row["tiers"].add(tiers.get(sid, default_tier))

    groups = hu_cfg.get("brief_groups") or {}
    priority_ids = []
    for key in ("non_nato_priority", "neighbours", "extended_nato"):
        for cid in groups.get(key) or []:
            if cid not in priority_ids:
                priority_ids.append(cid)
    if "hun" not in priority_ids:
        priority_ids.insert(0, "hun")

    candidates = defaultdict(list)
    for c in src_cfg.get("candidates") or []:
        candidates[c.get("country_id")].append(c)

    out_c = {}
    for cid in sorted(set(per) | set(priority_ids)):
        r = per.get(cid) or {"events_60d": 0, "events_window": 0,
                             "sources": set(), "tiers": set()}
        st = status_for(r["events_60d"], len(r["sources"]))
        c = countries_by_id.get(cid) or {}
        tier_list = sorted(r["tiers"])
        out_c[cid] = {
            "country_id": cid,
            "name": c.get("name") or cid,
            "region": c.get("region"),
            "status": st,
            "events_60d": r["events_60d"],
            "events_window": r["events_window"],
            "distinct_sources": len(r["sources"]),
            "source_tiers": tier_list,
            # Az elsodleges (hivatalos) forras hianya kulon jelzes: a
            # szakmedia lefedettseg nem ugyanaz, mint a hivatalos.
            "official_source": bool(set(tier_list) & {
                "official_af", "mod", "procurement_agency", "nato"}),
            "candidate_sources": [
                {"name": x.get("name"), "homepage": x.get("homepage"),
                 "tier": x.get("tier"), "language": x.get("language"),
                 "caveat": x.get("caveat")}
                for x in candidates.get(cid, [])] if st != "ADEQUATE" else [],
        }

    regions = defaultdict(lambda: {"events_60d": 0, "countries": 0,
                                   "gap": 0, "partial": 0, "adequate": 0})
    for cid, c in countries_by_id.items():
        reg = c.get("region") or "Other"
        row = out_c.get(cid)
        n = row["events_60d"] if row else 0
        st = row["status"] if row else "GAP"
        regions[reg]["events_60d"] += n
        regions[reg]["countries"] += 1
        regions[reg][st.lower()] += 1
    out_r = {}
    for reg, r in regions.items():
        if r["adequate"] and r["adequate"] >= r["countries"] / 2.0:
            st = "ADEQUATE"
        elif r["events_60d"]:
            st = "PARTIAL"
        else:
            st = "GAP"
        out_r[reg] = dict(r, status=st)

    prio = [out_c[c] for c in priority_ids if c in out_c]
    return {
        "days": days,
        "thresholds": {"adequate_events": ADEQUATE_EVENTS,
                       "adequate_sources": ADEQUATE_SOURCES},
        "countries": out_c,
        "regions": out_r,
        "priority": prio,
        "summary": {
            "priority_adequate": sum(1 for p in prio
                                     if p["status"] == "ADEQUATE"),
            "priority_partial": sum(1 for p in prio
                                    if p["status"] == "PARTIAL"),
            "priority_gap": sum(1 for p in prio if p["status"] == "GAP"),
            "priority_without_official_source": sum(
                1 for p in prio if not p["official_source"]),
        },
        "note": ("Coverage reflects what the collection SEES, not what "
                 "happened. GAP means no reporting reached the pipeline in "
                 "{} days — absence of reporting is not absence of "
                 "activity.".format(days)),
    }


def main():
    import supabase_client as db  # noqa: E402
    import ac_hungary  # noqa: E402
    import ac_window  # noqa: E402
    days = 60
    out_path = None
    args = sys.argv[1:]
    if "--days" in args:
        days = int(args[args.index("--days") + 1])
    if "--json" in args:
        out_path = Path(args[args.index("--json") + 1])
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days + 30)).isoformat()
    events = db.select("ac_events", {
        "select": "event_id,country_id,article_id,event_date,"
                  "announcement_date,created_at,review_status",
        "review_status": "neq.rejected", "created_at": "gte." + since})
    arts = {a["article_id"]: a for a in db.select(
        "ac_articles", {"select": "article_id,source_id"})}
    countries = {c["country_id"]: c for c in db.select(
        "ac_countries", {"select": "country_id,name,region"})}
    hu = ac_hungary.load_config()
    win = ac_window.reporting_window(now)
    res = audit(events, arts, countries, hu, window=win, days=days,
                now=now.replace(tzinfo=None))
    print("COVERAGE AUDIT — last {} days (window {})".format(days,
                                                          win["label"]))
    print("\nPriority countries (Command Brief pages 1-2):")
    print("  {:<26} {:<9} {:>5} {:>5} {:>4}  {}".format(
        "country", "status", "60d", "week", "src", "official?"))
    for p in res["priority"]:
        print("  {:<26} {:<9} {:>5} {:>5} {:>4}  {}".format(
            p["name"][:26], p["status"], p["events_60d"], p["events_window"],
            p["distinct_sources"], "yes" if p["official_source"] else "NO"))
    print("\nRegions:")
    for reg, r in sorted(res["regions"].items()):
        print("  {:<22} {:<9} events_60d={:<4} countries={} (gap {})".format(
            reg, r["status"], r["events_60d"], r["countries"], r["gap"]))
    gaps = [p for p in res["priority"] if p["status"] != "ADEQUATE"]
    if gaps:
        print("\nCandidate sources for non-adequate priority countries "
              "(VERIFY the feed before adding to ac_sources):")
        for p in gaps:
            for c in p["candidate_sources"]:
                print("  {:<26} [{}] {} — {}{}".format(
                    p["name"][:26], c["tier"], c["name"], c["homepage"],
                    "  (caveat: {})".format(c["caveat"]) if c.get("caveat")
                    else ""))
    if out_path:
        out_path.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                       default=str), encoding="utf-8")
        print("\nSaved {}".format(out_path))


if __name__ == "__main__":
    main()
