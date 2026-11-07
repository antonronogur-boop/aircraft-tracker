# -*- coding: utf-8 -*-
"""Command Brief egy MAR PUBLIKALT heti jelentesbol — modell nelkul.

Ugyanaz a build_command_brief(), amit a szerdai generator hiv; itt a tarolt
ac_reports payloadbol fut. Nem general uj elemzest: a developments /
key_judgements / since_last_week valtozatlan, csak a brief (es a coverage
audit) epul fole.

Alapertelmezesben CSAK OLVAS az adatbazisbol, es fajlba ir:
  data/command_brief_<het>.json        — a brief
  data/command_brief_rows_<het>.json   — a teljes sor (a webes E2E-hez)

--write: a brief bekerul a tarolt jelentesbe — LATHATO restatementkent
         ("Command Brief added; analytical content unchanged"), mert egy
         publikalt jelentest csendben nem modositunk.
--synthesis: executive synthesis modellhivassal (ANTHROPIC_API_KEY kell);
         nelkule a bottom line determinisztikus.

Usage: python scripts/backfill_command_brief.py [--week 2026-W45|latest]
                                                [--write] [--synthesis]
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402
import ac_hungary  # noqa: E402
import ac_command_brief  # noqa: E402
import coverage_audit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    args = sys.argv[1:]
    week = args[args.index("--week") + 1] if "--week" in args else "latest"
    write = "--write" in args
    q = {"select": "*", "order": "period_end.desc", "limit": "1"}
    if week != "latest":
        q = {"select": "*", "week_label": "eq." + week, "limit": "1"}
    rows = db.select("ac_reports", q)
    if not rows:
        sys.exit("No report found for {}".format(week))
    row = rows[0]
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    week = row["week_label"]
    print("Report {} ({} -> {}), {} development(s), {} judgement(s)".format(
        week, row.get("period_start"), row.get("period_end"),
        len(payload.get("developments") or []),
        len(payload.get("key_judgements") or [])))

    countries = {c["country_id"]: c for c in db.select(
        "ac_countries", {"select": "country_id,name,region,aliases"})}
    end = datetime.fromisoformat(str(row.get("period_end"))[:10])
    since = (end - timedelta(days=95)).isoformat()
    events = db.select("ac_events", {
        "select": "event_id,country_id,article_id,event_date,"
                  "announcement_date,created_at,review_status",
        "review_status": "neq.rejected", "created_at": "gte." + since})
    articles = {a["article_id"]: a for a in db.select(
        "ac_articles", {"select": "article_id,source_id"})}
    start = datetime.fromisoformat(str(row.get("period_start"))[:10])
    window = {"start_date": start.date(), "end_date": end.date()}
    hu_cfg = ac_hungary.load_config()
    cov = coverage_audit.audit(events, articles, countries, hu_cfg,
                               window=window, now=end + timedelta(days=1))
    payload["coverage"] = cov
    client = None
    if "--synthesis" in args:
        import anthropic
        client = anthropic.Anthropic()
    brief = ac_command_brief.build_command_brief(
        payload, countries, coverage=cov, cfg=hu_cfg, client=client,
        events_by_id={e["event_id"]: e for e in events})
    payload["command_brief"] = brief

    out = ROOT / "data" / "command_brief_{}.json".format(week)
    out.write_text(json.dumps(brief, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    rows_out = ROOT / "data" / "command_brief_rows_{}.json".format(week)
    rows_out.write_text(json.dumps([dict(row, payload=payload)],
                                   ensure_ascii=False, default=str),
                        encoding="utf-8")
    p1 = brief["page1"]
    print("\nBottom line ({}):".format(p1["bottom_line"]["origin"]))
    for s in p1["bottom_line"]["sentences"]:
        print("  - {} {}".format(s["text"], s["refs"] or ""))
    print("\nPage 1 key judgements:")
    for k in p1["key_judgements"]:
        print("  {:<6} HU {:<8} SIG {}  {}".format(
            k["id"], k["hu_relevance"]["level"], k["significance"],
            k["statement"][:90]))
    print("\nPage 2 regional rows: {}".format(len(brief["page2"]["rows"])))
    for r in brief["page2"]["rows"]:
        print("  {:<26} HU {:<8} {}".format(r["country"][:26],
                                            r["hu_relevance"], r["ref"]))
    print("  no material change: {}".format(", ".join(
        x["name"] for x in brief["page2"]["no_material_change"])))
    print("  collection gap:     {}".format(", ".join(
        brief["page2"]["collection_gap"])))
    print("\nUnresolved refs: {}".format(
        brief["traceability"]["unresolved_refs"] or "none"))
    print("Saved {}\n      {}".format(out, rows_out))

    if write:
        meta = payload.setdefault("report_meta", {})
        prev = meta.get("restatement") or {}
        meta["restatement"] = {
            "reason": "Command Brief added (methodology v3.1); analytical "
                      "content unchanged",
            "previous_generated_utc": row.get("generated_at"),
            "restated_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"),
            "number": int(prev.get("number") or 0) + 1,
        }
        brief["restatement"] = meta["restatement"]
        db.upsert("ac_reports", [{
            "week_label": week, "period_start": row.get("period_start"),
            "period_end": row.get("period_end"),
            "generated_at": row.get("generated_at"), "payload": payload,
        }], "week_label")
        print("Written to ac_reports ({}) as restatement #{}.".format(
            week, meta["restatement"]["number"]))


if __name__ == "__main__":
    main()
