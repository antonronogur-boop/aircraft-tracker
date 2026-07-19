# -*- coding: utf-8 -*-
"""Generate the analyst weekly report and archive it in ac_reports.

Computes hard stats (this week vs previous week vs previous 4-week average),
builds fleet context for each key deal (how many the country already has),
then asks Claude ONCE to write the analyst layers:
  * "week in one paragraph" overview with trend comparison,
  * a one-line fleet-context comment per key deal,
  * 1-2 sentence explanations per event-type slice,
  * a near-term / long-term watchlist assessment.

The frontend (/weekly) only renders the stored payload — no AI at view time.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY
Usage: python scripts\\generate_weekly_report.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

MODEL = "claude-sonnet-4-6"
DAY = timedelta(days=1)


def load_events(since, until=None):
    params = {"select": "*", "created_at": "gte.{}".format(since.isoformat()),
              "review_status": "neq.rejected", "order": "created_at.desc"}
    if until:
        params["created_at"] = "gte.{}".format(since.isoformat())
        # PostgREST needs and=() for two conditions on same column
        params = {"select": params["select"], "order": params["order"],
                  "review_status": "neq.rejected",
                  "and": "(created_at.gte.{},created_at.lt.{})".format(
                      since.isoformat(), until.isoformat())}
    return db.select("ac_events", params)


def main():
    run = db.start_run("ac_weekly_report")
    try:
        now = datetime.now(timezone.utc)
        wk_start, prev_start, month_start = now - 7 * DAY, now - 14 * DAY, now - 35 * DAY

        this_week = load_events(wk_start)
        prev_week = load_events(prev_start, wk_start)
        month = load_events(month_start, wk_start)  # the 4 weeks BEFORE this week

        countries = {c["country_id"]: c for c in db.select(
            "ac_countries", {"select": "country_id,name,region"})}
        types = {t["type_id"]: t for t in db.select(
            "ac_aircraft_types", {"select": "type_id,name,category"})}
        articles = {a["article_id"]: a for a in db.select(
            "ac_articles", {"select": "article_id,title,url"})}
        fleets = db.select("ac_fleets", {
            "select": "country_id,type_id,fleet_status,quantity"})

        def fleet_qty(cid, tid, status):
            return sum(f.get("quantity") or 0 for f in fleets
                       if f["country_id"] == cid and f["type_id"] == tid
                       and f["fleet_status"] == status)

        def cname(e):
            c = countries.get(e.get("country_id") or "")
            return c["name"] if c else (e.get("unresolved_country_name") or "?")

        def tname(e):
            t = types.get(e.get("type_id") or "")
            return t["name"] if t else (e.get("unresolved_type_name") or "?")

        hard = [e for e in this_week if e["event_type"] in ("order", "delivery", "export_sale")]
        key_deals = sorted(hard, key=lambda e: (-(float(e.get("value_usd_m") or 0)),
                                                -(int(e.get("quantity") or 0))))[:6]
        watchlist = [e for e in this_week if e["event_type"] in ("negotiation", "selection")]

        by_type, by_region = {}, {}
        for e in this_week:
            by_type.setdefault(e["event_type"], []).append(e)
            reg = (countries.get(e.get("country_id") or "") or {}).get("region")
            if reg:
                by_region.setdefault(reg, []).append(e)

        stats = {
            "events_this_week": len(this_week),
            "events_prev_week": len(prev_week),
            "events_prev_4wk_avg": round(len(month) / 4.0, 1),
            "firm_deals": len(hard),
            "aircraft_in_firm_deals": sum(int(e.get("quantity") or 0) for e in hard),
            "disclosed_value_usd_m": round(sum(float(e.get("value_usd_m") or 0)
                                               for e in this_week)),
            "pending_review": sum(1 for e in this_week if e.get("review_status") == "pending"),
        }

        # ---------- build the single Claude request ----------
        deal_ctx = []
        for e in key_deals:
            cid, tid = e.get("country_id"), e.get("type_id")
            deal_ctx.append({
                "event_id": e["event_id"], "event_type": e["event_type"],
                "country": cname(e), "aircraft": tname(e),
                "quantity": e.get("quantity"), "value_usd_m": e.get("value_usd_m"),
                "summary": e["summary"],
                "existing_active": fleet_qty(cid, tid, "active") if cid and tid else None,
                "existing_on_order": fleet_qty(cid, tid, "on_order") if cid and tid else None,
            })
        watch_ctx = [{"event_id": e["event_id"], "event_type": e["event_type"],
                      "country": cname(e), "aircraft": tname(e), "summary": e["summary"]}
                     for e in watchlist[:12]]
        type_counts = {k: len(v) for k, v in by_type.items()}
        region_ctx = {reg: {"count": len(evs),
                            "countries": sorted({cname(e) for e in evs})[:8],
                            "types": sorted({tname(e) for e in evs})[:8]}
                      for reg, evs in by_region.items()}

        prompt = (
            "You are a senior military-aviation analyst writing the weekly fleet report. "
            "Based ONLY on the data below, return STRICT JSON (no fences):\n"
            "{\n"
            ' "overview": "<5-8 sentence paragraph: what happened this week, explicit comparison '
            "vs previous week and vs the 4-week average, and any observable trend (regions, "
            'aircraft categories, buyer patterns). Sober, factual, analyst tone.>",\n'
            ' "deal_comments": {"<event_id>": "<ONE sentence: what this deal means for that '
            "country's air force — fleet growth %, replacement, new capability, does it fit "
            'their pattern; use the existing_active/existing_on_order numbers>", ...},\n'
            ' "type_notes": {"<event_type>": "<1-2 sentences explaining what is behind this '
            'slice this week, naming the main countries/regions involved>", ...},\n'
            ' "watchlist_assessment": {"near_term": "<2-3 sentences: which pending deals could '
            'be signed soon and what to watch>", "long_term": "<2-3 sentences: slower-moving '
            'processes and their strategic significance>"}\n'
            "}\n\n"
            "DATA:\nstats: {}\n\nkey_deals: {}\n\nevent_type_counts: {}\n\n"
            "regions: {}\n\nwatchlist: {}"
        ).format(json.dumps(stats), json.dumps(deal_ctx), json.dumps(type_counts),
                 json.dumps(region_ctx), json.dumps(watch_ctx))

        client = anthropic.Anthropic()
        msg = client.messages.create(model=MODEL, max_tokens=2500,
                                     messages=[{"role": "user", "content": prompt}])
        raw = "".join(b.text for b in msg.content if b.type == "text").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[4:] if raw.startswith("json") else raw
        ai = json.loads(raw.strip())

        # ---------- assemble payload ----------
        def event_view(e, comment=None):
            art = articles.get(e.get("article_id") or "")
            return {
                "event_id": e["event_id"], "event_type": e["event_type"],
                "country_id": e.get("country_id"), "country": cname(e),
                "type_id": e.get("type_id"), "aircraft": tname(e),
                "quantity": e.get("quantity"), "value_usd_m": e.get("value_usd_m"),
                "summary": e["summary"], "pending": e.get("review_status") == "pending",
                "article_title": art.get("title") if art else None,
                "article_url": art.get("url") if art else None,
                "analyst_comment": comment,
            }

        payload = {
            "stats": stats,
            "overview": ai.get("overview", ""),
            "key_deals": [event_view(e, (ai.get("deal_comments") or {}).get(str(e["event_id"])))
                          for e in key_deals],
            "by_type": [{"event_type": k, "count": len(v),
                         "note": (ai.get("type_notes") or {}).get(k)}
                        for k, v in sorted(by_type.items(), key=lambda kv: -len(kv[1]))],
            "by_region": [{"region": reg, "count": ctx["count"], "countries": ctx["countries"]}
                          for reg, ctx in sorted(region_ctx.items(), key=lambda kv: -kv[1]["count"])],
            "watchlist": {
                "items": [event_view(e) for e in watchlist],
                "assessment": ai.get("watchlist_assessment") or {},
            },
        }

        week_label = "{}-W{:02d}".format(now.isocalendar()[0], now.isocalendar()[1])
        db.upsert("ac_reports", [{
            "week_label": week_label,
            "period_start": wk_start.strftime("%Y-%m-%d"),
            "period_end": now.strftime("%Y-%m-%d"),
            "payload": payload,
        }], "week_label")
        print("Report {} saved ({} events, {} key deals).".format(
            week_label, len(this_week), len(key_deals)))
        db.finish_run(run, "success", items_processed=len(this_week))
    except Exception as e:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
