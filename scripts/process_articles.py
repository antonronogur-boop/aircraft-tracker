# -*- coding: utf-8 -*-
"""Process raw ac_articles with Claude: extract structured fleet EVENTS.

For each status=raw article the model returns zero or more events
(order / delivery / upgrade / export_sale / selection / negotiation /
retirement / incident / other), each tied to a country and — where
possible — a catalogue aircraft type. Unmatched names land in
unresolved_type_name / unresolved_country_name for later review.

Includes transient-error retry (lesson learned from the drone pipeline's
241 api_error incident) and full error-message logging.

Deps: pip install anthropic feedparser
Env:  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, ANTHROPIC_API_KEY
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

MODEL = "claude-sonnet-4-6"
BATCH_LIMIT = 25
FULLTEXT_MAX_CHARS = 12000
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

PROMPT = """You are a military-aviation OSINT analyst. From the given article,
extract AIRCRAFT FLEET EVENTS: anything a country does with a military
aircraft type — ordering, receiving, upgrading, selling, selecting,
negotiating, retiring, or losing aircraft.

Return STRICT JSON only (no markdown fences), with this shape:
{
  "relevant": true|false,        // false if the article contains no such event
  "events": [
    {
      "event_type": "order|delivery|upgrade|export_sale|selection|negotiation|retirement|incident|other",
      "country": "<country the fleet belongs to / buyer>",
      "counterparty_country": "<seller or other party, or null>",
      "aircraft_type": "<aircraft name as close to official as possible>",
      "quantity": <int or null>,
      "value_usd_m": <deal value in MILLIONS of USD, or null>,
      "value_type": "firm|ceiling|notified_max|estimate|unknown",
      "value_currency_year": <year the figure is quoted in, or null>,
      "event_date": "YYYY-MM-DD or null — WHEN IT HAPPENED, not when reported",
      "announcement_date": "YYYY-MM-DD or null — when it was made public",
      "lifecycle_stage": "requirement|rfi_sources_sought|rfp|bid|selection|national_approval|export_approval|contract_signed|production|delivery|ioc|foc|upgrade_programme|retirement|loss|other",
      "capability_domain": "fighter_strike|air_mobility_rotary|air_mobility_fixed|uncrewed_cca|counter_uas|isr_aew_sigint|tanker|training|attack_helicopter|maritime_patrol|other",
      "delivery_start_year": <int or null>,
      "delivery_end_year": <int or null>,
      "expected_ioc_year": <int or null — when the capability becomes usable>,
      "independent_lineages": <1 normally; >1 only if genuinely separate evidence chains>,
      "summary": "<1-2 sentence plain-English summary of the event>",
      "confidence": <0.0-1.0, how certain the article is (rumor=low, signed contract=high)>
    }
  ]
}

Rules:
- EVENT DATE DISCIPLINE — the single most important rule. "event_date" is the
  date the procurement action itself took place. If a 2026 article describes a
  contract signed in January 2020 or a budget approval given in 2025, the
  event_date is 2020-01 / 2025 — NOT today. A fresh article never makes an old
  event current. If the article gives only a month or year, use the first day
  of it. Put the publication date in announcement_date.
- LIFECYCLE STAGE IS NOT EVENT TYPE. Distinguish precisely:
  * requirement / rfi_sources_sought / rfp / bid — pre-competition steps
  * selection — type chosen, nothing signed
  * national_approval — parliament/cabinet/budget-committee authorisation
    (e.g. the German Bundestag budget committee releasing funds)
  * export_approval — US DSCA/State Department clearance or a congressional
    review passing. THIS IS NOT A PURCHASE: it is permission to sell, with a
    notional MAXIMUM value that regularly exceeds the eventual contract.
  * contract_signed — a signed, funded procurement contract
  * production / delivery / ioc / foc — execution and fielding
  If the article says "approved", decide WHO approved WHAT: a buyer's budget
  authority (national_approval) or an exporter's government (export_approval).
- VALUE TYPE: "up to $X" or IDIQ ceilings are "ceiling"; DSCA notification
  totals are "notified_max"; a signed contract sum is "firm"; press estimates
  are "estimate". Give value_currency_year when the figure is historical.
- CAPABILITY EFFECT DATES: where stated, give delivery_start_year,
  delivery_end_year and expected_ioc_year. Never invent them; null is correct
  when the article is silent. Do not infer IOC from the contract date.
- INDEPENDENT LINEAGES: several outlets repeating one manufacturer press
  release or one ministry statement is ONE lineage. Only count a second
  lineage for genuinely separate evidence (a second government, a contract
  document, imagery).
- Only MILITARY aircraft (incl. large military UAVs). Ignore airlines/civil.
- ONLY events that change (or will change) a country's FLEET. Explicitly
  DO NOT create events for: deployments, exercises, training missions,
  airshows/flypasts, operational strikes or combat usage, routine test
  flights, personnel/commander news, weapons integration tests without a
  procurement decision, opinion/analysis pieces. If the article contains
  only such content, return {"relevant": false}.
- "incident" = only an actual loss/destruction of an aircraft (crash,
  shoot-down) that reduces a fleet — not near-misses or disciplinary news.
- One event per (country, type, event_type) — merge duplicates.
- "order" = signed contract; "selection" = type chosen but not yet signed;
  "negotiation" = talks/requests/approvals (incl. US DSCA approvals);
  "export_sale" = a country selling its own aircraft onward.
  (event_type stays coarse for continuity; lifecycle_stage carries the
  precision. An FMS/DSCA clearance is event_type "negotiation" and
  lifecycle_stage "export_approval" — never event_type "order".)
- AIRCRAFT COUNT IS NOT COMBAT CAPABILITY. The summary states the procurement
  fact. Do not assert readiness, force-structure superiority, supplier
  dominance or regional balance conclusions — those need pilot readiness,
  weapons stocks, mission data, tanker and basing information the article
  does not contain.
- "upgrade" = a decided/contracted modernization programme for a fleet.
- Do not invent numbers. If the article gives no quantity/value, use null.
- Prefer FEWER, stronger events over many weak ones (max 3 per article
  unless it is genuinely a multi-country deal roundup).
- summary must state WHO does WHAT with WHICH aircraft (and how many)."""


def fetch_fulltext(url):
    # type: (str) -> Optional[str]
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    html = re.sub(r"(?is)<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:FULLTEXT_MAX_CHARS] if len(text) > 300 else None


def build_indexes():
    """Alias -> id lookup tables for countries and aircraft types."""
    type_idx, country_idx = {}, {}
    for t in db.select("ac_aircraft_types", {"select": "type_id,name,designation,aliases"}):
        # type_id itself is the most important alias: 'f-35', 'gripen', 'fcas'
        for v in [t["type_id"], t.get("name"), t.get("designation")] + list(t.get("aliases") or []):
            if v:
                type_idx[str(v).lower()] = t["type_id"]
    for c in db.select("ac_countries", {"select": "country_id,name,aliases"}):
        for v in [c.get("name")] + list(c.get("aliases") or []):
            if v:
                country_idx[v.lower()] = c["country_id"]
    return type_idx, country_idx


def match(value, index):
    # type: (Optional[str], Dict[str, str]) -> Optional[str]
    if not value:
        return None
    v = value.strip().lower()
    if v in index:
        return index[v]
    # Substring fallback: 'F-16C Block 70 jets' -> 'f-16'
    for alias, ident in sorted(index.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 4 and alias in v:
            return ident
    return None


def call_claude(client, article):
    # type: (anthropic.Anthropic, Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]
    body = fetch_fulltext(article.get("url", "")) or article.get("short_summary") \
        or article.get("title", "")
    if not body:
        return None, "no_content"
    content = "TITLE: {}\nURL: {}\nARTICLE TEXT:\n{}".format(
        article.get("title", ""), article.get("url", ""), body)

    last_err = None
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=3000, system=PROMPT,
                messages=[{"role": "user", "content": content}])
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            err_name = type(e).__name__
            print("  [WARN] Anthropic API error ({}/3): {}: {}".format(
                attempt + 1, err_name, str(e)[:300]))
            transient = err_name in ("RateLimitError", "InternalServerError",
                                     "OverloadedError", "APIConnectionError",
                                     "APITimeoutError", "APIStatusError")
            if not transient or attempt == 2:
                return None, "api_error"
            time.sleep(20 * (attempt + 1))
    else:
        print("  [WARN] API error (final): {}".format(last_err))
        return None, "api_error"

    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    if not raw:
        return None, "empty_response"
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, "json_parse_error"


LIFECYCLE_STAGES = {
    "requirement", "rfi_sources_sought", "rfp", "bid", "selection",
    "national_approval", "export_approval", "contract_signed", "production",
    "delivery", "ioc", "foc", "upgrade_programme", "retirement", "loss",
    "other"}
VALUE_TYPES = {"firm", "ceiling", "notified_max", "estimate", "unknown"}
CAPABILITY_DOMAINS = {
    "fighter_strike", "air_mobility_rotary", "air_mobility_fixed",
    "uncrewed_cca", "counter_uas", "isr_aew_sigint", "tanker", "training",
    "attack_helicopter", "maritime_patrol", "other"}
# event_type -> lifecycle_stage fallback, ha a modell nem ad ervenyeset
STAGE_FALLBACK = {"order": "contract_signed", "delivery": "delivery",
                  "upgrade": "upgrade_programme", "selection": "selection",
                  "negotiation": "requirement", "retirement": "retirement",
                  "incident": "loss", "export_sale": "contract_signed"}


def _year(value, lo=1990, hi=2060):
    try:
        y = int(value)
    except (TypeError, ValueError):
        return None
    return y if lo <= y <= hi else None


def _v2_fields(ev):
    """A kepesseg-mezok validalasa. Ervenytelen erteket sosem irunk be:
    inkabb null, mint egy kitalalt kategoria, amire kesobb elemzes epul."""
    stage = str(ev.get("lifecycle_stage") or "").strip().lower()
    if stage not in LIFECYCLE_STAGES:
        stage = STAGE_FALLBACK.get(ev.get("event_type") or "", "other")
    vtype = str(ev.get("value_type") or "").strip().lower()
    if vtype not in VALUE_TYPES:
        vtype = "unknown" if ev.get("value_usd_m") is not None else None
    dom = str(ev.get("capability_domain") or "").strip().lower()
    if dom not in CAPABILITY_DOMAINS:
        dom = None
    try:
        lineages = max(1, min(int(ev.get("independent_lineages") or 1), 6))
    except (TypeError, ValueError):
        lineages = 1
    out = {"lifecycle_stage": stage, "value_type": vtype,
           "capability_domain": dom, "independent_lineages": lineages,
           "value_currency_year": _year(ev.get("value_currency_year")),
           "delivery_start_year": _year(ev.get("delivery_start_year")),
           "delivery_end_year": _year(ev.get("delivery_end_year")),
           "expected_ioc_year": _year(ev.get("expected_ioc_year"))}
    ann = str(ev.get("announcement_date") or "")[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", ann):
        out["announcement_date"] = ann
    return out


def load_recent_soft_keys():
    """(country_id, type_id, event_type) of non-rejected soft events from the
    last 30 days — used to skip duplicate negotiation/selection/other events
    when multiple outlets cover the same story."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = db.select("ac_events", {
        "select": "country_id,type_id,event_type",
        "review_status": "neq.rejected",
        "event_type": "in.(negotiation,selection,other)",
        "created_at": "gte.{}".format(cutoff)})
    return {(r.get("country_id"), r.get("type_id"), r["event_type"]) for r in rows}


def main():
    run = db.start_run("ac_process_articles")
    processed = 0
    try:
        client = anthropic.Anthropic()
        type_idx, country_idx = build_indexes()
        soft_keys = load_recent_soft_keys()
        articles = db.select("ac_articles", {
            "select": "article_id,title,url,short_summary",
            "status": "eq.raw", "order": "collected_date.asc",
            "limit": str(BATCH_LIMIT)})
        print("Raw articles to process: {}".format(len(articles)))

        for art in articles:
            print("- {}".format((art.get("title") or "?")[:80]))
            result, failure = call_claude(client, art)
            if failure:
                db.update("ac_articles", {"article_id": "eq." + art["article_id"]},
                          {"status": "failed", "failure_reason": failure})
                continue

            if not result.get("relevant") or not result.get("events"):
                db.update("ac_articles", {"article_id": "eq." + art["article_id"]},
                          {"status": "irrelevant"})
                processed += 1
                continue

            for ev in result["events"]:
                type_id = match(ev.get("aircraft_type"), type_idx)
                country_id = match(ev.get("country"), country_idx)
                counterparty_id = match(ev.get("counterparty_country"), country_idx)
                etype = ev.get("event_type") or "other"
                # duplicate guard: same soft story already tracked -> skip
                if etype in ("negotiation", "selection", "other") \
                        and (country_id or type_id) \
                        and (country_id, type_id, etype) in soft_keys:
                    print("  [dup] skipped: {} / {} / {}".format(
                        ev.get("country"), ev.get("aircraft_type"), etype))
                    continue
                if etype in ("negotiation", "selection", "other"):
                    soft_keys.add((country_id, type_id, etype))
                row = {
                    "article_id": art["article_id"],
                    "event_type": etype,
                    "country_id": country_id,
                    "type_id": type_id,
                    "counterparty_country_id": counterparty_id,
                    "quantity": ev.get("quantity"),
                    "value_usd_m": ev.get("value_usd_m"),
                    "event_date": ev.get("event_date"),
                    "summary": (ev.get("summary") or "")[:1000],
                    "confidence": ev.get("confidence"),
                    "review_status": "pending",
                    "unresolved_type_name": None if type_id else ev.get("aircraft_type"),
                    "unresolved_country_name": None if country_id else ev.get("country"),
                }
                # v2 kepesseg-mezok, ervenyes ertekkeszletre szoritva. Ha a
                # migracio meg nem futott le, a beszuras a v2 kulcsok nelkul
                # ismetlodik (visszafele kompatibilitas).
                v2 = _v2_fields(ev)
                try:
                    db.insert("ac_events", dict(row, **v2))
                except Exception as e:  # noqa: BLE001
                    try:
                        db.insert("ac_events", row)
                        print("  [warn] v2 columns missing — inserted without "
                              "capability fields (run add_capability_fields.sql)")
                    except Exception as e2:  # noqa: BLE001
                        print("  [WARN] event insert failed: {}".format(str(e2)[:200]))

            db.update("ac_articles", {"article_id": "eq." + art["article_id"]},
                      {"status": "processed"})
            processed += 1
            print("  -> {} event(s)".format(len(result["events"])))

        print("Done. Processed: {}/{}".format(processed, len(articles)))
        db.finish_run(run, "success", items_processed=processed)
    except Exception as e:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
