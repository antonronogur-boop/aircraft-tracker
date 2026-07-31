# -*- coding: utf-8 -*-
"""Generate the weekly AIR POWER DEVELOPMENT INTELLIGENCE BRIEF -> ac_reports.

A korabbi valtozat procurement-trackert irt: eventszamot, deal-szamot, osszesitett
darabszamot es egyetlen "disclosed value" osszeget. Ez piaci elemzonek jo, egy
legieros felderito sejtnek keves — es hibas is volt, mert a heti tagsagot a
gyujtes ideje dontotte el, igy egy 2020-as lengyel F-35-szerzodes lett "a het
masodik legnagyobb uzlete".

Ez a valtozat:
  * az EVENT_DATE alapjan valogat, es kizarja a periodus utani datumokat;
  * kulon szamolja az observationt es az egyedi esemenyt, es jelzi, ha a
    volumen nem osszehasonlithato;
  * ertektipusonkent osszegez (firm / ceiling / DSCA-max kulon), arfolyam-evvel;
  * darabszamot kepesseg-domainenkent bont (F-35 es motoros siklóernyo nem
    egy KPI);
  * a fo terméket a KEPESSEG-VALTOZAS koré epiti: developments -> key
    judgements -> priority watch -> capability arrival timeline;
  * ORBAT-deltat ad orszagonkent a flotta-baseline-bol;
  * automatikus analitikai QA-t futtat, atirat, es visszatartja azt az
    iteletet, ami az atiras utan sem all meg.

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
import ac_intel  # noqa: E402

DAY = timedelta(days=1)


def load_events(since_iso):
    """Szeles betoltes a gyujtes ideje szerint; az idobeli besorolast utana az
    event_date vegzi (a friss cikk nem tesz egy regi esemenyt hetive)."""
    return db.select("ac_events", {
        "select": "*", "review_status": "neq.rejected",
        "created_at": "gte." + since_iso, "order": "created_at.desc"})


def main():
    run = db.start_run("ac_weekly_report")
    try:
        now = datetime.now(timezone.utc)
        naive_now = now.replace(tzinfo=None)
        wk_start = naive_now - 7 * DAY
        trend_start = naive_now - 35 * DAY

        # A gyujtesi ablak szelesebb (60 nap), mert egy most beerkezett cikk
        # regebbi esemenyrol is szolhat — azt viszont NEM e hetinek soroljuk be.
        raw = load_events((now - 60 * DAY).isoformat())

        countries = {c["country_id"]: c for c in db.select(
            "ac_countries", {"select": "country_id,name,region"})}
        types = {t["type_id"]: t for t in db.select(
            "ac_aircraft_types", {"select": "type_id,name,category"})}
        articles = {a["article_id"]: a for a in db.select(
            "ac_articles", {"select": "article_id,title,url"})}
        fleets = db.select("ac_fleets", {
            "select": "country_id,type_id,fleet_status,quantity"})

        def day(e):
            return ac_intel.effective_day(e)

        this_week, prev_week, prev_4wk, future_dated, undated = [], [], [], [], []
        for e in raw:
            d = day(e)
            if d is None:
                undated.append(e)
                continue
            if d > naive_now:
                future_dated.append(e)
            elif d >= wk_start:
                this_week.append(e)
            elif d >= trend_start:
                prev_4wk.append(e)
                if d >= naive_now - 14 * DAY:
                    prev_week.append(e)

        if future_dated:
            print("  Excluded {} event(s) dated beyond the period end.".format(
                len(future_dated)))
        # Datum nelkuli esemeny: a gyujtes napja szerint kerulhet be, de
        # jeloljuk — a temporal integritas resze, hogy ez latszik.
        for e in undated:
            d = ac_intel.parse_day(e.get("created_at"))
            if d and d >= wk_start:
                e["_undated"] = True
                this_week.append(e)
        if undated:
            print("  {} event(s) without an event_date (dated by collection "
                  "time).".format(sum(1 for e in this_week if e.get("_undated"))))

        # ---------------- kemény statisztika ----------------
        prev_n, prev_avg = len(prev_week), len(prev_4wk) / 4.0
        volume_not_comparable = bool(
            (prev_n < 8 and len(this_week) > 3 * max(prev_n, 1))
            or (prev_avg >= 1 and len(this_week) > 2.5 * prev_avg)
            or (len(this_week) >= 1 and prev_avg > 2.5 * len(this_week)))

        # Szerzodesnek MINOSULO stadiumok — csak ezekre mondjuk, hogy "firm".
        firm_stages = {"contract_signed", "production", "delivery", "ioc",
                       "foc"}
        firm = [e for e in this_week if ac_intel.stage_of(e) in firm_stages]

        by_stage, by_domain, by_region = {}, {}, {}
        for e in this_week:
            by_stage[ac_intel.stage_of(e)] = by_stage.get(
                ac_intel.stage_of(e), 0) + 1
            dm = ac_intel.domain_of(e, types)
            by_domain[dm] = by_domain.get(dm, 0) + 1
            reg = (countries.get(e.get("country_id") or "") or {}).get("region")
            if reg:
                by_region.setdefault(reg, []).append(e)

        stats = {
            "events_this_week": len(this_week),
            "events_prev_week": prev_n,
            "events_prev_4wk_weekly_avg": round(prev_avg, 1),
            "volume_not_comparable": volume_not_comparable,
            "firm_procurement_actions": len(firm),
            "value": ac_intel.value_breakdown(this_week),
            "airframes_by_domain": ac_intel.platform_breakdown(this_week, types),
            "by_lifecycle_stage": by_stage,
            "by_capability_domain": by_domain,
            "by_region": {r: len(v) for r, v in by_region.items()},
            "collection_health": {
                "unique_events": len(this_week),
                "events_missing_event_date": sum(
                    1 for e in this_week if e.get("_undated")),
                "future_dated_excluded": len(future_dated),
                "pending_review": sum(
                    1 for e in this_week
                    if e.get("review_status") == "pending"),
                "wow_comparable": not volume_not_comparable,
            },
        }

        client = anthropic.Anthropic()
        week_label = "{}-W{:02d}".format(*now.isocalendar()[:2])

        # ---------------- elemzoi retegek ----------------
        developments, background = [], []
        judgements, self_checks = None, []
        try:
            developments, background = ac_intel.build_developments(
                client, this_week, types, countries, fleets)
            if developments:
                judgements = ac_intel.build_judgements(
                    client, developments, stats)
            self_checks = ac_intel.run_self_checks(
                developments, judgements, wk_start, naive_now, stats,
                events=this_week)
            if self_checks:
                applied = ac_intel.qa_language_gate(
                    client, developments, judgements, self_checks)
                if applied:
                    print("  QA gate: {} field(s) rewritten, re-checking".format(
                        applied))
                    rechecked = ac_intel.run_self_checks(
                        developments, judgements, wk_start, naive_now, stats,
                        events=this_week)
                    self_checks = ac_intel.mark_unresolved(
                        self_checks, rechecked)
            gated = ac_intel.gate_key_judgements(judgements, self_checks)
            if gated:
                print("  KJ gate: {} judgement(s) withheld for analyst "
                      "review: {}".format(len(gated),
                                          ", ".join(str(g.get("id"))
                                                    for g in gated)))
            if self_checks:
                print("  self-checks raised {} issue(s):".format(
                    len(self_checks)))
                for c in self_checks[:8]:
                    print("    - {}: {}".format(c["check"], c["item"]))
        except Exception as exc:  # noqa: BLE001
            print("  [warn] intelligence layer unavailable ({}: {})".format(
                type(exc).__name__, str(exc)[:200]))

        # ---------------- szarmaztatott nezetek ----------------
        dev_event_ids = {i for d in developments
                         for i in (d.get("event_ids") or [])}
        dev_events = [e for e in this_week
                      if e.get("event_id") in dev_event_ids] or this_week
        orbat = ac_intel.orbat_delta(dev_events, fleets, types, countries)
        timeline = ac_intel.capability_timeline(this_week, types, countries)
        matrix = ac_intel.maturity_matrix(developments)

        def event_view(e):
            art = articles.get(e.get("article_id") or "")
            c = countries.get(e.get("country_id") or "") or {}
            t = types.get(e.get("type_id") or "") or {}
            return {
                "event_id": e["event_id"], "event_type": e["event_type"],
                "lifecycle_stage": ac_intel.stage_of(e),
                "capability_domain": ac_intel.domain_of(e, types),
                "country": c.get("name") or e.get("unresolved_country_name"),
                "aircraft": t.get("name") or e.get("unresolved_type_name"),
                "quantity": e.get("quantity"),
                "value_usd_m": e.get("value_usd_m"),
                "value_type": e.get("value_type"),
                "event_date": e.get("event_date"),
                "expected_ioc_year": e.get("expected_ioc_year"),
                "summary": e["summary"],
                "undated": bool(e.get("_undated")),
                "pending": e.get("review_status") == "pending",
                "article_title": art.get("title") if art else None,
                "article_url": art.get("url") if art else None,
            }

        payload = {
            "schema": "air_power_v2",
            "report_meta": {
                "period_start": wk_start.strftime("%Y-%m-%d"),
                "period_end": naive_now.strftime("%Y-%m-%d"),
                "collection_cutoff_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
                "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
                "status": ("analyst review required" if self_checks
                           else "auto-generated, QA clean"),
                "version": "v2.0",
            },
            "stats": stats,
            "bottom_line": (judgements or {}).get("bottom_line") or "",
            "key_judgements": (judgements or {}).get("key_judgements") or [],
            "judgements_requiring_review": (judgements or {}).get(
                "judgements_requiring_review") or [],
            "developments": developments,
            "background_items": background,
            "priority_watch": (judgements or {}).get("priority_watch") or [],
            "intelligence_gaps": (judgements or {}).get(
                "intelligence_gaps") or [],
            "orbat_delta": orbat,
            "capability_timeline": timeline,
            "maturity_matrix": matrix,
            "self_checks": self_checks,
            "annex_events": [event_view(e) for e in sorted(
                this_week,
                key=lambda x: -(float(x.get("value_usd_m") or 0)))[:60]],
        }

        db.upsert("ac_reports", [{
            "week_label": week_label,
            "period_start": wk_start.strftime("%Y-%m-%d"),
            "period_end": naive_now.strftime("%Y-%m-%d"),
            "generated_at": now.isoformat(),
            "payload": payload,
        }], "week_label")
        print("Report {} saved ({} in-period events, {} development(s), "
              "{} judgement(s), {} self-check issue(s)).".format(
                  week_label, len(this_week), len(developments),
                  len(payload["key_judgements"]), len(self_checks)))
        db.finish_run(run, "success", items_processed=len(this_week))
    except Exception as e:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
