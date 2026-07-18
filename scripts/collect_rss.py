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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import feedparser

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

MAX_PER_FEED = 30
POLITENESS_DELAY_S = 2
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


def main():
    run = db.start_run("ac_collect_rss")
    try:
        type_keywords = build_keyword_index()
        sources = db.select("ac_sources", {
            "select": "source_id,source_name,rss_url",
            "rss_url": "not.is.null", "enabled": "eq.true"})
        print("RSS sources: {}".format(len(sources)))

        total, skipped = 0, 0
        for source in sources:
            try:
                feed = feedparser.parse(source["rss_url"])
            except Exception as e:  # noqa: BLE001
                print("  [SKIP] {} — feed error: {}".format(source["source_name"], e))
                continue

            rows = []  # type: List[Dict[str, Any]]
            for entry in feed.entries[:MAX_PER_FEED]:
                if not entry.get("link"):
                    continue
                title = entry.get("title") or ""
                summary = entry.get("summary") or entry.get("description") or ""
                if not is_relevant(title, summary, type_keywords):
                    skipped += 1
                    continue
                rows.append(article_row(entry, source))

            if rows:
                db.insert_ignore_duplicates("ac_articles", rows, "article_id")
                total += len(rows)
                print("  [OK] {} — {} relevant items".format(source["source_name"], len(rows)))
            else:
                print("  [--] {} — nothing relevant".format(source["source_name"]))
            time.sleep(POLITENESS_DELAY_S)

        print("Done. Submitted: {} (irrelevant skipped: {})".format(total, skipped))
        db.finish_run(run, "success", items_processed=total,
                      details={"sources_checked": len(sources), "skipped_irrelevant": skipped})
    except Exception as e:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
