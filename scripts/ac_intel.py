# -*- coding: utf-8 -*-
"""ac_intel.py — az Aircraft Tracker elemzoi retegei (air power development
intelligence).

A korabbi jelentes azt mondta meg, mi kerult az adatbazisba (59 event, 22 deal,
476 aircraft, 22,8 mrd USD). A felderitoi kerdes mas:

    MELYIK 3-5 ESEMENY VALTOZTATJA MEG A KOVETKEZO 6-36 HONAP LEGI KEPESSEGKEPET,
    MENNYIRE BIZTOS, MIKORRA HAT, ES MIT JELENT RANK NEZVE?

Ezert a pipeline:

    ARTICLE -> CLAIM -> PROCUREMENT EVENT -> PROGRAMME -> FLEET ->
    CAPABILITY DELTA -> TIMELINE -> ASSESSMENT -> KEY JUDGEMENT

nem pedig ARTICLE -> EVENT -> deal count -> weekly summary.

A modul a Balkan/dron projektekben kidolgozott elveket viszi at:
  - event_date != publication_date (a heti tagsag az esemeny datuma szerint)
  - lineage != publikacioszam
  - confidence / significance / novelty / baseline change kulon dimenzio
  - trend csak longitudinalis bizonyitekbol
  - a QA kapu, nem labjegyzet
plusz a legiero-specifikus reteget: eletciklus-stadium, kepesseg-domain,
kepesseg-hatalybalepes (IOC), es ORBAT-delta.
"""
import json
import os
import re
from datetime import datetime

MODEL = os.environ.get("AC_ASSESSMENT_MODEL", "claude-sonnet-4-6")

# --------------------------------------------------------------------------
# Fogalmi keszletek
# --------------------------------------------------------------------------

DOMAIN_LABELS = {
    "fighter_strike": "Fighter / strike",
    "attack_helicopter": "Attack helicopter",
    "air_mobility_rotary": "Air mobility — rotary",
    "air_mobility_fixed": "Air mobility — fixed wing",
    "uncrewed_cca": "Uncrewed / CCA",
    "counter_uas": "Counter-UAS",
    "isr_aew_sigint": "ISR / AEW&C / SIGINT",
    "tanker": "Air-to-air refuelling",
    "training": "Training / pilot pipeline",
    "maritime_patrol": "Maritime patrol",
    "other": "Other",
}

# Katalogus-kategoria -> kepesseg-domain, ha az extrakcio nem adott domaint.
CATEGORY_TO_DOMAIN = {
    "fighter": "fighter_strike", "bomber": "fighter_strike",
    "attack": "fighter_strike", "helicopter": "air_mobility_rotary",
    "transport": "air_mobility_fixed", "tanker": "tanker",
    "trainer": "training", "uav": "uncrewed_cca",
    "special_mission": "isr_aew_sigint", "maritime_patrol": "maritime_patrol",
}

# Az eletciklus sorrendje: mennyire kozel van a tenyleges kepesseghez.
STAGE_ORDER = ["requirement", "rfi_sources_sought", "rfp", "bid", "selection",
               "national_approval", "export_approval", "contract_signed",
               "production", "delivery", "ioc", "foc", "upgrade_programme",
               "retirement", "loss", "other"]
STAGE_LABELS = {
    "requirement": "Requirement", "rfi_sources_sought": "RFI / sources sought",
    "rfp": "RFP", "bid": "Bid", "selection": "Selection",
    "national_approval": "National approval (buyer funding)",
    "export_approval": "Export approval (seller clearance — NOT a contract)",
    "contract_signed": "Contract signed", "production": "In production",
    "delivery": "Delivery", "ioc": "IOC", "foc": "FOC",
    "upgrade_programme": "Upgrade programme", "retirement": "Retirement",
    "loss": "Loss / attrition", "other": "Other",
}
# Erettsegi savok a matrixhoz.
STAGE_MATURITY = {
    "requirement": "Intent", "rfi_sources_sought": "Intent", "rfp": "Intent",
    "bid": "Intent", "selection": "Committed",
    "national_approval": "Committed", "export_approval": "Committed",
    "contract_signed": "Contracted", "production": "Contracted",
    "delivery": "Fielding", "ioc": "Operational", "foc": "Operational",
    "upgrade_programme": "Contracted", "retirement": "Fielding",
    "loss": "Fielding", "other": "Intent",
}
MATURITY_ORDER = ["Intent", "Committed", "Contracted", "Fielding", "Operational"]

# Csak azonos tipusu ertek adhato ossze.
VALUE_TYPE_LABELS = {
    "firm": "signed contract value",
    "ceiling": "IDIQ / 'up to' ceiling",
    "notified_max": "DSCA notification maximum (authorisation ceiling)",
    "estimate": "press estimate", "unknown": "unspecified basis",
}


# --------------------------------------------------------------------------
# Segedfuggvenyek
# --------------------------------------------------------------------------

def parse_day(value):
    """Valodi datum-parseolas. String-osszehasonlitas TILOS: a dronos
    projektben a 'Mon, 08 Jun' tipusu nyers datumok minden szuron atcsusztak,
    mert 'M' > '2'."""
    if not value:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def effective_day(e):
    """Az esemeny idobeli besorolasa. Az event_date az elsodleges; ha nincs,
    az announcement_date; vegso esetben a created_at. Egy 2020-ban alairt
    szerzodesrol szolo 2026-os cikk NEM tesz egy 2020-as esemenyt e hetive."""
    return (parse_day(e.get("event_date"))
            or parse_day(e.get("announcement_date"))
            or parse_day(e.get("created_at")))


def domain_of(e, types_by_id):
    d = e.get("capability_domain")
    if d in DOMAIN_LABELS:
        return d
    t = types_by_id.get(e.get("type_id") or "")
    if t:
        return CATEGORY_TO_DOMAIN.get(t.get("category") or "", "other")
    return "other"


def stage_of(e):
    s = e.get("lifecycle_stage")
    if s in STAGE_LABELS:
        return s
    return {"order": "contract_signed", "delivery": "delivery",
            "upgrade": "upgrade_programme", "selection": "selection",
            "negotiation": "requirement", "retirement": "retirement",
            "incident": "loss", "export_sale": "contract_signed"}.get(
                e.get("event_type") or "", "other")


def value_breakdown(events):
    """Ertek-osszegzes ERTEKTIPUSONKENT. Egyetlen 'disclosed value' szam
    osszeadna az alairt szerzodest, az IDIQ-plafont es a DSCA-notifikacios
    maximumot — ezek nem osszeadhatok. Az arfolyam-eveket is jelezzuk."""
    out, years = {}, set()
    for e in events:
        v = e.get("value_usd_m")
        if v in (None, ""):
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        vt = e.get("value_type") or "unknown"
        out.setdefault(vt, {"usd_m": 0.0, "events": 0})
        out[vt]["usd_m"] += v
        out[vt]["events"] += 1
        y = e.get("value_currency_year")
        if y:
            years.add(int(y))
    for vt in out:
        out[vt]["usd_m"] = round(out[vt]["usd_m"])
        out[vt]["label"] = VALUE_TYPE_LABELS.get(vt, vt)
    return {"by_value_type": out,
            "currency_years": sorted(years) or None,
            "note": ("Values are NOT summed across types: signed contracts, "
                     "IDIQ ceilings and DSCA notification maxima measure "
                     "different things.")}


def platform_breakdown(events, types_by_id):
    """Darabszam kepesseg-domainenkent. Egy F-35, egy Chinook, egy CCA es egy
    hatizsakos motoros siklóernyo osszeadasa ('476 aircraft') elemzoileg
    ertelmetlen headline KPI."""
    out = {}
    for e in events:
        q = e.get("quantity")
        try:
            q = int(q)
        except (TypeError, ValueError):
            continue
        if q <= 0:
            continue
        d = domain_of(e, types_by_id)
        out.setdefault(d, {"airframes": 0, "actions": 0,
                           "label": DOMAIN_LABELS.get(d, d)})
        out[d]["airframes"] += q
        out[d]["actions"] += 1
    return out


def orbat_delta(events, fleets, types_by_id, countries_by_id, max_countries=4):
    """ORBAT-delta orszagonkent es tipusonkent: mi van hadrendben, mi van
    rendelesben, mit erint a heti esemeny. Ez az, amit egy felderito sejt
    tenylegesen hasznal — nem a heti eventszam."""
    touched = {}
    for e in events:
        cid, tid = e.get("country_id"), e.get("type_id")
        if not cid or not tid:
            continue
        touched.setdefault(cid, {}).setdefault(tid, []).append(e)
    fleet_idx = {}
    for f in fleets:
        fleet_idx.setdefault((f.get("country_id"), f.get("type_id")), {})[
            f.get("fleet_status")] = (f.get("quantity") or 0)
    rows = []
    for cid, per_type in touched.items():
        entries = []
        for tid, evs in per_type.items():
            fl = fleet_idx.get((cid, tid), {})
            best = sorted(evs, key=lambda x: -(float(x.get("value_usd_m") or 0)
                                               or (x.get("quantity") or 0)))[0]
            t = types_by_id.get(tid) or {}
            entries.append({
                "type_id": tid, "type": t.get("name") or tid,
                "domain": domain_of(best, types_by_id),
                "active": fl.get("active") or 0,
                "on_order": fl.get("on_order") or 0,
                "stored": fl.get("stored") or 0,
                "this_week_stage": stage_of(best),
                "this_week_quantity": best.get("quantity"),
                "expected_ioc_year": best.get("expected_ioc_year"),
                "delivery_window": ("{}–{}".format(
                    best.get("delivery_start_year"),
                    best.get("delivery_end_year"))
                    if best.get("delivery_start_year") else None),
            })
        if not entries:
            continue
        entries.sort(key=lambda x: -(x["on_order"] + x["active"]))
        c = countries_by_id.get(cid) or {}
        rows.append({"country_id": cid, "country": c.get("name") or cid,
                     "region": c.get("region"), "entries": entries[:6],
                     "_weight": sum(e["on_order"] + e["active"] for e in entries)})
    rows.sort(key=lambda r: -r["_weight"])
    for r in rows:
        r.pop("_weight", None)
    return rows[:max_countries]


def capability_timeline(events, types_by_id, countries_by_id, horizon=2035):
    """Kepesseg-hatalybalepesi idovonal: mikor valik a beszerzes tenyleges
    kepesseggé. Egy 7,7 mrd USD-s szerzodes near-term hatasa nulla, ha az elso
    szazad 2030-ban all fel."""
    out = []
    for e in events:
        y = e.get("expected_ioc_year") or e.get("delivery_start_year")
        try:
            y = int(y)
        except (TypeError, ValueError):
            continue
        if not (2000 <= y <= horizon):
            continue
        c = countries_by_id.get(e.get("country_id") or "") or {}
        t = types_by_id.get(e.get("type_id") or "") or {}
        out.append({
            "year": y,
            "basis": "expected IOC" if e.get("expected_ioc_year")
                     else "first delivery",
            "country": c.get("name") or e.get("unresolved_country_name") or "?",
            "type": t.get("name") or e.get("unresolved_type_name") or "?",
            "domain": domain_of(e, types_by_id),
            "quantity": e.get("quantity"),
            "stage": stage_of(e),
        })
    out.sort(key=lambda x: (x["year"], x["country"]))
    return out


def maturity_matrix(developments):
    """Kepesseg-domain x programme-erettseg. Egy pillantasra megmutatja, mi
    csak szandek es mi lesz tenyleges katonai kepesseg."""
    grid = {}
    for d in developments:
        dom = d.get("capability_domain") or "other"
        mat = STAGE_MATURITY.get(d.get("lifecycle_stage") or "other", "Intent")
        grid.setdefault(dom, {}).setdefault(mat, []).append(
            d.get("display_label") or d.get("title"))
    return grid


# --------------------------------------------------------------------------
# Modellhivas
# --------------------------------------------------------------------------

def _json_from(raw):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[4:] if raw.startswith("json") else raw
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}")
        if 0 <= s < e:
            return json.loads(raw[s:e + 1])
        raise


def _call(client, system, payload, max_tokens):
    for attempt in range(3):
        try:
            tokens = min(max_tokens * (2 ** attempt), 32000)
            with client.messages.stream(
                    model=MODEL, max_tokens=tokens, system=system,
                    messages=[{"role": "user", "content": json.dumps(
                        payload, ensure_ascii=False)[:60000]}]) as stream:
                msg = stream.get_final_message()
            if getattr(msg, "stop_reason", None) == "max_tokens":
                raise ValueError("truncated at max_tokens")
            return _json_from("".join(b.text for b in msg.content
                                      if b.type == "text"))
        except Exception as exc:  # noqa: BLE001
            print("  [warn] intel-layer attempt {}/3: {}: {}".format(
                attempt + 1, type(exc).__name__, str(exc)[:150]))
            if attempt == 2:
                return None
    return None


DEV_PROMPT = """You are the intelligence officer of an air force wing writing
the weekly AIR POWER DEVELOPMENT brief from procurement events that all fall
inside the reporting period.

Your reader does not care how many events were collected. They ask: which
developments change the air capability picture over the next 6-36 months, how
certain is it, when does it take effect, and what does it mean for us.

Return STRICT JSON only:
{
 "developments": [
   {
     "event_ids": [<every event id this development is built from>],
     "title": "<country + action + platform + quantity, neutral>",
     "display_label": "<2-4 words for the matrix, e.g. 'PL F-35A batch 2'>",
     "capability_domain": "fighter_strike|attack_helicopter|air_mobility_rotary|air_mobility_fixed|uncrewed_cca|counter_uas|isr_aew_sigint|tanker|training|maritime_patrol|other",
     "lifecycle_stage": "<the stage actually reached — see the rules>",
     "fact": "<2-4 sentences, attributed: 'the ministry stated', 'Janes reported'. Numbers exactly as reported.>",
     "capability_delta": "<WHAT CHANGES in capability terms: type entering/leaving service, quantity, range/payload/LO/BVR/EW/lift, new basing, new ecosystem. If nothing changes yet — an intent, a study, a talks round — write 'no capability change at this stage'.>",
     "effect_timing": "immediate|<12 months|1-3 years|>3 years|unknown",
     "effect_timing_basis": "<why: stated IOC, delivery window, production rate, or 'not stated in reporting'>",
     "so_what": "<1-2 sentences for an air staff: what it means for force structure, regional balance or our own planning. If it means little, say so.>",
     "novelty": "new|escalation|continuation|confirmation_of_known",
     "significance": 1-5,
     "confidence": "high|moderate|low",
     "reports_count": <total source attachments>,
     "independent_lineages": <how many INDEPENDENT evidence chains>,
     "lineage_note": "<e.g. 'manufacturer press release restated by three outlets — one lineage'>",
     "value_usd_m": <number or null>,
     "value_type": "firm|ceiling|notified_max|estimate|unknown",
     "indicators_to_watch": ["<2-3 concrete, checkable next observables>"]
   }
 ],
 "dropped_event_ids": [
   {"event_id": <id>, "reason": "<max 8 words: duplicate facet, routine, no capability effect, too thin>"}
 ]
}

RULES — each traces to a specific failure in earlier editions:
- ACCOUNT FOR EVERY INPUT EVENT: in a development's event_ids or in
  dropped_event_ids with a reason.
- SELECT ON CAPABILITY EFFECT, NOT ON MONEY OR VOLUME. A $90M counter-UAS
  interceptor buy that fields next year can outrank a multi-billion order that
  reaches IOC in 2033. Aim for 4-8 developments; fewer on a quiet week.
- LIFECYCLE PRECISION. "Intends to acquire 60 helicopters" and "the 60th
  helicopter enters service" are different worlds. A parliamentary budget
  release is national_approval; a US DSCA/State Department clearance is
  export_approval — an authorisation ceiling, NOT a purchase, and its value is
  a notional maximum. Never call either a signed contract.
- AIRCRAFT COUNT IS NOT COMBAT CAPABILITY. From a procurement record you
  cannot know operational aircraft, pilot readiness, sortie generation,
  weapons stocks, mission-data availability, tanker support, SEAD/DEAD
  integration, basing resilience or maintenance availability. Never write that
  a country becomes "the most capable operator" or that a supplier is
  "consolidating as primary supplier" — those need force-generation evidence.
- ONE CONTRACT IS NOT A SUPPLIER RELATIONSHIP AND ONE ORDER IS NOT A DOCTRINE.
  Prefer "would introduce another Western fighter ecosystem into the force
  regeneration effort" over "consolidates X as primary supplier".
- TREND WORDS ("accelerating", "surge", "pivot", "structural shift") require
  >=3 temporal observations or an explicit stated baseline. Two data points are
  an indicator at most. Never infer a trend from event counts.
- DELIVERIES DO NOT PROVE SCHEDULE PERFORMANCE. From N delivery events you
  cannot say supply chains are meeting schedules: you do not know the
  contracted dates, the backlog, or engine/avionics bottlenecks. Write
  "continued execution of existing programmes; available data does not
  establish whether deliveries are on schedule".
- RETIREMENTS ARE NOT ACCELERATION without a prior-period baseline.
- TWO OUTLETS ON ONE PRESS RELEASE ARE ONE LINEAGE. More publications never
  means more confirmation.
- PROPER NOUNS AND NUMBERS copied exactly. Never re-spell a designation from
  memory. Do not convert or re-base currency figures.
- Write nothing you cannot trace to the events given. BE COMPACT — stay within
  the stated sentence limits so the JSON fits the response budget."""


KJ_PROMPT = """You write the front page of an air force wing's weekly AIR POWER
DEVELOPMENT INTELLIGENCE BRIEF.

Return STRICT JSON only:
{
 "bottom_line": "<3-5 sentences: what actually changed in the air capability
   picture this period, against the running baseline. If little changed, say so
   plainly — a quiet week honestly reported builds trust. Never explain a
   volume change with a cause the data does not contain.>",
 "key_judgements": [
   {
     "id": "KJ-01",
     "domain": "<capability domain this judgement is about>",
     "judgement": "<one falsifiable sentence about a capability change or its direction — not an event restatement, not a deal count>",
     "confidence": "high|moderate|low",
     "basis": "<2-3 sentences: which developments, how sourced, what is NOT independently confirmed>",
     "assessment": "<2-3 sentences: what it means for force structure / regional balance / our planning>",
     "effect_timing": "immediate|<12 months|1-3 years|>3 years|unknown",
     "alternative_explanation": "<one plausible alternative reading, or null>",
     "indicators": ["<2-3 checkable things that would strengthen or break it>"],
     "supporting_event_ids": [<ids>]
   }
 ],
 "priority_watch": [
   {"issue": "<short>", "why_it_matters": "<1 sentence, capability terms>",
    "next_observable": "<the single next thing that would move this>",
    "horizon": "days|weeks|months|quarters",
    "impact_if_confirmed": "high|medium|low"}
 ],
 "intelligence_gaps": ["<2-4 specific things this period's collection could not answer>"]
}

RULES:
- 3 to 5 judgements, one per capability domain or programme. A judgement
  interprets a CHANGE against the baseline and is falsifiable.
- CONFIDENCE DICTATES THE VERB. low -> "provides the first available
  indication that X could ..."; moderate -> "indicates / suggests"; high ->
  "we assess that". A low-confidence judgement never states a fact about the
  world.
- EVIDENCE BOUNDS CONFIDENCE: single-lineage support caps at moderate.
- SEPARATE PROCUREMENT FROM CAPABILITY. Contract value and airframe counts are
  procurement facts; combat capability needs readiness, weapons, enablers and
  basing. Judgements must respect that line explicitly.
- TIMING IS PART OF THE JUDGEMENT: a large order with IOC beyond three years
  has near-term operational effect of zero, and the judgement should say so.
- priority_watch: MAXIMUM 5, ranked by impact. Everything else belongs in the
  annex. A paramotor solicitation does not outrank a national fighter
  decision.
- If the period supports NO real judgement, return one saying exactly that and
  what would be needed. Do not force a narrative: if nothing happened in
  fighters this week, write no fighter judgement."""


def event_payload(e, types_by_id, countries_by_id, fleets_idx):
    c = countries_by_id.get(e.get("country_id") or "") or {}
    t = types_by_id.get(e.get("type_id") or "") or {}
    fl = fleets_idx.get((e.get("country_id"), e.get("type_id")), {})
    return {
        "event_id": e.get("event_id"),
        "country": c.get("name") or e.get("unresolved_country_name"),
        "region": c.get("region"),
        "aircraft": t.get("name") or e.get("unresolved_type_name"),
        "category": t.get("category"),
        "event_type": e.get("event_type"),
        "lifecycle_stage": stage_of(e),
        "capability_domain": domain_of(e, types_by_id),
        "quantity": e.get("quantity"),
        "value_usd_m": e.get("value_usd_m"),
        "value_type": e.get("value_type"),
        "value_currency_year": e.get("value_currency_year"),
        "event_date": e.get("event_date"),
        "announcement_date": e.get("announcement_date"),
        "delivery_start_year": e.get("delivery_start_year"),
        "delivery_end_year": e.get("delivery_end_year"),
        "expected_ioc_year": e.get("expected_ioc_year"),
        "independent_lineages": e.get("independent_lineages") or 1,
        "confidence": e.get("confidence"),
        "summary": (e.get("summary") or "")[:400],
        "fleet_baseline": {"active": fl.get("active") or 0,
                           "on_order": fl.get("on_order") or 0,
                           "stored": fl.get("stored") or 0},
    }


def build_developments(client, events, types_by_id, countries_by_id, fleets,
                       max_events=26):
    if client is None or not events:
        return [], []
    fleets_idx = {}
    for f in fleets:
        fleets_idx.setdefault((f.get("country_id"), f.get("type_id")), {})[
            f.get("fleet_status")] = (f.get("quantity") or 0)
    # Rangsor: eletciklus-erettseg elore (a szerzodes tobbet er, mint a
    # szandek), majd darabszam/ertek. NEM puszta penzertek szerint.
    stage_rank = {s: i for i, s in enumerate(
        ["contract_signed", "production", "delivery", "ioc", "foc",
         "national_approval", "upgrade_programme", "selection",
         "export_approval", "retirement", "loss", "bid", "rfp",
         "rfi_sources_sought", "requirement", "other"])}
    ranked = sorted(events, key=lambda e: (
        stage_rank.get(stage_of(e), 99),
        -(float(e.get("value_usd_m") or 0)),
        -(int(e.get("quantity") or 0))))[:max_events]
    picked = {id(e) for e in ranked}
    context_titles = [{"event_id": e.get("event_id"),
                       "summary": str(e.get("summary") or "")[:90]}
                      for e in events if id(e) not in picked][:120]
    payload = {"events": [event_payload(e, types_by_id, countries_by_id,
                                        fleets_idx) for e in ranked],
               "context_events": context_titles}
    print("  Developments: {} event (+{} context) -> model".format(
        len(ranked), len(context_titles)))
    out = _call(client, DEV_PROMPT, payload, 16000)
    if not out:
        return [], []
    devs = out.get("developments") or []
    by_id = {e.get("event_id"): e for e in ranked}
    for d in devs:
        try:
            d["significance"] = max(1, min(5, int(d.get("significance") or 1)))
        except (TypeError, ValueError):
            d["significance"] = 1
        try:
            rep = int(d.get("reports_count") or 1)
        except (TypeError, ValueError):
            rep = 1
        try:
            lin = int(d.get("independent_lineages") or 1)
        except (TypeError, ValueError):
            lin = 1
        lin = max(1, min(lin, rep))
        d["reports_count"], d["independent_lineages"] = rep, lin
        # Az export_approval sosem szerepelhet alairt uzletkent, es az erteke
        # engedelyezesi felso hatar — kodban is kikenyszeritve.
        if d.get("lifecycle_stage") == "export_approval" and \
                d.get("value_type") in (None, "firm"):
            d["value_type"] = "notified_max"
            d["auto_adjustment"] = ("value reclassified: export clearance "
                                    "ceiling, not a signed contract value")
        # A tenyleges esemenyadatokbol vett idozites felulirja a modellt.
        ioc = [by_id.get(i, {}).get("expected_ioc_year")
               for i in (d.get("event_ids") or [])]
        ioc = [int(y) for y in ioc if y]
        if ioc:
            d["expected_ioc_year"] = min(ioc)
    used = {i for d in devs for i in (d.get("event_ids") or [])}
    declared = {x.get("event_id"): x.get("reason") or ""
                for x in (out.get("dropped_event_ids") or [])
                if isinstance(x, dict)}
    for e in ranked:
        if e.get("event_id") not in used and e.get("event_id") not in declared:
            declared[e.get("event_id")] = ("NOT addressed by the model's "
                                           "selection — auto-flagged")
    # Ami nem valtoztat kepesseget, az hatterbe kerul, nem a fo termekbe.
    background = [d for d in devs
                  if "no capability change" in
                  str(d.get("capability_delta") or "").lower()
                  and d.get("significance", 1) <= 2]
    for b in background:
        devs.remove(b)
    order = {"immediate": 0, "<12 months": 1, "1-3 years": 2, ">3 years": 3,
             "unknown": 4}
    devs.sort(key=lambda d: (-d.get("significance", 1),
                             order.get(d.get("effect_timing"), 4),
                             {"high": 0, "moderate": 1, "low": 2}.get(
                                 d.get("confidence"), 3)))
    if devs:
        devs[0]["_selection"] = {"events_in": len(ranked),
                                 "developments_out": len(devs),
                                 "dropped": declared}
    return devs, background


def build_judgements(client, developments, stats):
    if client is None or not developments:
        return None
    slim = [{k: d.get(k) for k in (
        "event_ids", "title", "capability_domain", "lifecycle_stage", "fact",
        "capability_delta", "effect_timing", "effect_timing_basis", "so_what",
        "novelty", "significance", "confidence", "independent_lineages",
        "value_usd_m", "value_type", "expected_ioc_year")}
        for d in developments]
    payload = {"developments": slim, "period_stats": stats}
    print("  Key judgements: {} development -> model".format(len(slim)))
    out = _call(client, KJ_PROMPT, payload, 8000)
    if not out:
        return None
    lin_by_event = {}
    for d in developments:
        for i in (d.get("event_ids") or []):
            lin_by_event[i] = d.get("independent_lineages") or 1
    for j in (out.get("key_judgements") or []):
        lins = [lin_by_event.get(i, 1)
                for i in (j.get("supporting_event_ids") or [])]
        if lins and max(lins) <= 1 and j.get("confidence") == "high":
            j["confidence"] = "moderate"
            j["auto_adjustment"] = ("confidence capped at moderate: all "
                                    "supporting reporting is single-lineage")
    # A prioritalt figyelolista legfeljebb ot tetel.
    pw = out.get("priority_watch") or []
    rank = {"high": 0, "medium": 1, "low": 2}
    pw.sort(key=lambda x: rank.get(x.get("impact_if_confirmed"), 3))
    out["priority_watch"] = pw[:5]
    return out


# --------------------------------------------------------------------------
# Analytical QA — jelez, majd a kapu atirat vagy visszatart
# --------------------------------------------------------------------------

TREND_RX = re.compile(
    r"\b(accelerat\w+|intensif\w+|surge|structural shift|pivot(?:ing)?|"
    r"escalating trend|declining trend|ramp[- ]up)\b"
    r"|\b(?:increas\w+|growing|rising|mounting|deepening)\s+"
    r"(?:[\w-]+\s+){0,2}(?:tempo|activity|pressure|demand|procurement)\b", re.I)
CAPABILITY_OVERREACH_RX = re.compile(
    r"\bmost capable\b|\bprimary supplier\b|\bconsolidat\w+ as\b|"
    r"\bcombat[- ]ready\b|\boperationally superior\b|\bair superiority\b|"
    r"\bcomplete generational replacement\b", re.I)
SCHEDULE_RX = re.compile(
    r"\b(on schedule|meeting schedules?|schedule performance|"
    r"supply chains? (?:are|is) )\b", re.I)
SUPERL_RX = re.compile(
    r"\b(most|largest|biggest|strongest|leading)\s+(?:[\w-]+\s+){0,3}"
    r"(operator|fleet|capability|air force|buyer|programme|program)\b", re.I)
DETERMINISTIC_RX = re.compile(
    r"\b(would force|will force|guarantees?|ensures?|removes? all|"
    r"will inevitably)\b", re.I)
HEDGE_RX = re.compile(
    r"\b(may|might|could|appears|suggests?|indication|potential|if confirmed|"
    r"not established|cannot be|would)\b", re.I)
DOUBLE_WORD_RX = re.compile(r"\b(\w{3,})\s+\1\b", re.I)


def run_self_checks(developments, judgements, window_start, window_end,
                    stats=None, events=None):
    """Analitikai onellenorzes. Nem javit: JELEZ. A jelentes publikalja."""
    issues = []
    kjs = (judgements or {}).get("key_judgements") or []

    def prose(o, fields):
        return " ".join(str(o.get(f) or "") for f in fields)

    for d in developments:
        text = prose(d, ("fact", "capability_delta", "so_what"))
        label = d.get("display_label") or d.get("title")
        # 1. kepesseg-tulallitas beszerzesi rekordbol
        if CAPABILITY_OVERREACH_RX.search(text):
            issues.append(("capability claim beyond procurement evidence "
                           "(readiness/weapons/enablers unknown)", label))
        # 2. menetrend-teljesitmes allitas
        if SCHEDULE_RX.search(text):
            issues.append(("delivery events presented as schedule performance",
                           label))
        # 3. trend idosor nelkul
        if TREND_RX.search(text):
            issues.append(("trend claim without temporal baseline", label))
        # 4. szuperlativusz
        if SUPERL_RX.search(text):
            issues.append(("unqualified superlative claim", label))
        # 5. export-engedely mint uzlet
        if d.get("lifecycle_stage") == "export_approval" and \
                re.search(r"\b(contract|deal|purchase|order)\b", text, re.I) \
                and not re.search(r"clearance|approval|authoris|authoriz",
                                  text, re.I):
            issues.append(("export clearance described as a purchase", label))
        # 6. hianyzo hatalybalepesi ido nagy tetelnel
        if (d.get("significance") or 0) >= 4 and \
                d.get("effect_timing") in (None, "", "unknown"):
            issues.append(("high-significance development without a capability "
                           "effect date", label))
        # 7. datumfegyelem
        for key, day in (("event", parse_day(d.get("event_date"))),):
            if day and window_end and day > window_end:
                issues.append(("ERROR: {} date beyond the reporting period "
                               "end".format(key), label))
            if day and window_start and (window_start - day).days > 60:
                issues.append(("ERROR: development built on an event older "
                               "than the period by >60 days", "{} ({})".format(
                                   label, d.get("event_date"))))
        dw = DOUBLE_WORD_RX.search(text)
        if dw:
            issues.append(("duplicated word in prose ('{}')".format(
                dw.group(1)), label))

    # 8. ugyanaz az esemeny tobb developmentben
    seen = set()
    for d in developments:
        for i in (d.get("event_ids") or []):
            if i in seen:
                issues.append(("same event used in multiple developments",
                               "event {}".format(i)))
            seen.add(i)

    gaps = " ".join((judgements or {}).get("intelligence_gaps") or []).lower()
    for j in kjs:
        jt = prose(j, ("judgement", "basis", "assessment"))
        label = j.get("id")
        if TREND_RX.search(jt):
            issues.append(("judgement uses trend language — verify baseline",
                           label))
        if CAPABILITY_OVERREACH_RX.search(jt):
            issues.append(("judgement asserts combat capability from "
                           "procurement data", label))
        if SUPERL_RX.search(jt):
            issues.append(("unqualified superlative in judgement", label))
        if DETERMINISTIC_RX.search(jt):
            issues.append(("deterministic language in judgement", label))
        if j.get("confidence") == "low" and not HEDGE_RX.search(
                str(j.get("judgement") or "")):
            issues.append(("assertive judgement at low confidence", label))
        if j.get("effect_timing") in (None, "", "unknown"):
            issues.append(("judgement without a capability effect horizon",
                           label))
        for w in ("confirmed", "verified", "independent", "quantified"):
            if w in str(j.get("judgement") or "").lower() and \
                    (("not " + w) in gaps or ("no " + w) in gaps):
                issues.append(("judgement asserts what the gaps say is unknown",
                               label))
                break

    # 9. volumen mint aktivitas
    if stats and stats.get("volume_not_comparable"):
        bl = str((judgements or {}).get("bottom_line") or "")
        if re.search(r"\b(increase|surge|rose|jump|spike|decline|fell)\w*\b",
                     bl, re.I) and "collection" not in bl.lower():
            issues.append(("volume change may be presented as activity trend",
                           "bottom_line"))
    # 10. az annex esemenyszovegeiben is: kepesseg-tulallitas
    n = 0
    for e in (events or []):
        s = str(e.get("summary") or "")
        if n < 6 and CAPABILITY_OVERREACH_RX.search(s):
            issues.append(("capability claim in event-layer summary (annex)",
                           s[:70]))
            n += 1

    seen_i, out = set(), []
    for kind, what in issues:
        k = (kind, str(what))
        if k not in seen_i:
            seen_i.add(k)
            out.append({"check": kind, "item": what})
    return out


REWRITABLE = (
    "capability claim beyond procurement", "delivery events presented as",
    "trend claim without", "unqualified superlative",
    "export clearance described as", "judgement uses trend language",
    "judgement asserts combat capability", "deterministic language",
    "assertive judgement at low confidence", "duplicated word in prose",
    "volume change may be presented", "judgement asserts what the gaps",
)

KJ_BLOCKING = (
    "judgement asserts what the gaps say is unknown",
    "judgement uses trend language",
    "judgement asserts combat capability from procurement data",
    "assertive judgement at low confidence",
)

REWRITE_PROMPT = """You are the QA editor of an air force intelligence brief.
You get fields whose wording failed analytical-language checks, with the check
that fired. Rewrite ONLY the offending wording, changing NO facts, names,
numbers, designations or structure, keeping similar length. Return STRICT JSON:
{"fixes": [{"target": "dev|kj|bottom_line", "id": "<dev index or KJ id or
null>", "field": "<field name>", "new_text": "<rewritten full field>"}]}
Downgrade rules:
- capability claim beyond procurement -> describe the procurement fact and the
  potential capability, noting that readiness, weapons stocks, enablers and
  basing are not established by the data.
- delivery/schedule -> "continued execution of existing programmes; available
  data does not establish whether deliveries are on schedule".
- trend without baseline -> state the observation without trend words.
- superlative -> "the largest ... identified in the available collection" or
  drop the comparison.
- export clearance described as purchase -> "clearance authorising a sale of
  up to X; no signed contract is evidenced".
- deterministic -> "could / is likely to increase".
- assertive at low confidence -> "provides the first available indication that
  ... could".
- judgement asserting what gaps call unknown -> state the observation, then
  explicitly decline the unproven part.
- duplicated word -> fix the typo only.
Rewrite every listed item. No commentary."""


def qa_language_gate(client, developments, judgements, issues):
    fixable = [i for i in issues
               if any(i["check"].startswith(p) for p in REWRITABLE)]
    if client is None or not fixable:
        return 0
    dev_by_label = {}
    for idx, d in enumerate(developments or []):
        dev_by_label[str(d.get("display_label") or d.get("title"))] = idx
    kjs = (judgements or {}).get("key_judgements") or []
    kj_by_id = {str(j.get("id")): j for j in kjs}
    flagged_devs, flagged_kjs, extra = set(), set(), {}
    for i in fixable:
        item = str(i["item"])
        if item in dev_by_label:
            flagged_devs.add(dev_by_label[item])
        elif item in kj_by_id:
            flagged_kjs.add(item)
        elif item == "bottom_line":
            extra["bottom_line"] = str((judgements or {}).get("bottom_line")
                                       or "")
    payload = {
        "issues": fixable,
        "developments": [{
            "index": idx,
            "label": developments[idx].get("display_label")
            or developments[idx].get("title"),
            "fact": developments[idx].get("fact"),
            "capability_delta": developments[idx].get("capability_delta"),
            "so_what": developments[idx].get("so_what"),
        } for idx in sorted(flagged_devs)],
        "key_judgements": [{
            "id": jid, "judgement": kj_by_id[jid].get("judgement"),
            "basis": kj_by_id[jid].get("basis"),
            "assessment": kj_by_id[jid].get("assessment"),
        } for jid in sorted(flagged_kjs)],
    }
    payload.update(extra)
    print("  QA gate: {} language issue(s) -> rewrite".format(len(fixable)))
    out = _call(client, REWRITE_PROMPT, payload, 6000)
    applied = 0
    for f in ((out or {}).get("fixes") or []):
        tgt, field, text = f.get("target"), f.get("field"), f.get("new_text")
        if not text or not field:
            continue
        if tgt == "dev":
            try:
                idx = int(f.get("id"))
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(developments) and field in (
                    "fact", "capability_delta", "so_what"):
                developments[idx][field] = text
                applied += 1
        elif tgt == "kj":
            j = kj_by_id.get(str(f.get("id")))
            if j is not None and field in ("judgement", "basis", "assessment"):
                j[field] = text
                applied += 1
        elif tgt == "bottom_line" and judgements is not None:
            judgements["bottom_line"] = text
            applied += 1
    return applied


def gate_key_judgements(judgements, issues):
    """Kapu, nem labjegyzet: ami az atiras utan is olyat allit, amit a sajat
    gap-listank ismeretlennek mond — vagy beszerzesi adatbol allit harci
    kepesseget —, az nem jelenhet meg veglegesitett iteletkent."""
    if not judgements:
        return []
    blocked = {}
    for i in issues:
        if any(i["check"].startswith(p) for p in KJ_BLOCKING):
            blocked.setdefault(str(i["item"]), []).append(i["check"])
    if not blocked:
        return []
    kept, review = [], []
    for j in (judgements.get("key_judgements") or []):
        reasons = blocked.get(str(j.get("id")))
        if reasons:
            j["review_reasons"] = reasons
            review.append(j)
        else:
            kept.append(j)
    judgements["key_judgements"] = kept
    judgements["judgements_requiring_review"] = review
    return review


def mark_unresolved(before, after):
    keys = {(i["check"], str(i["item"])) for i in before}
    for i in after:
        if (i["check"], str(i["item"])) in keys and any(
                i["check"].startswith(p) for p in REWRITABLE):
            i["check"] += " — unresolved after rewrite; analyst review required"
    return after
