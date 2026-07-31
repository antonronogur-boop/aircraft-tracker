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


def _window(start, end):
    """Szallitasi ablak szoveggé: a hianyzo zaroev ne "2027–None" legyen."""
    if not start:
        return None
    return "{}–{}".format(start, end) if end else "from {}".format(start)


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
            act = fl.get("active") or 0
            oo = fl.get("on_order") or 0
            entries.append({
                "type_id": tid, "type": t.get("name") or tid,
                # A katalogus-baseline ORSZAGOS/HADERONEMI szintu. Egy
                # egyseg-szintu esemeny (egy szazad utolso gepe) NEM jelenti,
                # hogy az orszagos allomany nulla — a 0 ertek ilyenkor
                # hianyzo adat, nem teny.
                "baseline_missing": bool(act == 0 and oo == 0),
                "domain": domain_of(best, types_by_id),
                "active": fl.get("active") or 0,
                "on_order": fl.get("on_order") or 0,
                "stored": fl.get("stored") or 0,
                "this_week_stage": stage_of(best),
                "this_week_quantity": best.get("quantity"),
                "expected_ioc_year": best.get("expected_ioc_year"),
                "delivery_window": _window(best.get("delivery_start_year"),
                                           best.get("delivery_end_year")),
            })
        if not entries:
            continue
        entries.sort(key=lambda x: -(x["on_order"] + x["active"]))
        c = countries_by_id.get(cid) or {}
        rows.append({"country_id": cid, "country": c.get("name") or cid,
                     "region": c.get("region"), "entries": entries[:6],
                     "baseline_scope": "national fleet baseline (catalogue, "
                                       "open sources) — not unit-level",
                     "_weight": sum(e["on_order"] + e["active"] for e in entries)})
    rows.sort(key=lambda r: -r["_weight"])
    for r in rows:
        r.pop("_weight", None)
    return rows[:max_countries]


def capability_timeline(developments, events, types_by_id, countries_by_id,
                        horizon=2035):
    """Kepesseg-hatalybalepesi idovonal a FEJLEMENYEKBOL.

    A korabbi valtozat nyers esemenyekbol epult, es a KC-46 RVS 2.0 retrofit
    kezdetet "first delivery"-kent irta ki — miközben ugyanabban a jelentesben
    89 KC-46 mar aktiv allomanyban van. Egy upgrade-milestone NEM uj gep
    erkezese; a megnevezes az eletciklus-stadiumbol szarmazik."""
    basis_by_stage = {
        "upgrade_programme": "upgrade milestone",
        "retirement": "withdrawal milestone",
        "ioc": "declared IOC", "foc": "full operational capability",
        "delivery": "delivery", "production": "production start",
    }
    out = []
    for d in (developments or []):
        year = (d.get("meaningful_capability_year")
                or d.get("expected_ioc_year") or d.get("ioc_year")
                or d.get("first_delivery_year"))
        try:
            year = int(year)
        except (TypeError, ValueError):
            continue
        if not (2000 <= year <= horizon):
            continue
        stage = d.get("lifecycle_stage") or "other"
        if d.get("meaningful_capability_year"):
            basis = "meaningful capability"
        elif d.get("expected_ioc_year") or d.get("ioc_year"):
            basis = "expected IOC"
        elif stage in basis_by_stage:
            basis = basis_by_stage[stage] + " begins"
        else:
            basis = "first delivery"
        out.append({"year": year, "basis": basis,
                    "label": d.get("display_label") or d.get("title"),
                    "domain": d.get("capability_domain"),
                    "stage": stage,
                    "quantity": None,
                    "is_withdrawal": stage in ("retirement", "loss")})
    if not out:
        # Fallback: nyers esemenyek, de ugyanazzal a stadium-tudatos logikaval.
        for e in (events or []):
            year = e.get("expected_ioc_year") or e.get("delivery_start_year")
            try:
                year = int(year)
            except (TypeError, ValueError):
                continue
            if not (2000 <= year <= horizon):
                continue
            st = stage_of(e)
            c = countries_by_id.get(e.get("country_id") or "") or {}
            t = types_by_id.get(e.get("type_id") or "") or {}
            out.append({
                "year": year,
                "basis": ("expected IOC" if e.get("expected_ioc_year")
                          else basis_by_stage.get(st, "first delivery")),
                "label": "{} {}".format(c.get("name") or "?",
                                        t.get("name") or "?"),
                "domain": domain_of(e, types_by_id), "stage": st,
                "quantity": e.get("quantity"),
                "is_withdrawal": st in ("retirement", "loss")})
    out.sort(key=lambda x: (x["year"], x["label"] or ""))
    return out


def maturity_matrix(developments):
    """Kepesseg-domain x programme-erettseg — CSAK a kepessegBEVEZETESI
    eletciklusra. A kivonas (retirement/loss) parhuzamos, de mas folyamat:
    az Intent -> Committed -> Contracted -> Fielding -> Operational lanc nem
    ertelmezheto ra, ezert kulon retegbe kerul."""
    grid, withdrawal = {}, []
    for d in developments:
        dom = d.get("capability_domain") or "other"
        stage = d.get("lifecycle_stage") or "other"
        label = d.get("display_label") or d.get("title")
        if stage in ("retirement", "loss"):
            withdrawal.append({
                "domain": dom, "label": label, "stage": stage,
                "effect_timing": d.get("effect_timing"),
                "note": (d.get("capability_delta") or "")[:160]})
            continue
        mat = STAGE_MATURITY.get(stage, "Intent")
        grid.setdefault(dom, {}).setdefault(mat, []).append(label)
    return {"introduction": grid, "withdrawal": withdrawal}


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
     "first_delivery_year": <int or null — when the first airframe/kit is handed over>,
     "ioc_year": <int or null — when the first unit is declared operational>,
     "meaningful_capability_year": <int or null — when the capability is militarily usable at scale (crews, weapons, sustainment)>,
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
- CONTRACT != DELIVERY != OPERATIONAL CAPABILITY. Give the three dates
  separately where reported. effect_timing describes MEANINGFUL CAPABILITY,
  not first delivery: a 2028 first delivery of an immature type whose engine
  and weapons integration are unresolved is NOT a 1-3 year effect. If only the
  delivery year is known, say so in effect_timing_basis and stay conservative.
- UNKNOWN ACTOR -> NO ACTOR BASELINE. If the customer, operator or recipient
  is undisclosed, you may NOT assert anything about their existing inventory,
  their prior capability level or what this adds for them ("currently operates
  no X", "a previously AEW&C-deficient state"). State the contract fact and
  put the identity in the intelligence gap. The fleet_baseline block is only
  valid for a NAMED country.
- LIFECYCLE HONESTY: set lifecycle_stage from what is evidenced, not from the
  event_type label. If no contract date, value or signing party is reported,
  it is a plan — use selection or requirement, not contract_signed. Never let
  your own narrative contradict the stage you assigned.
- CERTIFICATION IS NOT COMPLETION: an upgrade "will remove" a restriction only
  after operational clearance. Write "is designed to remove ... subject to
  certification and operational clearance".
- A CONTRACT TO ESTABLISH A CAPABILITY IS NOT THE CAPABILITY. Depot, training
  or infrastructure awards start a process: use future tense ("will establish",
  "once stood up"), never "establishes domestic heavy maintenance capability".
- KEEP FIGURES WITH THEIR PROGRAMME. Never carry a date, quantity or value
  from one programme into a statement about another.
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
- INTELLIGENCE GAPS MUST NAME THE RIGHT PROGRAMME. Every figure or date in a
  gap must belong to the programme it is attributed to; never mix milestones
  from two programmes in one gap statement.
- If the period supports NO real judgement, return one saying exactly that and
  what would be needed. Do not force a narrative: if nothing happened in
  fighters this week, write no fighter judgement."""



# --------------------------------------------------------------------------
# Determinisztikus konzisztencia-kenyszerek
#
# A narrativa es a strukturalt mezok nem mondhatnak ellent egymasnak. Ahol a
# szoveg maga cafolja a cimket (a KAAN "production plan" es a francia H160M
# "no contract date or value" contract_signed jelolessel), ott a kod
# visszaminositi a stadiumot — lathato indoklassal.
# --------------------------------------------------------------------------

PLAN_LANGUAGE_RX = re.compile(
    r"\bno (?:formal )?contract (?:date|value|signature)\b|"
    r"\bplans? to (?:order|procure|acquire|buy)\b|\bplanned (?:order|serial "
    r"production|production)\b|\btargeted for\b|\bintends to\b|"
    r"\btreated as plan\b|\bno contract value is reported\b|"
    r"\bnot yet signed\b|\bformal (?:production )?contract .{0,30}would\b",
    re.I)
CONTRACT_EVIDENCE_RX = re.compile(
    r"\bsigned a contract\b|\bcontract (?:was )?signed\b|\bawarded\b|"
    r"\bcontract award\b|\bfirm-fixed-price\b|\bbooked\b", re.I)
UNKNOWN_ACTOR_RX = re.compile(
    r"\b(undisclosed|unidentified|unnamed|not disclosed|not identified)\b",
    re.I)
ACTOR_BASELINE_RX = re.compile(
    r"\b(currently (?:operates|has|holds) no|operates no|has no .{0,25}"
    r"(?:in service|on order)|previously .{0,20}-deficient|"
    r"first .{0,25}(?:for|in) (?:the|this) (?:operator|country|air force)|"
    r"no .{0,20}aircraft (?:currently )?(?:in service|on order))\b", re.I)
CATEGORICAL_FIX_RX = re.compile(
    r"\b(?:will|would)\s+(?:remove|eliminate|resolve|clear)\b", re.I)
CLEARANCE_HEDGE_RX = re.compile(
    r"subject to (?:certification|clearance|testing)|once (?:certified|cleared|"
    r"fielded)|pending (?:certification|clearance)|is designed to", re.I)
PRESENT_ESTABLISH_RX = re.compile(
    r"\bestablishes\s+(?:[\w-]+\s+){0,3}(?:capability|capacity|depot)\b",
    re.I)

_TIMING_ORDER = ["immediate", "<12 months", "1-3 years", ">3 years", "unknown"]


def _timing_from_year(year, now_year=None):
    """A KEPESSEG hatalybalepese a mervado, nem a szerzodes datuma."""
    if not year:
        return None
    now_year = now_year or datetime.now().year
    delta = int(year) - now_year
    if delta <= 0:
        return "immediate"
    if delta <= 1:
        return "<12 months"
    if delta <= 3:
        return "1-3 years"
    return ">3 years"


def _enforce_lifecycle(d):
    """Ha a narrativa cafolja a stadiumot, a stadium veszit."""
    text = " ".join(str(d.get(k) or "") for k in
                    ("fact", "capability_delta", "so_what", "lineage_note"))
    if d.get("lifecycle_stage") in ("contract_signed", "production") \
            and PLAN_LANGUAGE_RX.search(text) \
            and not CONTRACT_EVIDENCE_RX.search(text):
        d["lifecycle_stage"] = "selection"
        d["auto_adjustment"] = _add_adj(
            d, "lifecycle downgraded to selection: the narrative reports a "
               "plan or intent, with no contract date, value or signing party")


def _enforce_effect_timing(d):
    """A hatalybalepes a MEANINGFUL CAPABILITY eve szerint szamol; ha csak
    elso atadas ismert, az onmagaban nem tesz egy eromuvi-fegyverintegracios
    szempontbol eretlen tipust 1-3 eves hatasuva."""
    year = d.get("meaningful_capability_year") or d.get("expected_ioc_year")
    derived = _timing_from_year(year)
    if derived and derived != d.get("effect_timing"):
        d["auto_adjustment"] = _add_adj(
            d, "effect timing set to '{}' from the stated capability year {}"
               .format(derived, year))
        d["effect_timing"] = derived
    elif not year and d.get("first_delivery_year") \
            and d.get("effect_timing") in ("immediate", "<12 months",
                                           "1-3 years"):
        # Csak elso atadas ismert: konzervativ marad.
        d["auto_adjustment"] = _add_adj(
            d, "only a first-delivery year is reported; meaningful capability "
               "date unknown, so effect timing is not shortened")


def _add_adj(d, text):
    cur = d.get("auto_adjustment")
    return (cur + "; " + text) if cur else text


BOTTOM_LINE_PROMPT = """You rewrite the opening paragraph of an air force
weekly brief AFTER analytical QA. Return STRICT JSON only:
{"bottom_line": "<3-5 sentences>"}

You are given ONLY the judgements and developments that PASSED QA. Some
material was withheld from this edition; its topics are listed in
"withheld_topics".

RULES:
- Use nothing but the passed content. Do NOT restate, summarise, allude to or
  re-derive any withheld topic — not even in weaker wording. If a withheld
  topic was the week's biggest story, the correct brief says the period's
  assessable developments were smaller, and notes that one item is held for
  analyst review.
- Do not introduce numbers, dates or programme names that are absent from the
  passed content.
- If volume_not_comparable is true, do not explain event-count changes with a
  cause.
- Sober, factual, no adjectives of scale that the data does not support."""


def rebuild_bottom_line(client, judgements, developments, stats):
    """A QA-KAPU NEM MEGKERULHETO. Ha egy iteletet visszatartunk, a nyitó
    bekezdes nem csempeszheti vissza ugyanazt az allitast — ezert a bottom
    line a kapu UTAN, kizarolag az atment tartalombol keszul ujra."""
    withheld = (judgements or {}).get("judgements_requiring_review") or []
    if client is None or not judgements or not withheld:
        return 0
    passed_kjs = [{k: j.get(k) for k in ("id", "domain", "judgement",
                                         "confidence", "effect_timing")}
                  for j in (judgements.get("key_judgements") or [])]
    passed_devs = [{k: d.get(k) for k in ("title", "capability_delta",
                                          "effect_timing", "confidence",
                                          "lifecycle_stage")}
                   for d in (developments or [])]
    payload = {
        "key_judgements": passed_kjs,
        "developments": passed_devs,
        "withheld_topics": [str(j.get("judgement") or "")[:120]
                            for j in withheld],
        "volume_not_comparable": bool((stats or {}).get(
            "volume_not_comparable")),
    }
    print("  Bottom line: rebuilding from QA-passed content only "
          "({} withheld)".format(len(withheld)))
    out = _call(client, BOTTOM_LINE_PROMPT, payload, 2000)
    if out and out.get("bottom_line"):
        judgements["bottom_line"] = out["bottom_line"]
        judgements["bottom_line_rebuilt"] = True
        return 1
    return 0


def check_bottom_line_leak(judgements):
    """Vedohalo a kapu moge: ha a nyitó bekezdes tartalmi atfedest mutat egy
    visszatartott itelettel, azt jelezzuk (es a jelentes publikalja)."""
    withheld = (judgements or {}).get("judgements_requiring_review") or []
    bl = str((judgements or {}).get("bottom_line") or "")
    if not withheld or not bl:
        return []
    stop = {"the", "and", "that", "with", "for", "from", "this", "its", "are",
            "was", "were", "has", "have", "not", "but", "which", "would",
            "will", "been", "than", "into", "over", "all", "any", "our"}

    def toks(t):
        return {w for w in re.findall(r"[a-z0-9\-]{4,}", t.lower())
                if w not in stop}

    bl_t = toks(bl)
    out = []
    for j in withheld:
        jt = toks(str(j.get("judgement") or ""))
        if jt and len(bl_t & jt) >= 6:
            out.append({"check": "withheld judgement reappears in the bottom "
                                 "line — QA gate bypassed",
                        "item": str(j.get("id") or "KJ")})
    return out


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
        elif d.get("ioc_year"):
            d["expected_ioc_year"] = d.get("ioc_year")
        _enforce_lifecycle(d)
        _enforce_effect_timing(d)
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
# "most of the fleet" mennyisegjelzo, nem szuperlativusz — a (?!of\b) zarja ki.
SUPERL_RX = re.compile(
    r"\b(most|largest|biggest|strongest|leading)\s+(?!of\b)(?:[\w-]+\s+){0,3}"
    r"(operator|fleet|capability|air force|buyer|programme|program)\b", re.I)
# A detektorok NE tuzeljenek a sajat maguk altal eloirt javitasra: ha a
# talalatot tartalmazo mondat maga tagadja vagy korlatozza az allitast
# ("available data does not establish whether deliveries are on schedule",
# "no baseline is available to characterise this as an acceleration"), akkor
# az mar a helyes, fegyelmezett megfogalmazas.
NEGATION_RX = re.compile(
    r"\b(does not establish|do not establish|cannot be|can not be|is not "
    r"established|are not established|not confirmed|no baseline|"
    r"available data does not|not available|unknown|unverified|"
    r"does not indicate|no evidence|not stated|not reported)\b", re.I)


def _sentences(text):
    return re.split(r"(?<=[.!?])\s+", text or "")


def _flag(rx, text):
    """Igaz, ha a minta olyan mondatban szerepel, amely NEM tagadja vagy
    korlatozza az allitast."""
    for s in _sentences(text):
        if rx.search(s) and not NEGATION_RX.search(s):
            return True
    return False
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
        # KULON KEZELJUK a FACT reteget (idezett, attribualt beszamolo) es az
        # ELEMZOI reteget. A "US Air Force accelerates the F135 ECU" a tenyek
        # kozott idezet — a fegyelem az elemzoi allitasokra vonatkozik.
        text = prose(d, ("capability_delta", "so_what"))
        full = prose(d, ("fact", "capability_delta", "so_what"))
        label = d.get("display_label") or d.get("title")
        # 1. kepesseg-tulallitas beszerzesi rekordbol
        if _flag(CAPABILITY_OVERREACH_RX, text):
            issues.append(("capability claim beyond procurement evidence "
                           "(readiness/weapons/enablers unknown)", label))
        # 2. menetrend-teljesitmes allitas
        if _flag(SCHEDULE_RX, text):
            issues.append(("delivery events presented as schedule performance",
                           label))
        # 3. trend idosor nelkul
        if _flag(TREND_RX, text):
            issues.append(("trend claim without temporal baseline", label))
        # 4. szuperlativusz
        if _flag(SUPERL_RX, text):
            issues.append(("unqualified superlative claim", label))
        # 5. export-engedely mint uzlet
        if d.get("lifecycle_stage") == "export_approval" and \
                re.search(r"\b(contract|deal|purchase|order)\b", full, re.I) \
                and not re.search(r"clearance|approval|authoris|authoriz",
                                  full, re.I):
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
        dw = DOUBLE_WORD_RX.search(full)
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
        if _flag(TREND_RX, jt):
            issues.append(("judgement uses trend language — verify baseline",
                           label))
        if _flag(CAPABILITY_OVERREACH_RX, jt):
            issues.append(("judgement asserts combat capability from "
                           "procurement data", label))
        if _flag(SUPERL_RX, jt):
            issues.append(("unqualified superlative in judgement", label))
        if _flag(DETERMINISTIC_RX, jt):
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

    # 9. UNKNOWN ACTOR -> tilos a szereplo baseline-jarol kovetkeztetni
    for d in developments:
        full_d = prose(d, ("fact", "capability_delta", "so_what"))
        if UNKNOWN_ACTOR_RX.search(full_d) and ACTOR_BASELINE_RX.search(full_d):
            issues.append(("baseline inference about an undisclosed operator",
                           d.get("display_label") or d.get("title")))
        # 9b. kategorikus javitas-allitas hitelesites elott
        if CATEGORICAL_FIX_RX.search(full_d) and not CLEARANCE_HEDGE_RX.search(
                full_d):
            issues.append(("upgrade presented as completed before "
                           "certification/clearance",
                           d.get("display_label") or d.get("title")))
        # 9c. jelen ideju "establishes" egy meg le nem szallitott kepessegre
        if PRESENT_ESTABLISH_RX.search(full_d):
            issues.append(("a contract to build a capability described as the "
                           "capability itself (use future tense)",
                           d.get("display_label") or d.get("title")))
        # 9d. narrativa vs eletciklus
        if d.get("lifecycle_stage") in ("contract_signed", "production") \
                and PLAN_LANGUAGE_RX.search(full_d) \
                and not CONTRACT_EVIDENCE_RX.search(full_d):
            issues.append(("lifecycle stage contradicted by its own narrative",
                           d.get("display_label") or d.get("title")))

    # 9e. CROSS-PROGRAMME FIGURE: egy evszam nem vandorolhat at egyik
    # programrol a masikra. Programonkent osszegyujtjuk a sajat eveiket, majd
    # a KJ/gap mondatokban ellenorizzuk az attribuciot.
    prog_years, prog_tokens = {}, {}
    for d in developments:
        label = d.get("display_label") or d.get("title") or ""
        body = prose(d, ("fact", "capability_delta", "so_what",
                         "effect_timing_basis"))
        years = set(re.findall(r"\b(20[2-4]\d)\b", body))
        for y in (d.get("expected_ioc_year"), d.get("first_delivery_year"),
                  d.get("meaningful_capability_year")):
            if y:
                years.add(str(y))
        prog_years[label] = years
        toks = {t for t in re.findall(r"[A-Za-z][A-Za-z0-9.\-]{2,}",
                                      label + " " + str(d.get("title") or ""))
                if any(c.isdigit() for c in t) or t.isupper()}
        prog_tokens[label] = {t.lower() for t in toks}
    checked = list((judgements or {}).get("intelligence_gaps") or [])
    for j in kjs:
        checked.append(prose(j, ("judgement", "basis", "assessment")))
    for text in checked:
        for sent in _sentences(str(text)):
            low = sent.lower()
            years = set(re.findall(r"\b(20[2-4]\d)\b", sent))
            if not years:
                continue
            for label, toks in prog_tokens.items():
                if not toks or not (toks & set(re.findall(
                        r"[a-z0-9.\-]{3,}", low))):
                    continue
                stray = years - prog_years.get(label, set())
                if stray and prog_years.get(label):
                    issues.append((
                        "figure attributed to the wrong programme "
                        "(year {} does not appear in this programme's "
                        "reporting)".format(sorted(stray)[0]),
                        "{} — {}".format(label, sent[:60])))
                break

    # 9f. DEV vs KJ idozites-ellentmondas ugyanarra a programra
    dev_timing = {}
    for d in developments:
        for i in (d.get("event_ids") or []):
            dev_timing[i] = (d.get("effect_timing"),
                             d.get("display_label") or d.get("title"))
    for j in kjs:
        for i in (j.get("supporting_event_ids") or []):
            t = dev_timing.get(i)
            if t and t[0] and j.get("effect_timing") and \
                    t[0] != j.get("effect_timing"):
                issues.append((
                    "effect timing contradicts the supporting development "
                    "({} vs {})".format(j.get("effect_timing"), t[0]),
                    "{} / {}".format(j.get("id"), t[1])))
                break

    # 10. volumen mint aktivitas
    if stats and stats.get("volume_not_comparable"):
        bl = str((judgements or {}).get("bottom_line") or "")
        if re.search(r"\b(increase|surge|rose|jump|spike|decline|fell)\w*\b",
                     bl, re.I) and "collection" not in bl.lower():
            issues.append(("volume change may be presented as activity trend",
                           "bottom_line"))
    # 11. az annex esemenyszovegeiben is: kepesseg-tulallitas
    n = 0
    for e in (events or []):
        s = str(e.get("summary") or "")
        if n < 6 and _flag(CAPABILITY_OVERREACH_RX, s):
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
