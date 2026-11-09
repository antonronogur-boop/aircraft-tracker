# -*- coding: utf-8 -*-
"""Collect aircraft-related articles from RSS sources into ac_articles.

Relevance pre-filter: an item is kept if it mentions any catalogue aircraft
name/alias OR a generic procurement keyword. Everything else is skipped
before it ever reaches the (paid) AI processing step.

Dedupe: article_id = 'rss-' + sha256(url)[:16]; DB-side on_conflict ignore.

Deps: pip install feedparser
Env:  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import hashlib
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

MAX_PER_FEED = 30
POLITENESS_DELAY_S = 2
# Egy forras SOHA nem allithatja meg a gyujtest: minden feed sajat
# idokorlattal (FETCH_TIMEOUT_S) es sajat hibakezelessel fut; a hibas feed
# kimarad, a tobbi vegigmegy, es a futas naploja forrasonkent rogziti az
# eredmenyt (pipeline_runs.details.sources). Bongeszo-szeru User-Agent: tobb
# vedett oldal (pl. Cloudflare) a "feedparser/x.y" ugynokot elutasitja.
FETCH_TIMEOUT_S = 25
FETCH_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SUMMARY_MAX_CHARS = 2000

# Generic keywords that signal a procurement / fleet event even when the
# exact type name is missing from the headline.
GENERIC_KEYWORDS = [
    "fighter jet", "fighter aircraft", "combat aircraft", "military aircraft",
    "air force", "procurement", "arms deal", "foreign military sale", "fms",
    "aircraft order", "aircraft delivery", "squadron", "helicopter", "airlifter",
    "tanker aircraft", "trainer aircraft", "retire", "phase out", "fleet",
    "arms sale", "defense contract", "defence contract", "awacs", "aew&c",
]


def sha16(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_keyword_index():
    """Catalogue names + aliases, lowercased, for the relevance filter."""
    types = db.select("ac_aircraft_types", {"select": "type_id,name,designation,aliases"})
    keywords = set()
    for t in types:
        for value in [t.get("name"), t.get("designation")] + list(t.get("aliases") or []):
            if value and len(value) >= 3:
                keywords.add(value.lower())
    return keywords


def is_relevant(title, summary, type_keywords):
    text = " ".join([title or "", summary or ""]).lower()
    if any(kw in text for kw in type_keywords):
        return True
    return any(kw in text for kw in GENERIC_KEYWORDS)


def article_row(entry, source):
    # type: (Any, Dict[str, Any]) -> Dict[str, Any]
    url = entry.get("link") or ""
    publish_date = None
    if getattr(entry, "published_parsed", None):
        publish_date = time.strftime("%Y-%m-%d", entry.published_parsed)
    raw_summary = (entry.get("summary") or entry.get("description") or "").strip()
    if "<" in raw_summary:
        raw_summary = re.sub(r"<[^>]+>", " ", raw_summary)
        raw_summary = re.sub(r"\s+", " ", raw_summary).strip()
    return {
        "article_id": "rss-" + sha16(url),
        "source_id": source["source_id"],
        "title": (entry.get("title") or "").strip()[:500],
        "url": url,
        "publish_date": publish_date,
        "collected_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "short_summary": raw_summary[:SUMMARY_MAX_CHARS] or None,
        "dedupe_hash": sha16(url),
        "status": "raw",
    }


def fetch_feed(url):
    """A feed letoltese sajat idokorlattal, bongeszo-szeru fejlecekkel.
    Hiba eseten kivetelt dob (a hivo forrasonkent kezeli)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": FETCH_UA,
        "Accept": "application/rss+xml, application/atom+xml, "
                  "application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as r:  # noqa: S310
        body = r.read(5_000_000)
    feed = feedparser.parse(body)
    if not feed.entries and (getattr(feed, "bozo", False)
                             or not getattr(feed, "version", "")):
        raise ValueError("not a valid RSS/Atom feed (0 entries)")
    return feed


def collect_source(source, type_keywords):
    """Egy forras teljes feldolgozasa. Visszaad: (bekuldott sorok, kihagyott
    irrelevans, statusz-dict). Kivetelt NEM dob tovabb."""
    st = {"ok": False, "entries": 0, "submitted": 0}
    try:
        feed = fetch_feed(source["rss_url"])
        st["entries"] = len(feed.entries)
        rows, skipped = [], 0
        # Nem angol nyelvu (pl. szerb MoD, cirill) forrasnal az angol
        # kulcsszo-szuro mindent kidobna: ott a tobbnyelvu olcso
        # Haiku-kapu dont (config/source_policy.json -> haiku_gate).
        # Az eredeti nyelvu cim valtozatlanul kerul tarolasra.
        english = (source.get("language") or "en").lower().startswith("en")
        for entry in feed.entries[:MAX_PER_FEED]:
            if not entry.get("link"):
                continue
            title = entry.get("title") or ""
            summary = entry.get("summary") or entry.get("description") or ""
            if english and not is_relevant(title, summary, type_keywords):
                skipped += 1
                continue
            rows.append(article_row(entry, source))
        if rows:
            db.insert_ignore_duplicates("ac_articles", rows, "article_id")
        st.update(ok=True, submitted=len(rows))
        return len(rows), skipped, st
    except Exception as e:  # noqa: BLE001
        st["error"] = "{}: {}".format(type(e).__name__, str(e)[:160])
        return 0, 0, st


def main():
    run = db.start_run("ac_collect_rss")
    try:
        type_keywords = build_keyword_index()
        sources = db.select("ac_sources", {
            "select": "source_id,source_name,rss_url,language",
            "rss_url": "not.is.null", "enabled": "eq.true"})
        print("RSS sources: {}".format(len(sources)))

        total, skipped, per_source = 0, 0, {}
        for source in sources:
            n, sk, st = collect_source(source, type_keywords)
            total += n
            skipped += sk
            per_source[source["source_id"]] = st
            if not st["ok"]:
                print("  [FAIL] {} — {} (skipped; the other sources continue)"
                      .format(source["source_name"], st["error"]))
            elif n:
                print("  [OK] {} — {} relevant items".format(
                    source["source_name"], n))
            else:
                print("  [--] {} — nothing relevant ({} entries)".format(
                    source["source_name"], st["entries"]))
            time.sleep(POLITENESS_DELAY_S)

        failed = sorted(k for k, v in per_source.items() if not v["ok"])
        print("Done. Submitted: {} (irrelevant skipped: {}) · sources ok {} / "
              "failed {}{}".format(total, skipped, len(sources) - len(failed),
                                    len(failed),
                                    " ({})".format(", ".join(failed))
                                    if failed else ""))
        details = {"sources_checked": len(sources), "skipped_irrelevant": skipped,
                   "sources_failed": failed, "sources": per_source}
        if sources and len(failed) == len(sources):
            # Ha EGYETLEN forras sem mukodott, az rendszerhiba (halozat,
            # konfiguracio) — ezt hibakent jelezzuk.
            db.finish_run(run, "error", items_processed=0,
                          error_message="all {} sources failed".format(
                              len(sources)), details=details)
            raise SystemExit("All sources failed — see the log above.")
        db.finish_run(run, "success", items_processed=total, details=details)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
