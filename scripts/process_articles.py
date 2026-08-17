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
import ac_match  # noqa: E402
import ac_programmes as acprog  # noqa: E402

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
      "first_reported_at": "YYYY-MM-DD or null — when this was FIRST reported anywhere, if the article says so",
      "new_evidence_at": "YYYY-MM-DD or null — when THIS new piece of evidence appeared",
      "evidence_kind": "new_event|new_confirmation|reassessment|correction",
      "variant": "<the exact designation as written, e.g. 'HH-60W', 'AH-64E', 'F-15EX', or null>",
      "service": "<the operating service if named, e.g. 'USAF', 'US Army', 'RAF', or null>",
      "milestone_kind": "first_delivery|final_delivery|deliveries_complete|ioc|foc|contract_award|production_start|mro_standup|certification|withdrawal_start|withdrawal_complete|loss|schedule_slip|selection_decision|none",
      "programme_reference": "<how the article names the wider programme, if it does — e.g. 'the 2024 AH-64E contract', or null>",
      "foc_year": <int or null — full operational capability>,
      "meaningful_scale_year": <int or null — when usable at militarily meaningful scale>,
      "originating_source": "<the PRIMARY source this claim traces to: 'Boeing press release', 'DSCA notification 26-42', 'Polish MoD statement', 'Oryx visual confirmation', or null>",
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
- VARIANT AND SERVICE ARE NOT DECORATION. Give the designation EXACTLY as
  written ("HH-60W", not "UH-60"; "F-15EX", not "F-15") and name the operating
  service where the article does. A 26-aircraft USAF HH-60W buy and the US
  Army's UH-60M fleet are different programmes with different baselines; the
  system needs the variant to avoid attaching a family-wide fleet total to a
  variant-level action.
- EVIDENCE KIND — this decides whether the item is THIS WEEK'S NEWS. Use
  "new_confirmation" when the article confirms something that HAPPENED EARLIER
  (e.g. a 2026 visual confirmation of a 2025 aircraft loss): event_date stays
  2025, new_evidence_at is the 2026 date, evidence_kind is "new_confirmation".
  Use "new_event" only when the action itself occurred in this reporting
  window. Use "correction" when the article corrects an earlier claim.
- ORIGINATING SOURCE — name the PRIMARY claim, not the outlet you read. Three
  trade-press pieces about one Boeing release all have originating_source
  "Boeing press release". This is how the system counts independent evidence
  chains, and it caps confidence, so accuracy here matters more than detail.
- MILESTONE KIND — a DELAY IS NOT AN ARRIVAL. If the news is that a programme
  slipped, milestone_kind is "schedule_slip", not "first_delivery". An MRO,
  depot or offset award is "mro_standup" and has no aircraft-delivery
  milestone at all.
- PROGRAMME REFERENCE — if the article ties this to a wider, already-known
  programme ("under the 2024 contract", "part of the 96-helicopter buy"), say
  so. This prevents the same programme being counted again as a new order.
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
    """Alias -> id lookup tables for countries and aircraft types.

    Az indexepites az ac_match modulba kerult, mert ott kezeli a
    designation-nyelvtan es a hatarellenorzes. A KETERTELMU aliasokat az
    ac_match.build_index eldobja: egy ketertelmu alias rosszabb, mint egy
    hianyzo, mert csendben rossz entitashoz kot."""
    types = db.select("ac_aircraft_types",
                      {"select": "type_id,name,designation,aliases"})
    countries = db.select("ac_countries", {"select": "country_id,name,aliases"})
    type_idx = ac_match.build_index(types, "type_id",
                                    name_keys=("name", "designation"))
    country_idx = ac_match.build_index(countries, "country_id",
                                       name_keys=("name",))
    # Designation-csalad -> type_id, hogy a katalogizalt csaladot a
    # tipusjel-nyelvtan is megtalalja.
    family_idx = {}
    for t in types:
        fam = ac_match.designation_family(t["type_id"]) \
            or ac_match.designation_family(t.get("designation") or "")
        if fam and fam not in family_idx:
            family_idx[fam] = t["type_id"]
    return type_idx, country_idx, family_idx


def match_aircraft(value, type_idx, family_idx=None):
    """Tipus-illesztes designation-fegyelemmel.

    A KORABBI implementacio nyers substringgel dolgozott:

        if len(alias) >= 4 and alias in v:   ->   "a-10" in "a-100ll"  ==  True

    Ez vitte be a Beriev A-100LL AEW&C-tesztpad veszteseget "A-10 Thunderbolt
    II — Loss x1"-kent az adatbazisba, es onnan a heti jelentes ORBAT-tablajaba.

    Visszaad: (type_id, variant_raw, match_kind).
    """
    return ac_match.match_type(value, type_idx, family_idx)


def match(value, index):
    # type: (Optional[str], Dict[str, str]) -> Optional[str]
    """Orszag-illesztes (hatar-tudatos: 'Niger' != 'Nigeria')."""
    return ac_match.match_country(value, index)


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
           "expected_ioc_year": _year(ev.get("expected_ioc_year")),
           "foc_year": _year(ev.get("foc_year")),
           "meaningful_scale_year": _year(ev.get("meaningful_scale_year"))}
    for key in ("announcement_date", "first_reported_at", "new_evidence_at"):
        val = str(ev.get(key) or "")[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
            out[key] = val
    # --- evidencia-jelleg: ez dönti el, hogy e HETI hir-e ---
    ek = str(ev.get("evidence_kind") or "").strip().lower()
    out["evidence_kind"] = ek if ek in EVIDENCE_KINDS else "new_event"
    mk = str(ev.get("milestone_kind") or "").strip().lower()
    out["milestone_kind"] = mk if mk in MILESTONE_KINDS else None
    # --- forraslanc gyokere: a lineage EBBOL szamol, nem a lapok szamabol ---
    origin = str(ev.get("originating_source") or "").strip()
    if origin:
        # Normalizalt kulcs, hogy harom lap ugyanarrol a Boeing-kozlemenyrol
        # UGYANAZT a lancazonositot kapja.
        out["originating_evidence_id"] = re.sub(
            r"[^a-z0-9]+", "-", origin.lower()).strip("-")[:80]
    # A HETI SZALLITAS ELOTTI ellenorzes: egy 'schedule_slip' sosem lehet
    # egyben kepesseg-erkezes.
    if out["milestone_kind"] == "schedule_slip":
        out["schedule_change"] = "delay"
    return out


EVIDENCE_KINDS = {"new_event", "new_confirmation", "reassessment", "correction"}
MILESTONE_KINDS = {
    "first_delivery", "final_delivery", "deliveries_complete", "ioc", "foc",
    "contract_award", "production_start", "mro_standup", "certification",
    "withdrawal_start", "withdrawal_complete", "loss", "schedule_slip",
    "selection_decision", "none"}


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
        type_idx, country_idx, family_idx = build_indexes()
        soft_keys = load_recent_soft_keys()
        # A meglevo programok betoltese, hogy az uj esemeny a MEGLEVO
        # programhoz kotodjon, ne ujat nyisson minden heten.
        try:
            programmes = db.select("ac_programmes", {
                "select": "programme_id,country_id,type_id,variant,service,"
                          "programme_kind,canonical_quantity,lifecycle_stage,"
                          "review_status"})
        except Exception as exc:  # noqa: BLE001
            programmes = []
            print("[warn] ac_programmes unavailable ({}) — events will be "
                  "inserted without programme linkage; run "
                  "supabase/add_programme_layer.sql".format(str(exc)[:100]))
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
                # --- ENTITAS-ILLESZTES designation-fegyelemmel ---
                type_id, variant_detected, match_kind = match_aircraft(
                    ev.get("aircraft_type"), type_idx, family_idx)
                # A modell altal explicit megadott varians elonyt kap a
                # kikovetkeztetett fole.
                variant_raw = (ev.get("variant") or variant_detected
                               or (ev.get("aircraft_type")
                                   if match_kind == "variant" else None))
                if match_kind == "none" and type_id is None:
                    print("  [unresolved] {!r} did not match the catalogue "
                          "safely — sent to review rather than guessed".format(
                              ev.get("aircraft_type")))
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

                # ---------- v3: varians, programme-kotes, baseline-delta ----
                v3 = {
                    "variant_raw": variant_raw,
                    "type_match_kind": match_kind,
                    "quantity_claimed": ev.get("quantity"),
                }
                probe = dict(row, **v2)
                probe["variant_raw"] = variant_raw
                probe["service"] = ev.get("service")
                probe["quantity_claimed"] = ev.get("quantity")

                # A PROGRAMME-KOTES. Ez az, ami megakadalyozza, hogy ugyanaz a
                # program minden heten ujra "megvasarlodjon".
                prog, why = acprog.find_programme(probe, programmes,
                                                  ev.get("summary"))
                if prog:
                    v3["programme_id"] = prog.get("programme_id")
                    print("    -> programme {} ({})".format(
                        prog.get("programme_id"), why))
                elif country_id and type_id:
                    kind = acprog.kind_from_event(probe, ev.get("summary"))
                    anchor = None
                    m = re.match(r"^(\d{4})", str(ev.get("event_date") or ""))
                    if m:
                        anchor = int(m.group(1))
                    new_key = acprog.programme_key(
                        country_id, type_id, variant_raw, ev.get("service"),
                        kind, anchor)
                    v3["programme_id"] = new_key
                    # A programrekordot letrehozzuk, ha meg nincs — igy a
                    # kovetkezo cikk mar EHHEZ kotodik, nem ujat nyit.
                    try:
                        db.upsert("ac_programmes", [{
                            "programme_id": new_key,
                            "country_id": country_id, "type_id": type_id,
                            "variant": variant_raw, "service": ev.get("service"),
                            "programme_kind": kind,
                            "title": "{} {}{}".format(
                                country_id.upper(),
                                variant_raw or type_id,
                                "" if kind == "acquisition"
                                else " ({})".format(
                                    acprog.PROGRAMME_KINDS.get(kind, kind))),
                            "review_status": "active",
                        }], "programme_id")
                        programmes.append({
                            "programme_id": new_key, "country_id": country_id,
                            "type_id": type_id, "variant": variant_raw,
                            "service": ev.get("service"),
                            "programme_kind": kind, "canonical_quantity": None,
                            "lifecycle_stage": None, "review_status": "active"})
                        print("    -> new programme {} [{}]".format(
                            new_key, kind))
                    except Exception as exc:  # noqa: BLE001
                        print("    [warn] could not create programme {}: "
                              "{}".format(new_key, str(exc)[:120]))

                # A BASELINE-DELTA. Alapertelmezesben NULLA: egy ujabb cikk
                # ugyanarrol a programrol nem ad hozza repulogepet.
                delta, delta_why = acprog.on_order_delta(
                    probe, prog, ev.get("summary"))
                v3["on_order_delta"] = delta
                if delta:
                    print("    -> on-order delta {:+d} ({})".format(
                        delta, delta_why))

                try:
                    db.insert("ac_events", dict(row, **v2, **v3))
                except Exception as e:  # noqa: BLE001
                    try:
                        db.insert("ac_events", dict(row, **v2))
                        print("  [warn] v3 columns missing — inserted without "
                              "programme/variant fields (run "
                              "add_programme_layer.sql)")
                    except Exception as e2:  # noqa: BLE001
                        try:
                            db.insert("ac_events", row)
                            print("  [warn] v2 columns missing too — inserted "
                                  "base fields only")
                        except Exception as e3:  # noqa: BLE001
                            print("  [WARN] event insert failed: {}".format(
                                str(e3)[:200]))

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
