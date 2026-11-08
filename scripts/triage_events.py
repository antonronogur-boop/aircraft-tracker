# -*- coding: utf-8 -*-
"""REVIEW TRIAGE — tanacsado besorolas a fuggo (pending) esemenyekre.

A human article approval MARAD: ez a script nem hagy jova es nem utasit el
semmit, csak a review-sorhoz ad egy rovid, ellenorizheto besorolast, hogy az
emberi munka a relevans kivetelekkel skalazodjon, ne a teljes gyujtessel.

Bemenet: az AI-kinyert esemenymezok (process_articles.py), a forras, a
programallapot es a HU-relevancia modell. Kimenet: ac_events.triage (jsonb):
  country, source, source_tier, domain, hu_relevance, relevance (AI
  extraction confidence), novelty, duplicate_probability, materiality,
  triage_class, rationale.

triage_class:
  likely_material   — vezetoi szempontbol valoszinuleg anyagi
  routine           — air power relevans, de rutin
  likely_duplicate  — egy mar meglevo esemeny ujabb leirasa
  low_relevance     — gyenge kinyeres (orszag/tipus nem azonosithato)

Usage: python scripts/triage_events.py [--all-pending] [--dry-run]
A supabase/add_review_triage.sql migracio (supabase/migrations.txt) nelkul a
script semmit nem ir, csak jelzi, hogy a triage ki van hagyva — a pipeline
es a review-sor valtozatlanul mukodik.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402
import ac_intel  # noqa: E402
import ac_hungary  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MATERIAL_STAGES = {"contract_signed", "delivery", "ioc", "foc", "loss",
                   "export_approval", "national_approval", "selection",
                   "retirement"}


def classify(e, ctx):
    countries, types, arts, srcs, progs, others, cfg_src, hu_cfg = ctx
    c = countries.get(e.get("country_id") or "") or {}
    t = types.get(e.get("type_id") or "") or {}
    art = arts.get(e.get("article_id") or "") or {}
    src = srcs.get(art.get("source_id") or "") or {}
    state = ac_intel.state_group_of_url(art.get("url"))
    tier_key = ("mod" if state else (cfg_src.get("existing_source_tiers")
                                     or {}).get(art.get("source_id") or "")
                or cfg_src.get("default_tier") or "specialist_defence")
    tier = (cfg_src.get("tier_rank") or {}).get(tier_key, 3)
    domain = ac_intel.domain_of(e, types)
    stage = ac_intel.stage_of(e)
    item = {"title": e.get("summary"), "fact": e.get("summary"),
            "capability_domain": domain, "lifecycle_stage": stage,
            "significance": 3 if stage in MATERIAL_STAGES else 2}
    hu = ac_hungary.score_item(item, [e.get("country_id")] if e.get(
        "country_id") else [], countries, hu_cfg)

    # Duplikatum: ugyanaz az orszag + tipus + esemenytipus 14 napon belul,
    # mar nem elutasitott esemenykent.
    d0 = ac_intel.effective_day(e)
    dup, dup_of = "low", None
    for o in others:
        if o["event_id"] == e["event_id"]:
            continue
        if (o.get("country_id"), o.get("type_id"), o.get("event_type")) != (
                e.get("country_id"), e.get("type_id"), e.get("event_type")):
            continue
        d1 = ac_intel.effective_day(o)
        if d0 and d1 and abs((d0 - d1).days) > 14:
            continue
        same_q = (o.get("quantity") is not None
                  and o.get("quantity") == e.get("quantity"))
        level = "high" if same_q else "medium"
        if dup != "high":
            dup, dup_of = level, o["event_id"]
    # Ujdonsag a programallapothoz kepest.
    prog = progs.get(e.get("programme_id") or "")
    if prog is None:
        novelty = "new programme or unlinked"
    elif prog.get("lifecycle_stage") == stage:
        novelty = "continuation (same stage)"
    else:
        novelty = "stage change ({} -> {})".format(
            prog.get("lifecycle_stage") or "—", stage)
    unresolved = not (e.get("country_id") and e.get("type_id"))
    conf = e.get("confidence")
    material = (stage in MATERIAL_STAGES and not unresolved) or \
        hu["level"] in ("HIGH", "MEDIUM")
    if dup == "high":
        klass = "likely_duplicate"
    elif unresolved and hu["level"] in ("LOW", "MINIMAL"):
        klass = "low_relevance"
    elif material:
        klass = "likely_material"
    else:
        klass = "routine"
    why = []
    if klass == "likely_duplicate":
        why.append("same country, type and event type as event {} within "
                   "14 days, same quantity".format(dup_of))
    if stage in MATERIAL_STAGES:
        why.append("lifecycle stage {}".format(stage))
    if hu["level"] in ("HIGH", "MEDIUM"):
        why.append("Hungary relevance {}".format(hu["level"]))
    if unresolved:
        why.append("country or aircraft type not resolved")
    if state:
        why.append("state-controlled source (attributed, one lineage)")
    return {
        "version": "triage-1.0",
        "computed_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M"),
        "country": c.get("name") or e.get("unresolved_country_name"),
        "aircraft": t.get("name") or e.get("unresolved_type_name"),
        "source": src.get("source_name") or art.get("source_id"),
        "source_tier": "Tier {}".format(tier),
        "domain": ac_intel.DOMAIN_LABELS.get(domain, domain),
        "stage": stage,
        "hu_relevance": hu["level"],
        "relevance": round(float(conf), 2) if conf is not None else None,
        "novelty": novelty,
        "duplicate_probability": dup,
        "duplicate_of": dup_of,
        "materiality": "likely material" if material else "routine",
        "triage_class": klass,
        "rationale": "; ".join(why) or "routine air-power item",
    }


def main():
    dry = "--dry-run" in sys.argv
    since = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    pending = db.select("ac_events", {"select": "*",
                                      "review_status": "eq.pending"})
    if "--all-pending" not in sys.argv:
        pending = [e for e in pending if not e.get("triage")]
    if pending and "triage" not in pending[0]:
        print("ac_events.triage column not present yet (migration "
              "supabase/add_review_triage.sql not applied) — triage "
              "skipped; the review queue works unchanged.")
        return
    others = db.select("ac_events", {
        "select": "event_id,country_id,type_id,event_type,quantity,"
                  "event_date,announcement_date,created_at",
        "review_status": "neq.rejected", "created_at": "gte." + since})
    countries = {c["country_id"]: c for c in db.select(
        "ac_countries", {"select": "country_id,name,region,aliases"})}
    types = {t["type_id"]: t for t in db.select(
        "ac_aircraft_types", {"select": "type_id,name,category"})}
    arts = {a["article_id"]: a for a in db.select(
        "ac_articles", {"select": "article_id,source_id,url"})}
    srcs = {s["source_id"]: s for s in db.select(
        "ac_sources", {"select": "source_id,source_name"})}
    try:
        progs = {p["programme_id"]: p for p in db.select(
            "ac_programmes", {"select": "programme_id,lifecycle_stage"})}
    except Exception:  # noqa: BLE001
        progs = {}
    cfg_src = json.loads((ROOT / "config" / "coverage_sources.json")
                         .read_text(encoding="utf-8"))
    ctx = (countries, types, arts, srcs, progs, others, cfg_src,
           ac_hungary.load_config())
    counts = {}
    for e in pending:
        tr = classify(e, ctx)
        counts[tr["triage_class"]] = counts.get(tr["triage_class"], 0) + 1
        if not dry:
            db.update("ac_events", {"event_id": "eq.{}".format(
                e["event_id"])}, {"triage": tr})
    print("Triage: {} pending event(s) — {}".format(
        len(pending), ", ".join("{} {}".format(v, k)
                                for k, v in sorted(counts.items()))
        or "nothing to do"))


if __name__ == "__main__":
    main()
