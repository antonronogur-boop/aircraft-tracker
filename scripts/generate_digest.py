# -*- coding: utf-8 -*-
"""Weekly digest — compact summary of the last 7 days of fleet events,
sent to Telegram (if configured) and always printed to stdout.

Env:
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   (required)
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID      (optional — enables Telegram push)

Telegram setup (one-time):
    1. In Telegram, talk to @BotFather -> /newbot -> get the bot token.
    2. Send any message to your new bot, then open
       https://api.telegram.org/bot<TOKEN>/getUpdates and read "chat":{"id":...}
    3. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as GitHub repo secrets.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

EVENT_LABEL = {
    "order": "🟢 Order", "delivery": "🔵 Delivery", "upgrade": "🟣 Upgrade",
    "export_sale": "🟠 Export sale", "selection": "🟢 Selection",
    "negotiation": "🟡 Negotiation", "retirement": "🔴 Retirement",
    "incident": "❌ Incident", "other": "⚪ Other",
}


def build_digest():
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=7)).isoformat()

    events = db.select("ac_events", {
        "select": "*", "created_at": "gte.{}".format(cutoff),
        "review_status": "neq.rejected", "order": "created_at.desc"})
    countries = {c["country_id"]: c["name"]
                 for c in db.select("ac_countries", {"select": "country_id,name"})}
    types = {t["type_id"]: t["name"]
             for t in db.select("ac_aircraft_types", {"select": "type_id,name"})}

    hard = [e for e in events if e["event_type"] in ("order", "delivery", "export_sale")]
    total_value = sum(float(e.get("value_usd_m") or 0) for e in events)
    total_aircraft = sum(int(e.get("quantity") or 0) for e in hard)
    watch = [e for e in events if e["event_type"] in ("negotiation", "selection")]

    def name(e):
        c = countries.get(e.get("country_id") or "", e.get("unresolved_country_name") or "?")
        t = types.get(e.get("type_id") or "", e.get("unresolved_type_name") or "?")
        return c, t

    lines = []
    lines.append("✈️ <b>AIRCRAFT TRACKER — weekly digest</b>")
    lines.append("{} → {}".format((now - timedelta(days=7)).strftime("%b %d"), now.strftime("%b %d")))
    lines.append("")
    lines.append("<b>{} events</b> · {} firm deals · {} aircraft{}".format(
        len(events), len(hard), total_aircraft,
        " · ${:,.0f}M disclosed".format(total_value) if total_value else ""))

    key = sorted(hard, key=lambda e: (-(float(e.get("value_usd_m") or 0)),
                                      -(int(e.get("quantity") or 0))))[:6]
    if key:
        lines.append("")
        lines.append("<b>Key deals</b>")
        for e in key:
            c, t = name(e)
            qty = " ×{}".format(e["quantity"]) if e.get("quantity") else ""
            val = " (${:,.0f}M)".format(float(e["value_usd_m"])) if e.get("value_usd_m") else ""
            lines.append("• {} — {}: {}{}{}".format(
                EVENT_LABEL.get(e["event_type"], e["event_type"]), c, t, qty, val))

    if watch:
        lines.append("")
        lines.append("<b>Watchlist</b> (not signed yet)")
        for e in watch[:6]:
            c, t = name(e)
            lines.append("• {} — {} / {}".format(
                EVENT_LABEL.get(e["event_type"], e["event_type"]), c, t))

    pending = sum(1 for e in events if e.get("review_status") == "pending")
    if pending:
        lines.append("")
        lines.append("⏳ {} events awaiting review".format(pending))
    lines.append("")
    lines.append("Full report: your site /weekly")
    return "\n".join(lines)


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("\n[info] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping Telegram push.")
        return
    payload = json.dumps({
        "chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot{}/sendMessage".format(token),
        data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        ok = json.loads(resp.read().decode("utf-8")).get("ok")
        print("[info] Telegram push: {}".format("sent" if ok else "FAILED"))


def main():
    run = db.start_run("ac_weekly_digest")
    try:
        digest = build_digest()
        print(digest.replace("<b>", "").replace("</b>", ""))
        send_telegram(digest)
        db.finish_run(run, "success", items_processed=1)
    except Exception as e:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(e))
        raise


if __name__ == "__main__":
    main()
