# -*- coding: utf-8 -*-
"""Aircraft Tracker pipeline health check.

Answers: is the GitHub Actions cron actually running (ac_collect_rss /
ac_process_articles in pipeline_runs), are articles flowing in, and is
anything silently piling up as raw/failed?

Usage (from Aircraft_Tracker/):
    python scripts\\check_health.py <SUPABASE_SERVICE_ROLE_KEY>
Exit code: 0 = OK, 1 = warning, 2 = error.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://uqjhgdclaagfkopdfjlq.supabase.co").rstrip("/")
MAX_HOURS_SINCE_RUN = 36


def fetch(key, table, params):
    url = "{}/rest/v1/{}?{}".format(SUPABASE_URL, table, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={
        "apikey": key, "Authorization": "Bearer {}".format(key)})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_ts(v):
    if not v:
        return None
    # Pre-3.11 fromisoformat chokes on non-3/6-digit fractional seconds —
    # strip the fraction entirely (second precision is plenty here).
    import re
    s = re.sub(r"\.\d+", "", str(v)).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def main():
    key = (sys.argv[1].strip() if len(sys.argv) > 1
           else os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip())
    if not key:
        print("Usage: python scripts\\check_health.py <SERVICE_ROLE_KEY>")
        return 2
    now = datetime.now(timezone.utc)
    problems = []

    runs = fetch(key, "pipeline_runs", {
        "select": "script_name,status,started_at,items_processed,error_message",
        "script_name": "in.(ac_collect_rss,ac_process_articles)",
        "order": "started_at.desc", "limit": "12"})
    print("=== AIRCRAFT TRACKER HEALTH — {} ===".format(now.strftime("%Y-%m-%d %H:%M UTC")))
    print("\n--- Last runs ---")
    for r in runs:
        ts = parse_ts(r.get("started_at"))
        age = (now - ts).total_seconds() / 3600 if ts else None
        print("  {:<20} {:<8} {:>5}  {:.1f}h ago".format(
            r["script_name"], r["status"],
            r.get("items_processed") if r.get("items_processed") is not None else "-",
            age if age is not None else -1))
        if r.get("status") == "error":
            print("      error: {}".format(str(r.get("error_message", ""))[:150]))
    if not runs:
        problems.append((2, "No ac_* pipeline runs logged at all — the aircraft-tracker-sync "
                            "GitHub Actions workflow has never run. Check the Actions tab + secrets."))
    else:
        ts = parse_ts(runs[0].get("started_at"))
        age = (now - ts).total_seconds() / 3600 if ts else 9999
        if age > MAX_HOURS_SINCE_RUN:
            problems.append((2, "Last run was {:.0f}h ago (threshold {}h) — cron likely dead.".format(
                age, MAX_HOURS_SINCE_RUN)))
        if runs[0].get("status") == "error":
            problems.append((2, "Most recent run ended in error — see above."))

    counts = {}
    offset = 0
    while True:
        page = fetch(key, "ac_articles", {"select": "status", "limit": "1000", "offset": str(offset)})
        for row in page:
            counts[row.get("status") or "?"] = counts.get(row.get("status") or "?", 0) + 1
        if len(page) < 1000:
            break
        offset += 1000
    print("\n--- Articles by status ---")
    for s, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  {:<12} {}".format(s, n))
    if counts.get("raw", 0) > 60:
        problems.append((1, "{} articles stuck in raw — processing not keeping up.".format(counts["raw"])))
    if counts.get("failed", 0) > 30:
        problems.append((1, "{} failed articles — check failure_reason (API credit? key?).".format(
            counts["failed"])))

    cutoff = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    recent = fetch(key, "ac_articles", {"select": "article_id",
                                        "collected_date": "gte.{}".format(cutoff), "limit": "500"})
    print("\n  Articles collected in last 3 days: {}".format(len(recent)))
    if not recent:
        problems.append((1, "No new articles in 3 days."))

    print("\n=== VERDICT: {} ===".format(
        "OK" if not problems else ("ERROR" if max(p[0] for p in problems) == 2 else "WARNING")))
    for lvl, msg in problems:
        print("  [{}] {}".format("ERR" if lvl == 2 else "WARN", msg))
    return max([p[0] for p in problems], default=0)


if __name__ == "__main__":
    sys.exit(main())
