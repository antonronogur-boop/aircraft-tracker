# -*- coding: utf-8 -*-
"""ELES uzemeltetesi allapot — CSAK OLVAS (adatbazisba semmit nem ir).

  python scripts/ops_status.py

Kimenet: kepernyo + data/ops_status_<UTC>.json (a teljes, gepi valtozat).
  A. Forrasok: az ac_sources MINDEN sora (enabled, rss_url) — pontosan az,
     amit a collector hasznal (collect_rss.py: rss_url not null AND
     enabled = true); tier, policy, feed-formatum (RSS/Atom, elo lekeres),
     cikkek szama, utolso gyujtes, utolso 7 / 30 nap.
  B. Futasok: pipeline_runs utolso ac_* bejegyzesei.
  C. Coverage MOST (60 nap, a jelenlegi heti ablakkal) — prioritasi orszagok
     es regiok.
  D. Archivum: ac_reports hetek, Command Brief, draft-statusz, kiadas.
  E. Migraciok: ac_events.triage oszlop megvan-e.
  F. GAP-orszagok hivatalos jeloltjei: van-e RSS/Atom, elerheto-e az oldal
     (stabil page-polling jelolt), vagy elerhetetlen.
Csak stdlib + a meglevo scripts/ modulok (feedparser / anthropic nem kell).
"""
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402
import coverage_audit  # noqa: E402
import ac_hungary  # noqa: E402
import ac_window  # noqa: E402
import source_discovery  # noqa: E402  (csak olvas: RSS/Atom ellenorzes)

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime.now(timezone.utc)
OUT = {"checked_utc": NOW.strftime("%Y-%m-%d %H:%M:%S UTC")}
OFFICIAL = {"official_af", "mod", "procurement_agency", "nato", "government"}


def cfg(name):
    try:
        return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def feed_probe(url):
    """Elo lekeres ugyanugy, mint a forrasfelderites: valodi RSS vagy Atom,
    tetelek szama, legujabb tetel datuma."""
    ok, info = source_discovery.check_feed(url, 25)
    if not ok:
        return {"format": "FAILED", "error": info.get("error")}
    try:
        body, _ = source_discovery.fetch(url, 25)
        head = body[:600].decode("utf-8", "replace").lower()
        fmt = "Atom" if "<feed" in head else "RSS"
    except Exception:  # noqa: BLE001
        fmt = "?"
    return {"format": fmt, "items": info.get("items"), "newest": info.get("newest")}


def main():
    tiers = cfg("coverage_sources.json").get("existing_source_tiers") or {}
    default_tier = cfg("coverage_sources.json").get("default_tier") or "specialist_defence"
    policies = (cfg("source_policy.json").get("policies") or {})

    # ---------------- A. forrasok ----------------
    sources = db.select("ac_sources", {"select": "*", "order": "source_id.asc"})
    arts = db.select("ac_articles", {"select": "source_id,collected_date,publish_date"})
    per = defaultdict(lambda: {"n": 0, "last": None, "d7": 0, "d30": 0})
    d7 = (NOW - timedelta(days=7)).date().isoformat()
    d30 = (NOW - timedelta(days=30)).date().isoformat()
    for a in arts:
        p = per[a.get("source_id")]
        p["n"] += 1
        c = str(a.get("collected_date") or "")[:10]
        if c and (p["last"] is None or c > p["last"]):
            p["last"] = c
        if c >= d7:
            p["d7"] += 1
        if c >= d30:
            p["d30"] += 1
    try:
        last_collect = (db.select("pipeline_runs", {
            "select": "details,started_at", "script_name": "eq.ac_collect_rss",
            "order": "run_id.desc", "limit": "1"}) or [{}])[0]
    except Exception:  # noqa: BLE001
        last_collect = {}
    last_src = ((last_collect.get("details") or {}).get("sources") or {})
    rows = []
    print("\nA. SOURCES — ac_sources (the collector reads: rss_url not null AND enabled = true)")
    print("{:<9} {:<34} {:<7} {:<19} {:<10} {:<7} {:<6} {:>6} {:>4} {:>4}  {}".format(
        "id", "name", "ACTIVE", "tier", "policy", "format", "newest", "arts", "7d", "30d", "last collected"))
    for s in sources:
        sid = s["source_id"]
        active = bool(s.get("enabled")) and bool(s.get("rss_url"))
        tier = tiers.get(sid, default_tier)
        probe = feed_probe(s["rss_url"]) if active else {}
        p = per.get(sid) or {"n": 0, "last": None, "d7": 0, "d30": 0}
        r = {"source_id": sid, "name": s.get("source_name"), "active": active,
             "enabled": s.get("enabled"), "rss_url": s.get("rss_url"),
             "language": s.get("language"), "tier": tier,
             "category": ("official" if tier in OFFICIAL else "OEM" if tier == "oem"
                          else "regional media" if tier in ("regional_media", "general_media")
                          else "specialist media"),
             "policy": (policies.get(sid) or {}).get("policy", "pass"),
             "feed": probe, "articles_total": p["n"], "last_collected": p["last"],
             "articles_7d": p["d7"], "articles_30d": p["d30"]}
        rows.append(r)
        print("{:<9} {:<34} {:<7} {:<19} {:<10} {:<7} {:<6} {:>6} {:>4} {:>4}  {}".format(
            sid, (r["name"] or "")[:34], "ACTIVE" if active else "-", tier, r["policy"],
            probe.get("format", "-")[:7], str(probe.get("newest") or "-")[5:], p["n"], p["d7"], p["d30"],
            p["last"] or "never"))
        ls = last_src.get(sid)
        r["last_run"] = ls
        if ls and not ls.get("ok"):
            print("          ^ last scheduled collection FAILED for this source: {}".format(
                ls.get("error")))
    act = [r for r in rows if r["active"]]
    summ = Counter(r["category"] for r in act)
    fmts = Counter((r["feed"] or {}).get("format", "?") for r in act)
    print("ACTIVE: {} of {} · {} · feed formats {} · polling sources: 0 (collector has no page polling)".format(
        len(act), len(rows), dict(summ), dict(fmts)))
    OUT["sources"] = rows
    OUT["sources_summary"] = {"active": len(act), "total": len(rows), "by_category": dict(summ),
                              "by_format": dict(fmts), "polling": 0}

    # ---------------- B. futasok ----------------
    runs = db.select("pipeline_runs", {"select": "*", "script_name": "like.ac_*",
                                       "order": "run_id.desc", "limit": "15"})
    print("\nB. PIPELINE RUNS (pipeline_runs, latest ac_*)")
    for r in runs:
        print("  {:<24} {:<8} started {} finished {} items {} {}".format(
            r.get("script_name"), r.get("status"), str(r.get("started_at") or r.get("created_at") or "")[:19],
            str(r.get("finished_at") or "")[:19], r.get("items_processed"),
            (r.get("error_message") or "")[:80]))
    OUT["runs"] = runs
    raw = db.select("ac_articles", {"select": "article_id,collected_date",
                                    "status": "eq.raw"})
    oldest = min((str(a.get("collected_date") or "") for a in raw), default="")
    print("  RAW BACKLOG (collected, not yet processed): {}{}".format(
        len(raw), " · oldest collected {}".format(oldest) if raw else ""))
    OUT["raw_backlog"] = {"count": len(raw), "oldest": oldest or None}

    # ---------------- C. coverage most ----------------
    countries = {c["country_id"]: c for c in db.select(
        "ac_countries", {"select": "country_id,name,region,aliases"})}
    since = (NOW - timedelta(days=95)).date().isoformat()
    events = db.select("ac_events", {
        "select": "event_id,country_id,article_id,event_date,announcement_date,created_at,review_status",
        "review_status": "neq.rejected", "created_at": "gte." + since})
    art_src = {}
    ids = sorted({e.get("article_id") for e in events if e.get("article_id")})
    for i in range(0, len(ids), 100):
        chunk = ",".join('"{}"'.format(x) for x in ids[i:i + 100])
        for a in db.select("ac_articles", {"select": "article_id,source_id",
                                           "article_id": "in.({})".format(chunk)}):
            art_src[a["article_id"]] = a
    win = ac_window.reporting_window(NOW)
    cov = coverage_audit.audit(events, art_src, countries, ac_hungary.load_config(),
                               window=win, now=NOW.replace(tzinfo=None))
    print("\nC. COVERAGE NOW (60 days to {}; current window {} → {})".format(
        NOW.date(), win["start_date"], win["end_date"]))
    for g, items in (cov.get("groups") or {}).items():
        print("  [{}]".format(g))
        for c in items:
            print("    {:<26} {:<9} events60d {:>3}  sources {:>2}  official {}  missing official: {}".format(
                c["name"], c["status"], c["events_60d"], c["distinct_sources"],
                "yes" if c["official_source"] else "no",
                "; ".join(x["name"] for x in c.get("candidate_sources") or []
                          if x.get("tier") in OFFICIAL) or "—"))
    for reg, r in (cov.get("regions") or {}).items():
        print("  region {:<22} {}".format(reg, json.dumps(r, ensure_ascii=False)))
    OUT["coverage"] = cov
    OUT["window"] = {k: str(v) for k, v in win.items()}

    # ---------------- F. GAP-ek: hivatalos forras, feed, polling ----------------
    print("\nF. GAP / no-official countries — official candidate: feed? page reachable (polling)?")
    disc = {}
    for g, items in (cov.get("groups") or {}).items():
        for c in items:
            if c["status"] == "ADEQUATE" and c["official_source"]:
                continue
            for cand in c.get("candidate_sources") or []:
                if cand.get("tier") not in OFFICIAL or cand["name"] in disc:
                    continue
                r = source_discovery.discover(cand, 10)
                disc[cand["name"]] = dict(r, country=c["name"], status_cov=c["status"])
                print("  {:<24} {:<8} {:<44} {}".format(
                    c["name"][:24], c["status"], cand["name"][:44],
                    "FEED " + ", ".join(f["url"] for f in r["feeds"]) if r["feeds"]
                    else ("page reachable — polling candidate" if r["status"].startswith("NO FEED")
                          else "UNREACHABLE ({})".format(r.get("error")))))
    OUT["gap_sources"] = disc

    # ---------------- D. archivum ----------------
    reps = db.select("ac_reports", {
        "select": "week_label,period_start,period_end,generated_at,"
                  "brief:payload->command_brief->>schema,"
                  "draft_status:payload->command_brief_draft->>status,"
                  "draft_rev:payload->command_brief_draft->>revision,"
                  "release1:payload->command_brief_draft->releases->0->>release_no",
        "order": "period_end.desc"})
    print("\nD. ARCHIVE — ac_reports (one row per week; upsert key week_label)")
    for r in reps:
        print("  {:<9} {} → {}  generated {}  brief {:<16} draft {:<10} rev {:<3} released {}".format(
            r["week_label"], r["period_start"], r["period_end"], str(r["generated_at"])[:16],
            r.get("brief") or "—", r.get("draft_status") or "—", r.get("draft_rev") or "—",
            "R-" + r["release1"] if r.get("release1") else "—"))
    OUT["archive"] = reps

    # ---------------- E. migraciok ----------------
    try:
        db.select("ac_events", {"select": "triage", "limit": "1"})
        OUT["triage_column"] = True
    except Exception:  # noqa: BLE001
        OUT["triage_column"] = False
    print("\nE. ac_events.triage column: {}".format("present" if OUT["triage_column"] else
                                                   "NOT present (add_review_triage.sql not applied; triage step skips)"))

    out = ROOT / "data" / "ops_status_{}.json".format(NOW.strftime("%Y%m%dT%H%M%SZ"))
    out.write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\nSaved {}".format(out))


if __name__ == "__main__":
    main()
