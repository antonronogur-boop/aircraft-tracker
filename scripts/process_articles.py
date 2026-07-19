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
      "event_date": "YYYY-MM-DD or null",
      "summary": "<1-2 sentence plain-English summary of the event>",
      "confidence": <0.0-1.0, how certain the article is (rumor=low, signed contract=high)>
    }
  ]
}

Rules:
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
        for v in [t.get("name"), t.get("designation")] + list(t.get("aliases") or []):
            if v:
                type_idx[v.lower()] = t["type_id"]
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


def main():
    run = db.start_run("ac_process_articles")
    processed = 0
    try:
        client = anthropic.Anthropic()
        type_idx, country_idx = build_indexes()
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
                row = {
                    "article_id": art["article_id"],
                    "event_type": ev.get("event_type") or "other",
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
                try:
                    db.insert("ac_events", row)
                except Exception as e:  # noqa: BLE001
                    print("  [WARN] event insert failed: {}".format(str(e)[:200]))

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
