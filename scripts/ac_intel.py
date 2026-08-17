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
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ac_match  # noqa: E402
import ac_programmes as acprog  # noqa: E402

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


# --------------------------------------------------------------------------
# EVIDENCIA-LANCOK — a lineage nem az event-rekordok szama
# --------------------------------------------------------------------------
#
# A W33 key judgement ket fuggetlen evidencia-lancra hivatkozott, es az
# analyst layer is "2 reports / 2 lineages"-t irt. Az annexben viszont az
# MQ-1C es az MQ-9 esemeny UGYANAZZAL A CIKKCIMMEL szerepelt:
#
#   "Iran Shows Off Wreckage of U.S. Aircraft Lost During Operation Epic Fury"
#
# Ket event-rekord egy cikkbol NEM ket fuggetlen lanc. A confidence pedig
# ezen a szamon all vagy dol, ezert a lineage-et DETERMINISZTIKUSAN kell
# szamolni, nem a modelltol elkerni.

# A forraslanc gyokere: mi az az EGY primer allitas, amit tobb lap atvesz?
ORIGIN_KIND_WEIGHT = {
    "contract_document": 3, "parliamentary_record": 3,
    "government_statement": 2, "imagery": 2, "osint_visual": 2,
    "manufacturer_release": 1, "trade_press": 1, "unknown": 1,
}


def evidence_chain_id(event, articles_by_id=None):
    """Egy esemeny forraslancanak azonositoja.

    Preferencia-sorrend:
      1. originating_evidence_id — ha az extrakcio azonositotta a primer
         forrast (gyartoi kozlemeny, DSCA-notifikacio, miniszteriumi kozlemeny)
      2. article_id — ugyanaz a cikk = ugyanaz a lanc
      3. az esemeny azonositoja — vegso esetben minden esemeny sajat lanc
    """
    oid = event.get("originating_evidence_id")
    if oid:
        return "origin:" + str(oid)
    aid = event.get("article_id")
    if aid:
        return "article:" + str(aid)
    return "event:" + str(event.get("event_id"))


def count_lineages(events, articles_by_id=None):
    """Fuggetlen forraslancok szama egy esemenyhalmazra.

    Ez a szam korlatozza a confidence-t. Determinisztikus: a modell becslese
    nem irhatja felul.

    Visszaad: (lineages, reports, note)
    """
    events = list(events or [])
    if not events:
        return 1, 0, "no source events"
    chains = {}
    for e in events:
        chains.setdefault(evidence_chain_id(e, articles_by_id), []).append(e)
    reports = len(events)
    lineages = len(chains)
    if lineages == 1 and reports > 1:
        titles = set()
        for e in events:
            art = (articles_by_id or {}).get(e.get("article_id") or "") or {}
            if art.get("title"):
                titles.add(str(art["title"])[:70])
        note = ("{} event records trace to a single source chain — one "
                "lineage, not {}".format(reports, reports))
        if titles:
            note += " (shared reporting: \"{}\")".format(
                sorted(titles)[0])
        return 1, reports, note
    return lineages, reports, ("{} event record(s) across {} independent "
                               "source chain(s)".format(reports, lineages))


def cap_confidence_by_lineage(confidence, lineages):
    """Egyetlen forraslanc a moderate szinten hatarol. Ez nem stilisztika:
    egyetlen kozlemeny nem tud 'high confidence'-et alatamasztani."""
    order = ["low", "moderate", "high"]
    if confidence not in order:
        return confidence, None
    if lineages <= 1 and confidence == "high":
        return "moderate", ("confidence capped at moderate: all supporting "
                            "reporting traces to a single evidence chain")
    return confidence, None


# --------------------------------------------------------------------------
# MILESTONE-FEGYELEM — egy timeline-sor = egy programme + egy milestone
# --------------------------------------------------------------------------
#
# A W33 timeline igy nezett ki:
#     2026  UK AH-64E complete; US +12 remanuf (delivery begins)
#     2027  US F-15EX Kadena delay; F-16 Misawa exit (delivery begins)
#
# Ket kulonbozo program ket kulonbozo milestoneja egy sorba vonva, egyetlen
# kozos "(delivery begins)" alappal — mikozben a brit atadas MEGTORTENT, az
# amerikai +12 pedig csak sole-source szandeknyilatkozat. A W34-ben ugyanez
# finomabban: "2028 Poland AH-64E MRO deal (first delivery)" — egy MRO-
# megallapodasnak nincs elso gepatadasa —, es "2029 US VC-25B delay
# (meaningful capability)" — egy KESES nem kepesseg-erkezes.

MILESTONE_LABELS = {
    "first_delivery":      "first aircraft delivery",
    "final_delivery":      "final aircraft delivery",
    "deliveries_complete": "deliveries complete",
    "ioc":                 "initial operational capability",
    "foc":                 "full operational capability",
    "meaningful_scale":    "meaningful operational scale",
    "contract_award":      "contract award",
    "production_start":    "production start",
    "mro_standup":         "support facility operational",
    "certification":       "certification / operational clearance",
    "withdrawal_start":    "withdrawal begins",
    "withdrawal_complete": "out of service",
    "loss":                "airframe loss",
    "schedule_slip":       "schedule slip",
    "selection_decision":  "selection decision",
}

# Ezek NEM kepesseg-erkezesek. Sajat savba kerulnek, vagy kimaradnak.
NOT_AN_ARRIVAL = {"schedule_slip", "withdrawal_start", "withdrawal_complete",
                  "loss", "contract_award", "selection_decision"}

# GEP-erkezes vs TAMOGATO kepesseg erkezese. Egy depot uzembe allasa valodi
# kepesseg-erkezes, de NEM gepatadas — es ami ennel fontosabb: NINCS
# gepatadasi datuma, amit kolcsonvehetne a beszerzesi programtol.
AIRFRAME_ARRIVAL = {"first_delivery", "final_delivery", "deliveries_complete",
                    "ioc", "foc", "meaningful_scale", "production_start"}
SUPPORT_ARRIVAL = {"mro_standup", "certification"}

DELAY_RX = re.compile(
    r"\b(delay\w*|slip(?:page|ped|s)?|postpon\w+|deferr\w+|"
    r"pushed (?:back|to)|behind schedule|rebaselin\w+)\b", re.I)
MRO_STANDUP_RX = re.compile(
    r"\b(mro|depot|maintenance,? repair|overhaul|service cent(?:re|er)|"
    r"support (?:centre|center|facility)|offset agreement)\b", re.I)
CERTIFICATION_RX = re.compile(
    r"\b(certif\w+|airworthiness|operational clearance|type acceptance)\b",
    re.I)


def milestone_of(item, programme_kind=None):
    """Milyen milestone EZ valojaban?

    A megnevezes az eletciklus-stadiumbol ES a programfajtabol szarmazik,
    nem egy alapertelmezett "first delivery"-bol.
    """
    explicit = item.get("milestone_kind")
    if explicit in MILESTONE_LABELS:
        return explicit
    text = " ".join(str(item.get(k) or "") for k in
                    ("fact", "capability_delta", "so_what", "summary",
                     "title", "effect_timing_basis"))
    stage = item.get("lifecycle_stage") or ""

    # A KESES a legfontosabb kulonbseg: nem kepesseg-erkezes.
    if DELAY_RX.search(text) and stage not in ("ioc", "foc"):
        return "schedule_slip"
    if stage == "loss":
        return "loss"
    if stage == "retirement":
        return ("withdrawal_complete"
                if re.search(r"\b(out of service|final|last|complete)\b",
                             text, re.I) else "withdrawal_start")
    if stage == "foc":
        return "foc"
    if stage == "ioc":
        return "ioc"
    # Egy MRO/infrastruktura-programnak nincs gepatadasa.
    if programme_kind in acprog.NO_AIRFRAME_ARRIVAL or MRO_STANDUP_RX.search(text):
        if CERTIFICATION_RX.search(text):
            return "certification"
        return "mro_standup"
    if stage == "production":
        return "production_start"
    if stage == "delivery":
        return ("deliveries_complete"
                if re.search(r"\b(final|last|complete[sd]?|concluded)\b",
                             text, re.I) else "first_delivery")
    if stage == "upgrade_programme":
        return "certification" if CERTIFICATION_RX.search(text) \
            else "first_delivery"
    if stage in ("contract_signed",):
        return "contract_award"
    if stage in ("selection", "national_approval", "export_approval"):
        return "selection_decision"
    return "first_delivery"


# --------------------------------------------------------------------------
# HATALYBALEPESI HORIZONT — konkret datumbol, IOC es FOC KULON
# --------------------------------------------------------------------------
#
# A W34-ben a VC-25B elso atadasa 2028 kozepe, IOC 2028, hasznalhato 2029 —
# az effect horizon megis ">3 years" volt. 2026 augusztusatol 2028 kozepe
# KEVESEBB, mint ket ev. A HH-60W-nel ugyanez: IOC 2029 elejen, FOC 2030,
# jelolés ">3 years".
#
# Az ok: egyetlen 'effect' fogalom probalta lefedni a legkorabbi muveleti
# hatast ES a teljes, ertelmes kepesseget. Ez a ket dolog kulon mezo.

_TIMING_ORDER_FULL = ["immediate", "<12 months", "1-3 years", ">3 years",
                      "unknown"]


def _months_until(year, now=None, fiscal=False, precision="year"):
    """Honapok szama egy evszamig.

    A KORABBI valtozat mindig az EV VEGEIG szamolt. Ez a penzugyi evnel es a
    tiszta bizonytalansagnal helyes konzervativizmus, de egy KONKRETAN
    jelentett "mid-2028 first delivery" eseten indokolatlanul kitolja a
    horizontot — igy lett a 2028-as IOC ">3 years".

    precision:
      'year'    — csak evszam ismert: az ev VEGEIG szamolunk (konzervativ)
      'mid'     — az ev kozepe jelentve ("mid-2028"): junius 30.
      'quarter' — negyedev jelentve: a negyedev vege
      'exact'   — konkret datum ismert
    """
    if not year:
        return None
    now = now or datetime.now()
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None
    if fiscal:
        end_year, end_month = year + 1, 3
    elif precision == "mid":
        end_year, end_month = year, 6
    elif precision == "quarter":
        end_year, end_month = year, 9
    else:
        end_year, end_month = year, 12
    return (end_year - now.year) * 12 + (end_month - now.month)


def _timing_from_months(months):
    if months is None:
        return None
    if months <= 0:
        return "immediate"
    if months <= 12:
        return "<12 months"
    if months <= 36:
        return "1-3 years"
    return ">3 years"


MID_YEAR_RX = re.compile(r"\bmid[- ](\d{4})|\b(\d{4})\s*(?:H1|first half)\b",
                         re.I)
QUARTER_RX = re.compile(r"\b(Q[1-4])\s*(?:of\s*)?(\d{4})|\b(\d{4})\s*Q[1-4]\b",
                        re.I)


def _precision_for(year, text):
    """Milyen pontossaggal ismerjuk ezt az evet? A szoveg mondja meg."""
    if not year:
        return "year"
    y = str(int(year))
    if re.search(r"\bmid[- ]" + y, text or "", re.I):
        return "mid"
    if re.search(r"\b(Q[1-4]\s*(?:of\s*)?" + y + r"|" + y + r"\s*Q[1-4])\b",
                 text or "", re.I):
        return "quarter"
    if re.search(r"\b(early|first half of)\s*" + y, text or "", re.I):
        return "mid"
    return "year"


def _timing_from_year(year, now=None, fiscal=False, text=None):
    """Visszafele kompatibilis burkolo a korabbi hivasokhoz."""
    return _timing_from_months(_months_until(
        year, now, fiscal, _precision_for(year, text or "")))


def orbat_delta(events, fleets, types_by_id, countries_by_id, max_countries=4,
                programmes_by_id=None):
    """ORBAT-delta — VARIANS-BIZTOS es PROGRAMME-TUDATOS.

    Harom hibat javit a korabbi valtozathoz kepest.

    1. VARIANS-OSSZECSUSZAS. A korabbi kulcs (country_id, type_id) volt, es a
       `variant` mezot a fleet-index EL IS DOBTA. Emiatt jelent meg egy 26
       gepes USAF HH-60W esemeny mellett "UH-60 Black Hawk — Active 2000", es
       egy 50 gepes brit AH-64E flotta mellett "UK AH-64 Apache — Active 100".
       Most a kulcs (country, type, variant, service), es ha az esemeny
       varians-szintu, de a baseline csak csalad-szintu, a SZAM NEM JELENIK
       MEG — helyette explicit hatokor-eltéres.

    2. OSSZEADASRA CSABITAS. A korabbi tabla "On order 190" es "This period
       contract signed x94" oszlopokat allitott egymas melle, amit az olvaso
       284-nek olvasott. Most a programme kanonikus darabszama szerepel, es a
       heti reteg EXPLICITEN mondja meg, mozdult-e a baseline (on_order_delta).

    3. STADIUM-ELLENTMONDAS. Az esemeny cimkeje (contract_signed) es a sajat
       szovege (negotiation, unconfirmed) kulonbozhetett. Most a stadium csak
       akkor jelenik meg szerzodottkent, ha van szerzodes-evidencia.
    """
    programmes_by_id = programmes_by_id or {}

    def scope_key(e):
        """Az esemeny ORBAT-hatokore. A varianst a tipusjelre normalizaljuk."""
        return (e.get("country_id"), e.get("type_id"),
                acprog.variant_key(e.get("variant_raw") or ""),
                (e.get("service") or "").strip().lower())

    touched = {}
    for e in events:
        cid, tid = e.get("country_id"), e.get("type_id")
        if not cid or not tid:
            continue
        touched.setdefault(cid, {}).setdefault(scope_key(e), []).append(e)

    # A flotta-index a TELJES hatokort megorzi, es kulon tartja a
    # csalad-szintu es a varians-szintu sorokat.
    fleet_idx, family_idx = {}, {}
    for f in fleets:
        key = (f.get("country_id"), f.get("type_id"),
               acprog.variant_key(f.get("variant") or ""),
               (f.get("service") or "").strip().lower())
        fleet_idx.setdefault(key, {})[f.get("fleet_status")] = \
            (f.get("quantity") or 0)
        fam = (f.get("country_id"), f.get("type_id"))
        family_idx.setdefault(fam, {"quantities": {}, "variants": set(),
                                    "scopes": set()})
        fs = family_idx[fam]
        fs["quantities"][f.get("fleet_status")] = \
            fs["quantities"].get(f.get("fleet_status"), 0) + (f.get("quantity") or 0)
        if f.get("variant"):
            fs["variants"].add(f.get("variant"))
        fs["scopes"].add(f.get("baseline_scope") or "national_family")

    rows = []
    for cid, per_scope in touched.items():
        entries = []
        for key, evs in per_scope.items():
            _cid, tid, var_key, svc = key
            # A "legjelentosebb" esemeny kivalasztasa a hatokorön belul.
            best = sorted(evs, key=lambda x: (
                -(float(x.get("value_usd_m") or 0)),
                -(int(x.get("quantity_claimed") or x.get("quantity") or 0))))[0]
            t = types_by_id.get(tid) or {}

            # --- baseline a PONTOS hatokorre ---
            fl = fleet_idx.get(key)
            scope_match = "exact"
            if fl is None and var_key:
                # Varians-szintu esemeny, de nincs varians-szintu baseline.
                # A csalad-szintu szamot NEM hasznaljuk fel: az a hiba, ami a
                # HH-60W melle UH-60 Active 2000-et irt.
                fl, scope_match = None, "variant_without_baseline"
            elif fl is None:
                fl = fleet_idx.get((cid, tid, "", svc)) \
                    or fleet_idx.get((cid, tid, "", ""))
                scope_match = "family" if fl else "missing"

            fam = family_idx.get((cid, tid)) or {}
            fam_variants = sorted(fam.get("variants") or [])

            act = (fl or {}).get("active") or 0
            oo = (fl or {}).get("on_order") or 0

            # --- programme-allapot: a KANONIKUS darabszam ---
            prog_ids = {e.get("programme_id") for e in evs
                        if e.get("programme_id")}
            prog = None
            if len(prog_ids) == 1:
                prog = programmes_by_id.get(next(iter(prog_ids)))
            delta = sum(int(e.get("on_order_delta") or 0) for e in evs)
            claimed = [int(e["quantity_claimed"]) for e in evs
                       if e.get("quantity_claimed") not in (None, "")]
            if not claimed:
                claimed = [int(e["quantity"]) for e in evs
                           if e.get("quantity") not in (None, "")]

            # --- stadium: csak evidenciaval szerzodott ---
            stage = stage_of(best)
            stage_note = None
            if stage in ("contract_signed", "production"):
                ok, why = acprog.contract_evidenced(best)
                if not ok:
                    stage = "selection"
                    stage_note = why

            entries.append({
                "type_id": tid,
                "type": t.get("name") or tid,
                # A megjelenitett megnevezes a KANONIKUS katalogus-nev; a
                # forras tipusjelet kulon mutatjuk. Nev alapjan itt SOHA nem
                # keresunk vissza — ez zarja le az A-100LL -> A-10 hibat a
                # megjelenitesi oldalon is.
                "variant_reported": best.get("variant_raw"),
                "service": best.get("service") or None,
                "domain": domain_of(best, types_by_id),

                # --- baseline, hatokorrel ---
                "baseline_scope_match": scope_match,
                "baseline_shown": scope_match == "exact",
                "active": act if scope_match == "exact" else None,
                "on_order": oo if scope_match == "exact" else None,
                "stored": ((fl or {}).get("stored") or 0)
                if scope_match == "exact" else None,
                "baseline_missing": scope_match == "missing",
                "baseline_note": {
                    "exact": None,
                    "variant_without_baseline": (
                        "no baseline for this variant. The catalogue holds a "
                        "family-level figure only{} — a family total is not a "
                        "valid baseline for a variant-level action and is "
                        "therefore not shown.".format(
                            " (variants on file: {})".format(
                                ", ".join(fam_variants)) if fam_variants
                            else "")),
                    "family": ("family-level baseline; this action may concern "
                               "one variant or service only"),
                    "missing": ("no catalogue baseline for this type — treat "
                                "as missing data, never as zero aircraft"),
                }[scope_match],
                "family_total_active": (fam.get("quantities") or {}).get("active"),

                # --- programme-allapot ---
                "programme_id": prog.get("programme_id") if prog else None,
                "programme_title": prog.get("title") if prog else None,
                "programme_kind": prog.get("programme_kind") if prog else None,
                "canonical_quantity": prog.get("canonical_quantity")
                if prog else None,
                "quantity_basis": prog.get("quantity_basis") if prog else None,

                # --- a HETI reteg, explicit szemantikaval ---
                "this_period_stage": stage,
                "this_period_stage_note": stage_note,
                "this_period_quantity_claimed": max(claimed) if claimed else None,
                "on_order_delta": delta,
                "baseline_moved": delta != 0,
                "period_reading": (
                    "baseline unchanged — this period's reporting restates or "
                    "confirms an existing programme"
                    if delta == 0 else
                    "baseline moves {:+d} on this period's contract evidence"
                    .format(delta)),
                "evidence_kinds": sorted({e.get("evidence_kind")
                                          or "new_event" for e in evs}),

                "expected_ioc_year": best.get("expected_ioc_year"),
                "delivery_window": _window(best.get("delivery_start_year"),
                                           best.get("delivery_end_year")),

                # --- anomalia: csak EXACT hatokorön ertelmes ---
                "baseline_anomaly": bool(
                    scope_match == "exact" and act == 0
                    and oo >= 3 * max(int(best.get("quantity") or 1), 1)
                    and oo >= 20),
                "_weight": (oo + act) if scope_match == "exact" else (
                    max(claimed) if claimed else 0),
            })
        if not entries:
            continue
        entries.sort(key=lambda x: -(x.get("_weight") or 0))
        for e in entries:
            e.pop("_weight", None)
        c = countries_by_id.get(cid) or {}
        rows.append({
            "country_id": cid, "country": c.get("name") or cid,
            "region": c.get("region"), "entries": entries[:6],
            "baseline_scope": ("baseline keyed on country + type + variant + "
                               "service; a family total is never substituted "
                               "for a variant-level figure"),
            "_weight": sum((e.get("on_order") or 0) + (e.get("active") or 0)
                           for e in entries)})
    rows.sort(key=lambda r: -r["_weight"])
    for r in rows:
        r.pop("_weight", None)
    return rows[:max_countries]


def capability_timeline(developments, events, types_by_id, countries_by_id,
                        horizon=2035, programmes_by_id=None):
    """Kepesseg-idovonal. EGY SOR = EGY PROGRAMME + EGY MILESTONE.

    Mit javit ez a korabbi valtozathoz kepest:

    * A W33 timeline egy sorba vonta ossze ket kulonbozo program ket
      kulonbozo milestoneját, egyetlen kozos alappal:
          2026  UK AH-64E complete; US +12 remanuf (delivery begins)
      — a brit atadas MEGTORTENT, az amerikai +12 viszont sole-source
      szandeknyilatkozat volt. Most minden sor onallo, sajat alappal es
      sajat evidencia-erossegggel.

    * A W34-ben "2028 Poland AH-64E MRO deal (first delivery)" szerepelt. Egy
      MRO-megallapodasnak nincs elso gepatadasa; a 2028-as atadas a 2024-es
      BESZERZESI programhoz tartozik. A milestone most a PROGRAMFAJTABOL is
      szarmazik, nem csak a stadiumbol.

    * "2029 US VC-25B delay (meaningful capability)" — egy KESES nem
      kepesseg-erkezes. A nem-erkezes tipusu milestone-ok (schedule_slip,
      withdrawal, loss) kulon savba kerulnek, es nem allnak be az
      arrival-listaba.

    Minden sor egy programot es egy milestone-t nevez meg, sajat evvel es
    ev-pontossaggal. Ha egy program tobb milestone-t is jelent (elso atadas
    2028, teljes kepesseg 2029), az KET sor.
    """
    programmes_by_id = programmes_by_id or {}
    out = []

    def add(year, kind, label, programme, domain, basis_text, source,
            confidence=None, quantity=None, note=None, allow_undated=False):
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None
        if year is not None and not (2000 <= year <= horizon):
            return
        # Egy datalhatatlan milestone NEM esik ki csendben: kiirjuk TBD-vel,
        # kulonben a tamogato program vagy elveszik, vagy — ami rosszabb —
        # kolcsonvesz egy datumot a beszerzesi programtol.
        if year is None and not allow_undated:
            return
        prec = _precision_for(year, basis_text or "") if year else "unknown"
        out.append({
            "year": year,
            "year_label": str(year) if year else "TBD",
            "year_precision": prec,
            "milestone_kind": kind,
            "milestone": MILESTONE_LABELS.get(kind, kind),
            "is_arrival": kind not in NOT_AN_ARRIVAL,
            # A KETTOS BONTAS: gep-erkezes vagy tamogato kepesseg?
            "arrival_kind": ("airframe" if kind in AIRFRAME_ARRIVAL
                             else "support" if kind in SUPPORT_ARRIVAL
                             else "none"),
            "is_airframe_arrival": kind in AIRFRAME_ARRIVAL,
            "is_withdrawal": kind in ("withdrawal_start", "withdrawal_complete",
                                      "loss"),
            "programme": programme,
            "label": label,
            "domain": domain,
            "confidence": confidence,
            "quantity": quantity,
            "note": note,
            "source_layer": source,
        })

    for d in (developments or []):
        prog_id = d.get("programme_id")
        prog = programmes_by_id.get(prog_id) if prog_id else None
        kind_of_prog = (prog or {}).get("programme_kind") \
            or d.get("programme_kind")
        label = d.get("display_label") or d.get("title")
        programme = (prog or {}).get("title") or label
        domain = d.get("capability_domain")
        basis_text = " ".join(str(d.get(k) or "") for k in
                              ("effect_timing_basis", "fact",
                               "capability_delta", "so_what"))
        conf = d.get("confidence")
        primary = milestone_of(d, kind_of_prog)

        # --- 1. nem-erkezes tipusu milestone: sajat sor, sajat cimke ---
        if primary in NOT_AN_ARRIVAL:
            year = (d.get("meaningful_capability_year")
                    or d.get("ioc_year") or d.get("expected_ioc_year")
                    or d.get("first_delivery_year"))
            add(year, primary, label, programme, domain, basis_text,
                "development", conf,
                note=("this is not a capability arrival"
                      if primary == "schedule_slip" else None))
            continue

        # --- 2. MRO / infrastruktura: NINCS gepatadas, es NEM VESZI AT a
        #        beszerzesi program atadasi datumat sem ---
        #
        # A W34-ben "2028 Poland AH-64E MRO deal (first delivery)" allt. A 2028
        # a 2024-es BESZERZESI program elso gepatadasa; az MRO-megallapodasnak
        # sajat, fuggetlen datuma van (uzembe allas / hitelesites), es ha az nem
        # ismert, akkor TBD — nem a beszerzes datuma.
        if kind_of_prog in acprog.NO_AIRFRAME_ARRIVAL \
                or primary in ("mro_standup", "certification"):
            year = (d.get("meaningful_capability_year")
                    or d.get("meaningful_scale_year") or d.get("ioc_year"))
            add(year, primary, label, programme, domain, basis_text,
                "development", conf, allow_undated=True,
                note=("support milestone — this programme has no airframe "
                      "delivery date; the acquisition programme's delivery "
                      "year is NOT applicable here"
                      if not year else
                      "support milestone — no airframe arrival"))
            continue

        # --- 3. beszerzes/upgrade: KULON SOR minden milestone-nak ---
        emitted = 0
        if d.get("first_delivery_year"):
            add(d["first_delivery_year"], "first_delivery", label, programme,
                domain, basis_text, "development", conf,
                quantity=d.get("quantity"))
            emitted += 1
        ioc = d.get("ioc_year") or d.get("expected_ioc_year")
        if ioc and ioc != d.get("first_delivery_year"):
            add(ioc, "ioc", label, programme, domain, basis_text,
                "development", conf)
            emitted += 1
        scale = (d.get("meaningful_capability_year")
                 or d.get("meaningful_scale_year") or d.get("foc_year"))
        if scale and scale not in (ioc, d.get("first_delivery_year")):
            add(scale, "meaningful_scale", label, programme, domain,
                basis_text, "development", conf)
            emitted += 1
        if not emitted:
            # Nincs egyetlen datalt milestone sem — a sor kimarad, mert egy
            # datum nelkuli "erkezes" nem informacio.
            continue

    if not out:
        # Fallback: nyers esemenyek, ugyanazzal a milestone-fegyelemmel.
        for e in (events or []):
            c = countries_by_id.get(e.get("country_id") or "") or {}
            t = types_by_id.get(e.get("type_id") or "") or {}
            label = "{} {}".format(c.get("name") or "?", t.get("name") or "?")
            prog = programmes_by_id.get(e.get("programme_id") or "")
            kind_of_prog = (prog or {}).get("programme_kind")
            kind = milestone_of(dict(e, lifecycle_stage=stage_of(e)),
                                kind_of_prog)
            basis_text = str(e.get("summary") or "")
            for year, mk in ((e.get("delivery_start_year"), "first_delivery"),
                             (e.get("expected_ioc_year"), "ioc"),
                             (e.get("meaningful_scale_year"),
                              "meaningful_scale")):
                if not year:
                    continue
                add(year, kind if kind in NOT_AN_ARRIVAL else mk, label,
                    (prog or {}).get("title") or label,
                    domain_of(e, types_by_id), basis_text, "event",
                    quantity=e.get("quantity"))

    order = {k: i for i, k in enumerate(
        ["first_delivery", "ioc", "meaningful_scale", "foc",
         "deliveries_complete", "production_start", "mro_standup",
         "certification", "contract_award", "selection_decision",
         "schedule_slip", "withdrawal_start", "withdrawal_complete", "loss"])}
    # A datalhatatlan (TBD) sorok a vegere kerulnek, nem az ev 0-ra.
    out.sort(key=lambda x: (x["year"] is None, x["year"] or 9999,
                            order.get(x["milestone_kind"], 99),
                            x["label"] or ""))
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

--- PROGRAMME vs EVENT vs EVIDENCE (the single most important distinction) ---
- AN EVENT IS NOT A PROGRAMME. Each input event carries a programme_id and the
  programme's canonical_quantity. A new article about a known programme
  CONFIRMS OR REVISES it; it never adds aircraft. If the programme already
  records 96 airframes and this week's reporting mentions 94 or 96, that is
  the SAME 96 — write "restates the existing programme of record", never
  "a further 96". Use programme_delta to describe change, and if it is zero,
  say the baseline is unchanged.
- A SUPPORT CONTRACT IS ITS OWN PROGRAMME. An MRO, depot, offset, training or
  infrastructure award belongs to a sustainment programme, not to the
  acquisition. It has NO first-aircraft-delivery milestone. Never attach the
  acquisition's delivery date to it.
- LOSSES: THREE SEPARATE LEVELS. (1) attrition — airframes were lost, this is
  observable; (2) mechanism — what caused it, usually an inference; (3) intent
  — whether an adversary deliberately and systematically denied coverage, a
  further inference again. Wreckage evidences (1) only. If the mechanism is
  unknown, say so and stop; never write that a state "demonstrated effective
  counter-X capability" or "denied persistent coverage" from loss counts.
- RECOVERED WRECKAGE IS AN OPPORTUNITY, NOT AN OUTCOME. Write "creates a
  technical exploitation opportunity", never "has exploited" or "has gained
  access to" — public display evidences possession, not exploitation.
- ONE COUNTRY IS NOT A GROUP. A single order never supports "Baltic allies",
  "several states" or "a growing number of operators". Name the actor; put the
  group question in indicators_to_watch.
- DO NOT CLAIM MEASUREMENT YOU DO NOT HAVE. "quantifiable gap" requires a
  figure, an out-of-service date or a throughput number in the reporting.
  Otherwise: "creates a credible risk of X; its duration and scale cannot yet
  be quantified".
- NEUTRAL REGISTER. Not "a token addition" but "a limited-scale contribution".
  Analytical language describes scale; it does not editorialise about it.
- TWO HORIZONS, NOT ONE. Give ioc_year (earliest operational effect) and
  meaningful_capability_year (usable at scale) separately whenever both are
  reported. A 2028 IOC is a 1-3 year effect even when full capability is 2030;
  reporting only the later date understates near-term change.
- A DELAY IS NOT AN ARRIVAL. If the news is a slip, set milestone_kind to
  "schedule_slip". Never present a delay as a capability milestone.
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
  fighters this week, write no fighter judgement.
- alternative_explanation: give a real alternative reading, or JSON null. NEVER
  the string "null", "none" or "N/A" — an empty line is better than a filled
  one that says nothing.
- ATTRITION IS NOT CAUSATION IS NOT INTENT. From losses you may judge that
  operations incurred attrition. You may NOT judge the mechanism if the
  reporting does not establish it, and you may not judge that an adversary
  deliberately denied coverage. If you find yourself writing "demonstrated
  effective counter-X", stop and write what the evidence bounds instead.
- LINEAGE IS COMPUTED, NOT ESTIMATED. Two event records drawn from one article
  are ONE evidence chain. The system recomputes this and will cap your
  confidence accordingly, so do not claim high confidence on single-chain
  support — write the moderate-confidence verb instead.
- BASELINE CHANGE IS EXPLICIT. If a programme's canonical quantity did not
  move this period, do not imply growth. "Poland's programme of record stands
  at 96" is right; "Poland's programme now totals 284" from adding weekly
  figures is the error this system exists to prevent."""



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
# ABSZOLUT fuggetlenseg-allitas: ez akkor is hibas, ha a mondat egyebkent
# feltetelesen fogalmaz ("would provide ... independent of foreign supply
# chains"), mert nem a szallitastol, hanem a FUGGOSEG feloldasatol fugg —
# amit eppen ismeretlennek jelolunk.
ABSOLUTE_INDEPENDENCE_RX = re.compile(
    r"independent of foreign|free (?:from|of) foreign|without foreign|"
    r"self-sufficien|no foreign dependenc", re.I)
# Relativ allitas: ez elfogadhato, ha feltetelesen fogalmaz.
REDUCE_DEPENDENCE_RX = re.compile(
    r"reduc\w+ (?:the )?foreign (?:supply[- ]chain )?dependenc", re.I)
DEPENDENCY_UNRESOLVED_RX = re.compile(
    r"engine (?:sourcing|supply|selection).{0,40}(?:uncertain|unresolved|"
    r"unconfirmed|not confirmed|remain)|foreign (?:technology )?dependenc"
    r"\w*.{0,30}(?:unconfirmed|not confirmed|unknown)|pending a domestic|"
    r"currently us\w+ (?:GE|General Electric|foreign)", re.I)
PRESENT_ESTABLISH_RX = re.compile(
    r"\b(?:establishes|introduces|adds|delivers|provides)\s+"
    r"(?:[\w-]+\s+){0,4}(?:capability|capacity|depot|infrastructure|"
    r"ecosystem|fleet)\b", re.I)

# --------------------------------------------------------------------------
# A W33 IRAN/MQ-9 HIBAOSZTALY: VESZTESEG != MECHANIZMUS != SZANDEK
# --------------------------------------------------------------------------
#
# A W33 key judgement magas confidence-szel azt allitotta, hogy Iran olyan
# C-UAS kepesseggel rendelkezik, amely elegendo volt a tartos MQ-9/MQ-1C
# lefedettseg MEGTAGADASAHOZ. Kozvetlenul utana a sajat Basis kimondta, hogy
# az engagement mechanism NEM ISMERT (lehet kinetikus, EW, GPS/datalink
# jamming), az Alternative Explanation pedig megengedte a balesetet, az
# uzemanyaghianyt es a navigacios hibat is. Az Intelligence Gap ugyancsak azt
# irta, hogy az irani modszer ismeretlen.
#
# A roncs BIZONYITJA a veszteseget. NEM bizonyitja
#   (a) a lefövesi/hataskifejtesi mechanizmust, sem
#   (b) azt, hogy a veszteseg SZANDEKOS, RENDSZERES megtagadas eredménye.
#
# Harom kulon szintet kell szetvalasztani:
#   1. attrition   — gepek vesztek el (megfigyelheto)
#   2. mechanism   — mi okozta (kovetkeztetes, itt ismeretlen)
#   3. intent      — szandekos, rendszerszintu megtagadas (tovabbi ugras)

# Mechanizmust vagy szandekos megtagadast allito megfogalmazasok.
MECHANISM_CLAIM_RX = re.compile(
    r"\b(?:demonstrated|demonstrates|proved|proves|confirms?|confirmed|"
    r"establishes?|shows?|showed)\s+(?:[\w,'-]+\s+){0,6}"
    r"(?:counter[- ]?(?:uas|male|air)|c-uas|air defence|air defense|"
    r"engagement|intercept\w*|shoot[- ]?down|jamming|"
    r"electronic (?:warfare|attack))\b"
    r"|\b(?:denied|denies|denying|contested and denied|"
    r"successfully denied)\s+(?:[\w,'-]+\s+){0,4}"
    r"(?:coverage|access|persistent|overflight|air ?space|orbit)\b"
    r"|\beffective (?:counter[- ]?male|counter[- ]?uas|air defence)\b"
    r"|\b(?:shot down|downed)\b(?=[^.]*\bassess)", re.I)

# A mechanizmus ismeretlensegét kimondo megfogalmazasok. Ha EZEK is ott vannak
# ugyanabban a blokkban, akkor a fenti allitas onellentmondas.
MECHANISM_UNKNOWN_RX = re.compile(
    r"\b(?:engagement|loss|attrition|downing)\s+"
    r"(?:mechanism|method|cause|means)\b[^.]{0,60}"
    r"\b(?:unknown|not (?:known|established|confirmed|determined)|unclear|"
    r"cannot be)\b"
    r"|\b(?:mechanism|method|cause) (?:is |remains )?"
    r"(?:unknown|unestablished|unclear|not established)\b"
    r"|\b(?:could be|may have been|might have been)\s+"
    r"(?:kinetic|ew|electronic|accident\w*|mechanical)"
    r"|\bwhether\b[^.]{0,50}\b(?:kinetic|jamming|electronic|accident)"
    r"|\b(?:accident|mechanical failure|fuel exhaustion|navigation\w* error)\b"
    r"[^.]{0,60}\b(?:cannot be (?:excluded|ruled out)|possible|plausible)\b",
    re.I)

# Az exploitation MEGTORTENTNEK allitasa. A nyilvanos roncsbemutatas
# LEHETOSEGET teremt; nem bizonyitja, hogy a technikai kiertekeles megtortent
# — es meg kevesbe, hogy eredmenyes volt.
EXPLOITATION_DONE_RX = re.compile(
    r"\b(?:has|have|had)\s+(?:been\s+)?(?:technically\s+)?exploit(?:ed)?\b"
    r"|\bexploitation (?:has|had) (?:occurred|taken place|been (?:conducted|"
    r"completed|achieved))\b"
    r"|\b(?:recovered|captured)\s+(?:[\w-]+\s+){0,3}"
    r"(?:wreckage|airframe|debris)\s+(?:has|have)\s+"
    r"(?:enabled|provided|yielded|given)\b"
    r"|\bgained access to\s+(?:[\w-]+\s+){0,3}"
    r"(?:technology|sensors?|mission data|source code|seeker)\b", re.I)
EXPLOITATION_HEDGE_RX = re.compile(
    r"\b(?:creates?|presents?|offers?|would (?:create|offer|provide))\s+"
    r"(?:[\w-]+\s+){0,3}(?:opportunit|potential|possibilit)"
    r"|\bmay (?:permit|enable|allow)\b|\bif exploited\b|"
    r"\bpotential(?:ly)? for exploitation\b", re.I)

# --------------------------------------------------------------------------
# EGY ESET != CSOPORT-TREND ("small Baltic NATO allies could be fielding...")
# --------------------------------------------------------------------------
# A W33-ban EGY litvan Merops-rendelesbol "small Baltic NATO allies" tobbes
# szamu allitas lett. Egy orszag nem tobb orszag.
PLURAL_ACTOR_RX = re.compile(
    r"\b(?:baltic|nordic|balkan|gulf|visegrad|benelux|central european|"
    r"eastern european|southern european|small)\s+"
    r"(?:nato\s+|eu\s+)?(?:allies|states|countries|members|nations|"
    r"air forces|operators)\b"
    r"|\b(?:several|multiple|a (?:number|growing number) of|"
    r"an increasing number of)\s+(?:[\w-]+\s+){0,2}"
    r"(?:allies|states|countries|members|nations|operators|air forces)\b",
    re.I)
# Az orszagnevek szamlalasahoz: ha csak EGY nevezett orszag van a blokkban,
# a tobbes szamu csoport-allitas nem all meg.
_COUNTRY_NAME_RX = None  # lusta inicializalas a NATO/EU listakbol


def _named_countries(text):
    """A blokkban NEVEZETT orszagok halmaza (NATO+EU listabol)."""
    global _COUNTRY_NAME_RX
    if _COUNTRY_NAME_RX is None:
        names = sorted({n for n in (NATO_MEMBERS | EU_MEMBERS)
                        if len(n) >= 5}, key=len, reverse=True)
        _COUNTRY_NAME_RX = re.compile(
            r"\b(" + "|".join(re.escape(n) for n in names) + r")\b", re.I)
    return {m.group(1).lower() for m in _COUNTRY_NAME_RX.finditer(text or "")}


# --------------------------------------------------------------------------
# KVANTIFIKALHATATLAN "QUANTIFIABLE GAP"
# --------------------------------------------------------------------------
# A W33 Hawk-kartya "quantifiable gap"-rol es "will affect throughput for at
# least the next five or more years"-rol beszelt, mikozben sem Hawk T2
# out-of-service datum, sem a valto tipus service-entry datuma, sem
# throughput-adat nem szerepelt a jelentesben.
QUANTIFIED_CLAIM_RX = re.compile(
    r"\bquantifiab\w+\b|\bquantified\b(?!\s+(?:in|by)\b)|"
    r"\bmeasurab\w+ (?:gap|shortfall|reduction|effect)\b", re.I)
DURATION_CLAIM_RX = re.compile(
    r"\b(?:for|over)\s+(?:at least\s+)?(?:the\s+)?(?:next\s+)?"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"(?:\s+or more)?\s+(?:years?|decades?)\b", re.I)
# Konkret szam, datum vagy arany, ami egy ilyen allitast alatamaszthat.
HARD_FIGURE_RX = re.compile(
    r"\b\d+\s*(?:%|per cent|percent|aircraft|airframes?|pilots?|sorties?|"
    r"hours?|students?|crews?)\b|\b(?:20\d\d)\b|\b\d+\s*(?:per|a)\s*year\b",
    re.I)
# Nyelvi redundancia: "at least five OR MORE years".
REDUNDANT_DURATION_RX = re.compile(
    r"\bat least\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    r"\s+or more\b", re.I)

# --------------------------------------------------------------------------
# RETORIKUS LEERTEKELES — a katonai elemzoi nyelv neutralis
# --------------------------------------------------------------------------
# "remains a token addition" -> "remains a limited-scale contribution".
DISMISSIVE_RX = re.compile(
    r"\b(?:a |an |mere(?:ly)? |purely |little more than a )?"
    r"token (?:addition|contribution|gesture|force|capability|buy|order)\b"
    r"|\bmerely (?:symbolic|cosmetic)\b|\bsymbolic (?:addition|gesture)\b"
    r"|\bnegligible (?:addition|contribution)\b|\bwindow[- ]dressing\b", re.I)

_TIMING_ORDER = ["immediate", "<12 months", "1-3 years", ">3 years", "unknown"]

# Szovetsegi tagsag — entity-szintu tenyellenorzeshez. Egy jelentesben a
# "NATO-adjacent Turkey" tipusu tevedes (Torokorszag 1952 ota TAG) a termek
# hitelet rontja, ezert ez KEMENY ellenorzes, nem stilisztikai kerdes.
NATO_MEMBERS = {
    "albania", "belgium", "bulgaria", "canada", "croatia", "czechia",
    "czech republic", "denmark", "estonia", "finland", "france", "germany",
    "greece", "hungary", "iceland", "italy", "latvia", "lithuania",
    "luxembourg", "montenegro", "netherlands", "north macedonia", "norway",
    "poland", "portugal", "romania", "slovakia", "slovenia", "spain",
    "sweden", "turkey", "türkiye", "turkiye", "united kingdom",
    "united states", "usa", "uk",
}
EU_MEMBERS = {
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czechia",
    "czech republic", "denmark", "estonia", "finland", "france", "germany",
    "greece", "hungary", "ireland", "italy", "latvia", "lithuania",
    "luxembourg", "malta", "netherlands", "poland", "portugal", "romania",
    "slovakia", "slovenia", "spain", "sweden",
}
# A tagsagot TAGADO vagy relativizalo megfogalmazasok.
NON_MEMBER_PHRASES = (
    "nato-adjacent", "nato adjacent", "nato-aligned", "nato aligned",
    "nato partner", "nato-partner", "non-nato", "outside nato",
    "nato candidate", "aspiring nato", "eu-adjacent", "eu-aligned",
    "eu candidate", "non-eu",
)


def alliance_check(text, countries_by_id=None):
    """Talalatok: (orszag, hibas megfogalmazas). A tagorszagokat nem szabad
    'adjacent', 'aligned', 'partner' vagy 'candidate' jelzovel illetni."""
    hits, low = [], (text or "").lower()
    for phrase in NON_MEMBER_PHRASES:
        for m in re.finditer(re.escape(phrase), low):
            window = low[max(0, m.start() - 60):m.end() + 60]
            alliance = "eu" if phrase.startswith(("eu-", "eu ", "non-eu")) \
                else "nato"
            members = EU_MEMBERS if alliance == "eu" else NATO_MEMBERS
            for country in members:
                if len(country) < 4:
                    continue
                if re.search(r"\b" + re.escape(country) + r"\b", window):
                    hits.append((country.title(), phrase, alliance.upper()))
    return hits


FISCAL_RX = re.compile(r"\b(fy|fiscal year|jfy|japanese fiscal)\b", re.I)


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


def _enforce_effect_timing(d, now=None):
    """KETTOS HORIZONT: legkorabbi muveleti hatas ES ertelmes meretu kepesseg.

    A korabbi valtozat egyetlen 'effect_timing' mezoben probalta lefedni mind
    a kettot, es a ket fogalom keveredett. Emiatt lett a VC-25B — elso atadas
    2028 kozepe, IOC 2028, hasznalhato 2029 — ">3 years", holott 2026
    augusztusatol 2028 kozepe ket even beluli. Ugyanez a HH-60W-nel (IOC 2029
    eleje, FOC 2030).

    Most ket kulon mezo keszul:

      effect_timing            — a LEGKORABBI muveleti hatas (IOC-alapu)
      full_capability_timing   — az ERTELMES meretu kepesseg (FOC / scale)

    A pontossagot a szoveg dönti el: egy konkretan jelentett "mid-2028" nem
    kerekitheto ki 2028 vegere, egy puszta "2028" viszont igen (konzervativ).
    """
    basis_text = " ".join(str(d.get(k) or "") for k in
                          ("effect_timing_basis", "fact", "capability_delta",
                           "so_what"))
    fiscal = bool(FISCAL_RX.search(basis_text))

    # --- 1. legkorabbi muveleti hatas: IOC, ennek hianyaban elso atadas ---
    early_year = d.get("ioc_year") or d.get("expected_ioc_year")
    early_basis = "declared or reported IOC"
    if not early_year:
        early_year = d.get("first_delivery_year")
        early_basis = "first delivery (no IOC reported)"
    early_months = _months_until(
        early_year, now, fiscal, _precision_for(early_year, basis_text))
    early = _timing_from_months(early_months)

    # --- 2. ertelmes meretu kepesseg: FOC / scale / meaningful ---
    full_year = (d.get("meaningful_capability_year")
                 or d.get("meaningful_scale_year") or d.get("foc_year"))
    full_months = _months_until(
        full_year, now, fiscal, _precision_for(full_year, basis_text))
    full = _timing_from_months(full_months)

    if full:
        d["full_capability_timing"] = full
        d["full_capability_year"] = full_year
        d["full_capability_months"] = full_months

    if early:
        if early != d.get("effect_timing"):
            d["auto_adjustment"] = _add_adj(
                d, "earliest-effect horizon set to '{}' ({} months to {}{}) "
                   "from the {}".format(
                       early, early_months, "FY" if fiscal else "", early_year,
                       early_basis))
        d["effect_timing"] = early
        d["effect_timing_months"] = early_months
        d["effect_horizon_basis"] = early_basis
        # Ha a ket horizont eltér, azt KI KELL IRNI — kulonben az olvaso a
        # legkorabbi datumot olvassa teljes kepessegnek.
        if full and full != early:
            d["auto_adjustment"] = _add_adj(
                d, "two horizons reported separately: earliest operational "
                   "effect {} ({}), meaningful scale {} ({})".format(
                       early, early_year, full, full_year))
    elif full:
        d["effect_timing"] = full
        d["effect_horizon_basis"] = "meaningful scale only (no IOC reported)"
    elif d.get("first_delivery_year") and d.get("effect_timing") in (
            "immediate", "<12 months", "1-3 years"):
        # Sem IOC, sem scale: konzervativ marad.
        d["auto_adjustment"] = _add_adj(
            d, "only a first-delivery year is reported; neither IOC nor "
               "meaningful-scale date is known, so the horizon is not "
               "shortened")


def _add_adj(d, text):
    cur = d.get("auto_adjustment")
    return (cur + "; " + text) if cur else text


# --------------------------------------------------------------------------
# MEGJELENITESI HIGIENIA — a "null" nem tartalom
# --------------------------------------------------------------------------
#
# A W34 briefben ez a sor szerepelt:
#     Alternative explanation: null
# A frontend helyesen elrejti a hianyzo erteket, de a modell nem JSON-null-t,
# hanem a "null" SZOVEGET adta vissza — az pedig igaz erteku string. Ha nincs
# alternativ magyarazat, a sor egyszeruen ne keletkezzen; a "None" kiirasa
# ugyanolyan csunya egy briefingben.

_NULLISH = {"null", "none", "n/a", "na", "nil", "nincs", "-", "--", "",
            "not applicable", "no alternative", "no alternative explanation",
            "undefined", "unknown alternative"}


def scrub_nullish(obj, fields=None):
    """A "null"/"none"/"n/a" SZOVEGEK valodi None-ra alakitasa, rekurzivan.

    Listaknal a nullish elemek kiesnek; ha a lista ures marad, a mezo None
    lesz — igy a frontend meglevo `{x && ...}` orzese eleg."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if fields and k not in fields:
                obj[k] = scrub_nullish(v)
                continue
            obj[k] = scrub_nullish(v)
        return obj
    if isinstance(obj, list):
        cleaned = [scrub_nullish(x) for x in obj]
        cleaned = [x for x in cleaned if x not in (None, "", [])]
        return cleaned or None
    if isinstance(obj, str):
        return None if obj.strip().lower() in _NULLISH else obj
    return obj


def scrub_report_payload(payload):
    """A teljes payload higieniaja kozvetlenul mentes elott."""
    if not isinstance(payload, dict):
        return payload
    for key in ("key_judgements", "judgements_requiring_review"):
        for j in (payload.get(key) or []):
            scrub_nullish(j)
    for key in ("developments", "background_items"):
        for d in (payload.get(key) or []):
            scrub_nullish(d)
    for w in (payload.get("priority_watch") or []):
        scrub_nullish(w)
    payload["intelligence_gaps"] = scrub_nullish(
        payload.get("intelligence_gaps")) or []
    if isinstance(payload.get("bottom_line"), str):
        payload["bottom_line"] = scrub_nullish(payload["bottom_line"]) or ""
    return payload


# --------------------------------------------------------------------------
# A DEV-SZINTU STADIUM-JAVITAS VISSZAIRASA AZ ESEMENYEKRE
# --------------------------------------------------------------------------
#
# Ez a fuggveny szunteti meg az uzbeg ketallapotusagot. A `_enforce_lifecycle`
# eddig CSAK a developmentet minositette vissza (contract_signed ->
# selection), de az ORBAT es az annex a NYERS esemenyekbol epult — igy a
# jelentes egyik fele "negotiation, unconfirmed"-et irt, a masik
# "Contract signed x24"-et.

def propagate_stage_corrections(developments, events):
    """A development elemzoi stadium-javitasat visszairja a sajat esemenyeire.

    Az esemeny eredeti cimkeje megorzodik (`lifecycle_stage_reported`), hogy a
    beavatkozas atlathato legyen — a felderitoi termek nem torol nyomot.

    Visszaad: a javitott (event_id, from, to) harmasok listaja.
    """
    ev_by_id = {e.get("event_id"): e for e in (events or [])}
    applied = []
    for d in (developments or []):
        dev_stage = d.get("lifecycle_stage")
        if not dev_stage:
            continue
        for i in (d.get("event_ids") or []):
            e = ev_by_id.get(i)
            if e is None:
                continue
            cur = e.get("lifecycle_stage")
            if cur == dev_stage:
                continue
            # Csak LEFELE minositunk. Egy elemzoi osszevonas nem lephet elore
            # a szerzodottseg iranyaba az esemeny sajat evidenciaja nelkul.
            rank = {s: i2 for i2, s in enumerate(STAGE_ORDER)}
            if rank.get(dev_stage, 99) < rank.get(cur, 99):
                e.setdefault("lifecycle_stage_reported", cur)
                e["lifecycle_stage"] = dev_stage
                e["stage_correction_note"] = (
                    "downgraded from '{}' by the analyst layer: {}".format(
                        cur, (d.get("auto_adjustment")
                              or "narrative does not evidence the labelled "
                                 "stage")))
                # A baseline-delta ujraszamol: nem szerzodott stadium -> 0.
                ok, why = acprog.contract_evidenced(e)
                if not ok and e.get("on_order_delta"):
                    e["on_order_delta"] = 0
                    e["stage_correction_note"] += \
                        "; on-order delta reset to 0 ({})".format(why)
                applied.append((i, cur, dev_stage))
    return applied


# --------------------------------------------------------------------------
# SINCE LAST WEEK — longitudinalis kovetes
# --------------------------------------------------------------------------
#
# A W33 es a W34 egyarant jo HETI PILLANATFELVETEL, de gyenge LONGITUDINALIS
# TRACKER: nem mondja meg, mi valtozott az elozo het OTA. Ez a blokk maximum
# 4-6 sor, es ez teszi a terméket heti hirszerzo termékké.

_WATCH_STATE = {
    "resolved":  "resolved — the next observable occurred",
    "escalated": "escalated — new evidence strengthened it",
    "unchanged": "unchanged — no new evidence this period",
    "dropped":   "dropped — no longer assessed as priority",
    "new":       "new this period",
}


def _norm_key(text):
    """Osszehasonlithato kulcs egy programnevbol/temabol."""
    return " ".join(sorted(
        w for w in re.findall(r"[a-z0-9\-]{3,}", str(text or "").lower())
        if w not in _KW_STOP))[:120]


def since_last_week(current, previous, max_rows=6):
    """Programme-szintu diff az ELOZO HETI PUBLIKALT jelentes payloadjabol.

    `current` / `previous`: report payload dictek.

    Visszaad: {"programmes": [...], "watch": [...], "note": str}

    A sorok szandekosan rovidek: ez nem ujabb harom oldal, hanem 4-6 sor.
    """
    if not previous:
        return {"programmes": [], "watch": [], "note":
                "no prior report on file — longitudinal comparison begins next "
                "period"}

    def dev_index(payload):
        out = {}
        for d in (payload or {}).get("developments") or []:
            key = d.get("programme_id") or _norm_key(
                d.get("display_label") or d.get("title"))
            if not key:
                continue
            out[key] = d
        return out

    cur_d, prev_d = dev_index(current), dev_index(previous)
    rows = []
    for key in sorted(set(cur_d) | set(prev_d)):
        c, p = cur_d.get(key), prev_d.get(key)
        label = ((c or p).get("display_label") or (c or p).get("title") or key)

        def state(d):
            if not d:
                return None
            return "{} · {}".format(
                STAGE_LABELS.get(d.get("lifecycle_stage") or "", "—"),
                d.get("confidence") or "—")

        if c and not p:
            change = "new to the reporting this period"
        elif p and not c:
            change = "no new evidence this period"
        else:
            bits = []
            if c.get("lifecycle_stage") != p.get("lifecycle_stage"):
                bits.append("lifecycle {} -> {}".format(
                    STAGE_LABELS.get(p.get("lifecycle_stage") or "", "—"),
                    STAGE_LABELS.get(c.get("lifecycle_stage") or "", "—")))
            if c.get("confidence") != p.get("confidence"):
                bits.append("confidence {} -> {}".format(
                    p.get("confidence") or "—", c.get("confidence") or "—"))
            if c.get("effect_timing") != p.get("effect_timing"):
                bits.append("effect horizon {} -> {}".format(
                    p.get("effect_timing") or "—",
                    c.get("effect_timing") or "—"))
            change = "; ".join(bits) or "unchanged"
        rows.append({
            "programme": label,
            "programme_id": (c or p).get("programme_id"),
            "previous": state(p) or "not reported",
            "current": state(c) or "not reported",
            "change": change,
            "moved": change not in ("unchanged", "no new evidence this period"),
        })
    # A valodi valtozasok elore.
    rows.sort(key=lambda r: (not r["moved"], r["programme"]))

    # --- az elozo heti watchok allapota ---
    prev_watch = (previous or {}).get("priority_watch") or []
    cur_watch = (current or {}).get("priority_watch") or []
    cur_keys = {_norm_key(w.get("issue")): w for w in cur_watch}
    watch = []
    for w in prev_watch:
        k = _norm_key(w.get("issue"))
        match = cur_keys.pop(k, None)
        if match:
            prev_rank = {"high": 0, "medium": 1, "low": 2}
            if prev_rank.get(match.get("impact_if_confirmed"), 3) < \
                    prev_rank.get(w.get("impact_if_confirmed"), 3):
                st = "escalated"
            else:
                st = "unchanged"
        else:
            st = "dropped"
        watch.append({"issue": w.get("issue"), "state": st,
                      "state_label": _WATCH_STATE[st],
                      "next_observable": (match or w).get("next_observable")})
    for k, w in cur_keys.items():
        watch.append({"issue": w.get("issue"), "state": "new",
                      "state_label": _WATCH_STATE["new"],
                      "next_observable": w.get("next_observable")})

    return {
        "previous_week": (previous.get("report_meta") or {}).get("week_label")
        or previous.get("week_label"),
        "programmes": rows[:max_rows],
        "watch": watch[:8],
        "note": ("Programme-level comparison against the previous published "
                 "report. 'Unchanged' means no new evidence, not that the "
                 "programme stopped."),
    }


# --------------------------------------------------------------------------
# BRIEFING VIEW — 4 slide egy 5-8 perces szobeli briefinghez
# --------------------------------------------------------------------------
#
# A 13-14 oldalas PDF marad a REFERENCE PRODUCT. Emellett kell egy nezet,
# amibol tenylegesen elo lehet adni. A negy slide szerkezete szandekosan
# szigoru: ha valami nem fer bele, az a reference productban van.
#
#   1. This week in air power   — 1 bottom line + 3 legfontosabb valtozas
#   2. What actually changed    — NOW | 1-3 YEARS | >3 YEARS, oszloponkent 1-2
#   3. Deep dive               — a het legfontosabb temaja, 4 kerdesre bontva
#   4. Watch next              — 3-5 watch + az elozo hetiek allapota

def build_briefing(week_label, judgements, developments, timeline, diff, stats):
    """A briefing-nezet adatretege. Nem hiv modellt: kizarolag a mar
    QA-n atment tartalombol valogat, hogy a kapu ne legyen megkerulhetó."""
    j = judgements or {}
    devs = list(developments or [])
    kjs = list(j.get("key_judgements") or [])

    # --- 1. slide: a het ---
    # A harom legfontosabb valtozas: szignifikancia, majd horizont szerint.
    order = {"immediate": 0, "<12 months": 1, "1-3 years": 2, ">3 years": 3,
             "unknown": 4}
    top = sorted(devs, key=lambda d: (-(d.get("significance") or 1),
                                      order.get(d.get("effect_timing"), 4)))[:3]
    slide1 = {
        "bottom_line": j.get("bottom_line") or "",
        "headline_changes": [{
            "label": d.get("display_label") or d.get("title"),
            "what": (d.get("capability_delta") or "")[:180],
            "confidence": d.get("confidence"),
            "effect_timing": d.get("effect_timing"),
            "full_capability_timing": d.get("full_capability_timing"),
            "baseline_moved": d.get("baseline_moved"),
            "significance": d.get("significance"),
        } for d in top],
        "volume": {
            "events": (stats or {}).get("events_this_week"),
            # A WoW itt is a PUBLIKALT alapon all, es ha nem hasonlithato,
            # azt kiirjuk — nem +0-t mutatunk.
            "wow": (stats or {}).get("wow"),
            "wow_basis": (stats or {}).get("wow_basis"),
            "comparable": ((stats or {}).get("collection_health") or {})
            .get("wow_comparable"),
        },
        "withheld": len(j.get("judgements_requiring_review") or []),
    }

    # --- 2. slide: NOW | 1-3 YEARS | >3 YEARS ---
    # Oszloponkent legfeljebb ket program. Az "unknown" horizont nem oszlop:
    # ami nem datalhato, az nem kepesseg-elorejelzes.
    buckets = {"now": [], "near": [], "far": []}
    for d in devs:
        t = d.get("effect_timing")
        if t in ("immediate", "<12 months"):
            key = "now"
        elif t == "1-3 years":
            key = "near"
        elif t == ">3 years":
            key = "far"
        else:
            continue
        buckets[key].append({
            "label": d.get("display_label") or d.get("title"),
            "domain": d.get("capability_domain"),
            "note": (d.get("capability_delta") or "")[:110],
            "confidence": d.get("confidence"),
            "significance": d.get("significance") or 1,
            "year": (d.get("ioc_year") or d.get("expected_ioc_year")
                     or d.get("first_delivery_year")),
        })
    for k in buckets:
        buckets[k] = sorted(buckets[k],
                            key=lambda x: -(x["significance"]))[:2]
    slide2 = {
        "columns": [
            {"key": "now", "title": "NOW", "subtitle": "in effect or <12 months",
             "items": buckets["now"]},
            {"key": "near", "title": "1–3 YEARS",
             "subtitle": "earliest operational effect", "items": buckets["near"]},
            {"key": "far", "title": ">3 YEARS",
             "subtitle": "no near-term operational effect",
             "items": buckets["far"]},
        ],
        "note": ("Placement is by EARLIEST operational effect (IOC). Where "
                 "meaningful scale comes later, both horizons are stated on "
                 "the card."),
        "undated": sum(1 for d in devs
                       if d.get("effect_timing") in (None, "", "unknown")),
    }

    # --- 3. slide: deep dive a het legfontosabb temajarol ---
    lead = top[0] if top else None
    lead_kj = None
    if lead:
        ids = set(lead.get("event_ids") or [])
        for k in kjs:
            if ids & set(k.get("supporting_event_ids") or []):
                lead_kj = k
                break
    slide3 = None
    if lead:
        # "What we don't know" — a gapek koreje, plusz a sajat QA-jelzesek.
        unknowns = []
        if lead_kj and lead_kj.get("alternative_explanation"):
            unknowns.append("Alternative reading: {}".format(
                lead_kj["alternative_explanation"]))
        for g in (j.get("intelligence_gaps") or [])[:3]:
            unknowns.append(g)
        if lead.get("independent_lineages", 1) <= 1:
            unknowns.append(
                "All supporting reporting traces to a single evidence chain; "
                "no independent confirmation is available.")
        slide3 = {
            "title": lead.get("title"),
            "programme": lead.get("programme_id"),
            "what_happened": lead.get("fact"),
            "capability_delta": lead.get("capability_delta"),
            "why_it_matters": lead.get("so_what"),
            "what_we_dont_know": unknowns[:4],
            "confidence": lead.get("confidence"),
            "effect_timing": lead.get("effect_timing"),
            "full_capability_timing": lead.get("full_capability_timing"),
            "timing_basis": lead.get("effect_timing_basis"),
            "lineage": lead.get("lineage_basis") or lead.get("lineage_note"),
            "judgement": (lead_kj or {}).get("judgement"),
        }

    # --- 4. slide: watch next + az elozo hetiek allapota ---
    slide4 = {
        "watch": [{
            "issue": w.get("issue"),
            "why": w.get("why_it_matters"),
            "next_observable": w.get("next_observable"),
            "horizon": w.get("horizon"),
            "impact": w.get("impact_if_confirmed"),
        } for w in (j.get("priority_watch") or [])[:5]],
        "previous_watch": (diff or {}).get("watch") or [],
        "since_last_week": (diff or {}).get("programmes") or [],
    }

    return {
        "week_label": week_label,
        "slides": [
            {"n": 1, "title": "This week in air power", "body": slide1},
            {"n": 2, "title": "What actually changed", "body": slide2},
            {"n": 3, "title": "Deep dive", "body": slide3},
            {"n": 4, "title": "Watch next", "body": slide4},
        ],
        "speaking_time_estimate_min": 5 if len(devs) <= 5 else 8,
        "note": ("Derived only from QA-passed content. The full report remains "
                 "the reference product."),
    }


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


def event_payload(e, types_by_id, countries_by_id, fleets_idx,
                  programmes_by_id=None):
    c = countries_by_id.get(e.get("country_id") or "") or {}
    t = types_by_id.get(e.get("type_id") or "") or {}
    prog = (programmes_by_id or {}).get(e.get("programme_id") or "") or {}
    # A flotta-baseline hatokore: varians-szintu esemenyhez NEM adunk
    # csalad-szintu szamot. Enelkul a modell ugyanazt a hibat kapja
    # bemenetkent, amit a jelentesben javitani akarunk.
    var_key = acprog.variant_key(e.get("variant_raw") or "")
    fl = fleets_idx.get((e.get("country_id"), e.get("type_id"), var_key,
                         (e.get("service") or "").strip().lower()))
    baseline_scope = "variant" if fl else None
    if fl is None and not var_key:
        fl = fleets_idx.get((e.get("country_id"), e.get("type_id"), "", ""))
        baseline_scope = "family" if fl else None
    return {
        "event_id": e.get("event_id"),
        "country": c.get("name") or e.get("unresolved_country_name"),
        "region": c.get("region"),
        # A KANONIKUS katalogus-nev. A forras tipusjele kulon mezoben megy —
        # a modell igy nem kever csaladot es varianst.
        "aircraft": t.get("name") or e.get("unresolved_type_name"),
        "variant_reported": e.get("variant_raw"),
        "type_match_kind": e.get("type_match_kind"),
        "service": e.get("service"),
        "category": t.get("category"),
        "event_type": e.get("event_type"),
        "lifecycle_stage": stage_of(e),
        "capability_domain": domain_of(e, types_by_id),
        "quantity": e.get("quantity"),
        "quantity_claimed": e.get("quantity_claimed"),
        # A baseline-mozgas EXPLICIT. Ha 0, a modell nem irhat novekedest.
        "on_order_delta": e.get("on_order_delta") or 0,
        "value_usd_m": e.get("value_usd_m"),
        "value_type": e.get("value_type"),
        "value_currency_year": e.get("value_currency_year"),
        "event_date": e.get("event_date"),
        "announcement_date": e.get("announcement_date"),
        # --- evidencia-idorend: a heti tagsag oka lathato ---
        "evidence_kind": e.get("evidence_kind") or "new_event",
        "first_reported_at": e.get("first_reported_at"),
        "new_evidence_at": e.get("new_evidence_at"),
        "delivery_start_year": e.get("delivery_start_year"),
        "delivery_end_year": e.get("delivery_end_year"),
        "expected_ioc_year": e.get("expected_ioc_year"),
        "foc_year": e.get("foc_year"),
        "meaningful_scale_year": e.get("meaningful_scale_year"),
        "milestone_kind": e.get("milestone_kind"),
        "independent_lineages": e.get("independent_lineages") or 1,
        "confidence": e.get("confidence"),
        "summary": (e.get("summary") or "")[:400],
        # --- A TARTOS PROGRAMALLAPOT. Ez az, ami megakadalyozza, hogy a
        #     modell ugyanazt a programot minden heten ujra "megvegye". ---
        "programme": ({
            "programme_id": prog.get("programme_id"),
            "title": prog.get("title"),
            "kind": prog.get("programme_kind"),
            "canonical_quantity": prog.get("canonical_quantity"),
            "quantity_basis": prog.get("quantity_basis"),
            "lifecycle_stage": prog.get("lifecycle_stage"),
            "contract_date": prog.get("contract_date"),
            "first_reported_at": prog.get("first_reported_at"),
            "evidence_count": prog.get("evidence_count"),
            "note": ("This programme is already on record. This week's "
                     "reporting updates or confirms it — it does not add "
                     "aircraft to the baseline."),
        } if prog else None),
        "fleet_baseline": ({"active": fl.get("active") or 0,
                            "on_order": fl.get("on_order") or 0,
                            "stored": fl.get("stored") or 0,
                            "scope": baseline_scope} if fl else {
            "scope": None,
            "note": ("no baseline at this scope. A family-level total is NOT "
                     "a valid baseline for a variant-level action — do not "
                     "assume a figure.")}),
    }


def build_developments(client, events, types_by_id, countries_by_id, fleets,
                       max_events=26, programmes_by_id=None,
                       articles_by_id=None):
    if client is None or not events:
        return [], []
    # A flotta-index HATOKOR-TUDATOS: (orszag, tipus, varians, haderonem).
    # A korabbi (orszag, tipus) kulcs eldobta a variant mezot, es igy adott
    # csalad-szintu szamot varians-szintu esemenyhez.
    fleets_idx = {}
    for f in fleets:
        key = (f.get("country_id"), f.get("type_id"),
               acprog.variant_key(f.get("variant") or ""),
               (f.get("service") or "").strip().lower())
        fleets_idx.setdefault(key, {})[f.get("fleet_status")] = \
            (f.get("quantity") or 0)
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
                                        fleets_idx, programmes_by_id)
                          for e in ranked],
               "context_events": context_titles}
    print("  Developments: {} event (+{} context) -> model".format(
        len(ranked), len(context_titles)))
    out = _call(client, DEV_PROMPT, payload, 16000)
    if not out:
        return [], []
    devs = out.get("developments") or []
    by_id = {e.get("event_id"): e for e in ranked}
    for d in devs:
        scrub_nullish(d)
        try:
            d["significance"] = max(1, min(5, int(d.get("significance") or 1)))
        except (TypeError, ValueError):
            d["significance"] = 1

        src_events = [by_id[i] for i in (d.get("event_ids") or []) if i in by_id]

        # ---- LINEAGE: DETERMINISZTIKUS, nem a modell becslese ----
        # A W33-ban a modell 2 fuggetlen lancot allitott az iráni MQ-9/MQ-1C
        # veszteseghez, mikozben mindket event UGYANABBOL a cikkbol szarmazott.
        # A szamot ezert a forraslancokbol szamoljuk, es a modell erteket
        # legfeljebb LEFELE fogadjuk el.
        actual_lin, actual_rep, lin_note = count_lineages(
            src_events, articles_by_id)
        try:
            model_lin = int(d.get("independent_lineages") or 1)
        except (TypeError, ValueError):
            model_lin = 1
        d["reports_count"] = max(actual_rep, 1)
        d["independent_lineages"] = min(max(model_lin, 1), actual_lin)
        if model_lin > actual_lin:
            d["auto_adjustment"] = _add_adj(
                d, "independent lineages corrected {} -> {}: {}".format(
                    model_lin, actual_lin, lin_note))
        d["lineage_basis"] = lin_note
        # A confidence-t a lanc korlatozza.
        capped, why = cap_confidence_by_lineage(
            d.get("confidence"), d["independent_lineages"])
        if why:
            d["confidence"] = capped
            d["auto_adjustment"] = _add_adj(d, why)

        # ---- PROGRAMME-KOTES: a fejlemeny a tartos programra hivatkozik ----
        prog_ids = {e.get("programme_id") for e in src_events
                    if e.get("programme_id")}
        if len(prog_ids) == 1:
            pid = next(iter(prog_ids))
            d["programme_id"] = pid
            prog = (programmes_by_id or {}).get(pid) or {}
            d["programme_kind"] = prog.get("programme_kind")
            d["programme_canonical_quantity"] = prog.get("canonical_quantity")
        elif len(prog_ids) > 1:
            d["programme_ids"] = sorted(prog_ids)
            d["auto_adjustment"] = _add_adj(
                d, "development spans {} programmes — figures are not "
                   "aggregated across them".format(len(prog_ids)))
        # ---- BASELINE-MOZGAS: explicit, es nulla is informacio ----
        d["programme_delta"] = sum(int(e.get("on_order_delta") or 0)
                                   for e in src_events)
        d["baseline_moved"] = d["programme_delta"] != 0
        # ---- EVIDENCIA-JELLEG: e heti esemeny vagy regi esemeny uj igazolasa?
        kinds = {e.get("evidence_kind") or "new_event" for e in src_events}
        d["evidence_kinds"] = sorted(kinds)
        if kinds and kinds <= {"new_confirmation", "reassessment"}:
            d["is_new_confirmation"] = True
            occurred = [parse_day(e.get("event_date")) for e in src_events]
            occurred = [o for o in occurred if o]
            if occurred:
                d["occurred_year"] = min(occurred).year
        d["milestone_kind"] = milestone_of(d, d.get("programme_kind"))
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
# Tagadja-e a gap-mondat az ismeretet? A korabbi, szo szerinti minta
# ("not confirmed") kihagyta a "No delivery schedule ... has been confirmed"
# format, ezert a helyesen hedgelt iteletek is atmentek — illetve a valodi
# ellentmondasok NEM buktak el.
GAP_DENIAL_RX = re.compile(
    r"\b(no|not|never|none|unknown|undisclosed|unconfirmed|unavailable|"
    r"cannot|impossible|unclear|lacks?)\b", re.I)
NEGATION_RX = re.compile(
    r"\b(does not establish|do not establish|cannot be|can not be|is not "
    r"established|are not established|not confirmed|no baseline|"
    r"available data does not|not available|unknown|unverified|"
    r"does not indicate|no evidence|not stated|not reported)\b", re.I)


_KW_STOP = {"the", "and", "that", "with", "for", "from", "this", "its", "are",
            "was", "were", "has", "have", "not", "but", "which", "would",
            "will", "been", "than", "into", "over", "all", "any", "our",
            "available", "reporting", "data", "does", "establish", "confirmed"}


def _kw(text):
    return {w for w in re.findall(r"[a-z0-9\-]{4,}", (text or "").lower())
            if w not in _KW_STOP}


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
# Az atiras utan maradt nyelvtani torzsek ("A operational KAAN fleet").
ARTICLE_RX = re.compile(r"\bA\s+(?=[aeiouAEIOU])[a-z]", re.M)


DESIGNATION_RX = re.compile(
    r"\b(?:[A-Z]{1,4}[- ]?\d{1,4}[A-Z]{0,3}|[A-Z]{2,4}\d{2,5})\b")
# Altalanos, minden hetre ervenyes megnevezesek, amelyek nem igenyelnek
# forras-egyezest (szervezetek, szabvanyok).
DESIGNATION_ALLOW = {
    "NATO", "USAF", "USN", "RAF", "JASDF", "EU", "UN", "FMS", "IOC", "FOC",
    "CDR", "RFI", "RFP", "IDIQ", "DSCA", "MRO", "AEW", "ISR", "BVR", "AAR",
    "UAS", "CCA", "TTP", "C2", "EW", "MOU", "LOI", "QA", "P3", "Q1", "Q2",
    "Q3", "Q4",
}


def _source_designations(events):
    """Minden tipus-/programjel, amely a HETI FORRASSZOVEGEKBEN tenylegesen
    szerepel. Ami ezen kivul esik, azt a modell a sajat emlekezetebol hozta —
    ilyenkor keletkezik a 'TEI TF-6000' tipusu, nevben kozeli, de tenyszeruen
    rossz entitas."""
    out = set()
    for e in (events or []):
        for field in ("summary", "unresolved_type_name"):
            for m in DESIGNATION_RX.findall(str(e.get(field) or "")):
                out.add(m.replace(" ", "-").upper())
    return out


def run_self_checks(developments, judgements, window_start, window_end,
                    stats=None, events=None, countries_by_id=None,
                    orbat=None):
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
        if ARTICLE_RX.search(full):
            issues.append(("grammar artifact: 'a' before a vowel — rewrite "
                           "left the sentence malformed", label))
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

    # ------------------------------------------------------------------
    # 7b. VESZTESEG != MECHANIZMUS != SZANDEK  (a W33 Iran/MQ-9 hibaosztaly)
    # ------------------------------------------------------------------
    # A roncs bizonyitja a veszteseget. Nem bizonyitja, mi okozta, es meg
    # kevesbe, hogy szandekos, rendszerszintu megtagadas eredmenye volt.
    for scope, items in (("development", developments), ("judgement", kjs)):
        for o in (items or []):
            fields = (("fact", "capability_delta", "so_what")
                      if scope == "development"
                      else ("judgement", "basis", "assessment",
                            "alternative_explanation"))
            body = prose(o, fields)
            label = (o.get("display_label") or o.get("title")
                     if scope == "development" else o.get("id"))
            # A gap-lista is szamit: ha ott all, hogy a modszer ismeretlen,
            # az ugyanugy cafolja a mechanizmus-allitast.
            with_gaps = body + " " + " ".join(
                (judgements or {}).get("intelligence_gaps") or [])
            mech_claim = _flag(MECHANISM_CLAIM_RX, body)
            mech_unknown = bool(MECHANISM_UNKNOWN_RX.search(with_gaps))
            if mech_claim and mech_unknown:
                issues.append((
                    "loss evidence presented as proof of an engagement "
                    "mechanism or deliberate denial, while the same reporting "
                    "states the mechanism is unknown", label))
            elif mech_claim and o.get("confidence") == "high":
                issues.append((
                    "high-confidence claim about a loss mechanism or denial "
                    "of coverage — attrition is observable, causation is not",
                    label))
            # Exploitation: lehetoseg vs megtortent teny.
            if _flag(EXPLOITATION_DONE_RX, body) \
                    and not EXPLOITATION_HEDGE_RX.search(body):
                issues.append((
                    "wreckage recovery presented as completed technical "
                    "exploitation — public display creates an opportunity, it "
                    "does not evidence exploitation", label))
            # Egy eset != csoport-trend.
            if _flag(PLURAL_ACTOR_RX, body) and len(_named_countries(body)) <= 1:
                issues.append((
                    "plural-actor trend claim supported by at most one named "
                    "country — a single order is not a group trend", label))
            # Kvantifikalhatatlan kvantifikalas.
            if (_flag(QUANTIFIED_CLAIM_RX, body)
                    or _flag(DURATION_CLAIM_RX, body)) \
                    and not HARD_FIGURE_RX.search(body):
                issues.append((
                    "gap or duration described as quantifiable/measured with "
                    "no figure, out-of-service date or throughput datum in "
                    "the reporting", label))
            if REDUNDANT_DURATION_RX.search(body):
                issues.append((
                    "redundant duration phrasing ('at least N or more') — "
                    "use 'at least N years' or 'N years or more'", label))
            # Retorikus leertekeles.
            if DISMISSIVE_RX.search(body):
                issues.append((
                    "dismissive rhetoric where neutral analytical language is "
                    "required (prefer 'limited-scale contribution')", label))

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
        # A KORABBI VALTOZAT HAMIS POZITIVOT GYARTOTT: barmely "confirmed"
        # szo a KJ-ben osszeakadt barmilyen targyu "not confirmed" gappel, es
        # olyan iteleteket tartott vissza, amelyek EPPEN a helyes, hedgelt
        # formaban fogalmaztak ("available data does not establish ...").
        # Ket szigoritas: (a) a talalat mondata ne legyen maga is tagado —
        # aki kimondja a bizonytalansagot, az nem allitja az ellenkezojet;
        # (b) legyen tenyleges TEMAEGYEZES a konkret gappel.
        jud = str(j.get("judgement") or "")
        jud_t = _kw(jud)
        flagged = False
        for g in ((judgements or {}).get("intelligence_gaps") or []):
            gl = str(g).lower()
            if not GAP_DENIAL_RX.search(gl):
                continue
            for w in ("confirmed", "verified", "independent", "quantified",
                      "established", "disclosed", "stated"):
                if w not in gl:
                    continue
                for sent in _sentences(jud):
                    if w in sent.lower() and not NEGATION_RX.search(sent) \
                            and len(jud_t & _kw(gl)) >= 3:
                        issues.append(("judgement asserts what the gaps say "
                                       "is unknown", label))
                        flagged = True
                        break
                if flagged:
                    break
            if flagged:
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
        # 9c. jelen ideju kepesseg-ige egy meg le nem szallitott kepessegre.
        # "Establishes/introduces ... capability" mikozben a szerzodes csak
        # most indul: a szerzodes nem maga a kepesseg.
        if PRESENT_ESTABLISH_RX.search(full_d) and d.get(
                "lifecycle_stage") not in ("ioc", "foc", "delivery"):
            issues.append(("a contracted item described with a present-tense "
                           "capability verb (use 'would introduce' / "
                           "'initiates establishment of')",
                           d.get("display_label") or d.get("title")))
        # 9c2. onellentmondas: fuggetlenseg-allitas feloldatlan fuggoseg mellett
        _dep_open = DEPENDENCY_UNRESOLVED_RX.search(full_d)
        _abs_claim = ABSOLUTE_INDEPENDENCE_RX.search(full_d)
        # A relativ allitas rendben van, ha a SAJAT mondata felteteles.
        _rel_claim = any(
            REDUCE_DEPENDENCE_RX.search(sent) and not HEDGE_RX.search(sent)
            for sent in _sentences(full_d))
        if _dep_open and (_abs_claim or _rel_claim):
            issues.append(("self-sufficiency claim contradicted by an "
                           "unresolved dependency in the same block",
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
        # Csak betut IS tartalmazo, programra jellemzo tokenek. A puszta
        # "12" vagy "35" tul general — a JP F-2 kartya igy kapott hamis
        # "2030 nem ehhez a programhoz tartozik" jelzest.
        toks = {t.lower() for t in re.findall(
            r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+|[A-Z]{3,}",
            label + " " + str(d.get("title") or ""))}
        prog_tokens[label] = {t for t in toks if len(t) >= 3}
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
                # Legalabb KET egyezo programtoken kell — egyetlen general
                # egyezes nem azonositja a programot.
                if len(toks & set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+|"
                                             r"[a-z]{3,}", low))) < 2:
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

    # 9g. SZOVETSEGI TAGSAG (kemeny tenyellenorzes)
    for scope, texts in (("development",
                          [prose(d, ("fact", "capability_delta", "so_what"))
                           for d in developments]),
                         ("judgement",
                          [prose(j, ("judgement", "basis", "assessment"))
                           for j in kjs])):
        labels = ([d.get("display_label") or d.get("title")
                   for d in developments] if scope == "development"
                  else [j.get("id") for j in kjs])
        for text, label in zip(texts, labels):
            for country, phrase, alliance in alliance_check(text):
                issues.append((
                    "FACT ERROR: {} is a {} member, described as '{}'".format(
                        country, alliance, phrase), label))

    # 9h. MEGNEVEZES A FORRASON KIVULROL
    src = _source_designations(events)
    if src:
        for d in developments:
            body = " ".join([prose(d, ("fact", "capability_delta", "so_what"))]
                            + list(d.get("indicators_to_watch") or []))
            unknown = {m.replace(" ", "-").upper()
                       for m in DESIGNATION_RX.findall(body)} - src
            unknown -= DESIGNATION_ALLOW
            unknown = {u for u in unknown if not re.fullmatch(r"20\d\d", u)}
            if unknown:
                issues.append((
                    "designation not present in this period's source "
                    "reporting ({}) — verify the entity".format(
                        ", ".join(sorted(unknown)[:3])),
                    d.get("display_label") or d.get("title")))

    # 9h2. LINEAGE-INFLACIO — a fuggetlen forraslancok szama determinisztikus
    # A W33 "2 reports / 2 lineages"-t irt az iráni MQ-9/MQ-1C veszteseghez,
    # de az annexben mindket esemeny UGYANAZZAL A CIKKCIMMEL szerepelt. Ket
    # event-rekord egy cikkbol egy lanc.
    ev_by_id = {e.get("event_id"): e for e in (events or [])}
    for d in developments:
        src = [ev_by_id[i] for i in (d.get("event_ids") or []) if i in ev_by_id]
        if not src:
            continue
        actual, reports, note = count_lineages(src)
        claimed = int(d.get("independent_lineages") or 1)
        if claimed > actual:
            issues.append((
                "independent lineages overstated ({} claimed, {} actual) — "
                "{}".format(claimed, actual, note),
                d.get("display_label") or d.get("title")))
        if actual <= 1 and d.get("confidence") == "high":
            issues.append((
                "high confidence on single-chain evidence — one source chain "
                "cannot support a high-confidence judgement",
                d.get("display_label") or d.get("title")))

    # 9i. ORBAT-BASELINE ANOMALIA (a jelentes sajat adatai nem stimmelnek)
    for row in (orbat or []):
        for ent in (row.get("entries") or []):
            # 9i2. Hatokor-eltéres: varians-szintu esemeny csalad-szintu
            # baseline-nal. Ez a HH-60W / UH-60 "Active 2000" hibaosztaly.
            if ent.get("baseline_scope_match") == "variant_without_baseline":
                issues.append((
                    "variant-level action has no variant-level baseline; the "
                    "family total is withheld rather than substituted",
                    "{} / {}{}".format(
                        row.get("country"), ent.get("type"),
                        " ({})".format(ent.get("variant_reported"))
                        if ent.get("variant_reported") else "")))
            # 9i3. Stadium-ellentmondas az ORBAT-ban.
            if ent.get("this_period_stage_note"):
                issues.append((
                    "ORBAT stage downgraded — the event was labelled as "
                    "contracted but its own reporting does not evidence a "
                    "contract: {}".format(ent["this_period_stage_note"]),
                    "{} / {}".format(row.get("country"), ent.get("type"))))
            if ent.get("baseline_anomaly"):
                issues.append((
                    "ORBAT baseline anomaly: on-order {} is not explained by "
                    "this period's action ({}) and the type shows no active "
                    "airframes — verify the fleet baseline".format(
                        ent.get("on_order"), ent.get("this_week_quantity")),
                    "{} / {}".format(row.get("country"), ent.get("type"))))

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
    "FACT ERROR:", "designation not present in this period's source",
    "self-sufficiency claim contradicted", "grammar artifact",
    "capability claim beyond procurement", "delivery events presented as",
    "trend claim without", "unqualified superlative",
    "export clearance described as", "judgement uses trend language",
    "judgement asserts combat capability", "deterministic language",
    "assertive judgement at low confidence", "duplicated word in prose",
    "volume change may be presented", "judgement asserts what the gaps",
    # --- v3: a W33/W34 osszehasonlitasbol azonositott hibaosztalyok ---
    "loss evidence presented as proof of an engagement mechanism",
    "high-confidence claim about a loss mechanism",
    "wreckage recovery presented as completed technical exploitation",
    "plural-actor trend claim supported by at most one named country",
    "gap or duration described as quantifiable",
    "redundant duration phrasing",
    "dismissive rhetoric where neutral analytical language",
)

KJ_BLOCKING = (
    "judgement asserts what the gaps say is unknown",
    "judgement uses trend language",
    "judgement asserts combat capability from procurement data",
    "assertive judgement at low confidence",
    # A W33 Iran-KJ pontosan ez volt: magas confidence-szel allitott
    # mechanizmust es szandekot, mikozben a sajat Basis es a gap-lista
    # ismeretlennek mondta a modszert. Egy atiras ezt nem javitja meg — az
    # ITELET SZERKEZETE hibas, ezert visszatartando.
    "loss evidence presented as proof of an engagement mechanism",
    "high confidence on single-chain evidence",
    "independent lineages overstated",
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
- duplicated word or grammar artifact -> fix the typo only.
- alliance fact error -> use the correct status ("a NATO Ally"), never
  "NATO-adjacent/aligned/partner" for a member state.
- designation not in source -> remove the specific designation and refer to
  the programme generically ("the indigenous engine programme").
- self-sufficiency claim contradicted by an unresolved dependency in the same
  block -> make it conditional ("could reduce foreign dependency if an
  indigenous engine and associated subsystems mature").
- a contracted item described with a present-tense capability verb
  ("introduces", "adds", "establishes") -> conditional/future ("would
  introduce", "initiates establishment of").

--- the v3 downgrades, each traced to a specific defect ---
- loss evidence presented as proof of an engagement mechanism or deliberate
  denial -> separate the three levels explicitly. Losses are observable; the
  mechanism is not; deliberate systematic denial is a further inference.
  Model answer: "Multiple MQ-9/MQ-1C losses during Operation Epic Fury
  demonstrate that persistent MALE operations over Iran incurred material
  attrition; the available evidence does not establish the loss mechanism or
  whether Iran systematically denied persistent coverage." Never keep
  "demonstrated effective counter-MALE capability".
- wreckage recovery presented as completed exploitation -> "recovered wreckage
  creates a technical exploitation opportunity"; never "has exploited",
  "has provided access to". Public display of wreckage evidences possession,
  not exploitation, and never its success.
- plural-actor trend claim from one named country -> name the single actor and
  demote the group claim to an indicator: "Lithuania is moving toward an
  organic dedicated C-UAS intercept capability; whether Latvia and Estonia
  follow is an indicator to watch", never "Baltic allies could be fielding".
- gap or duration described as quantifiable with no figures -> state the risk
  without claiming measurement: "creates a credible risk of an advanced-jet
  training capacity gap; its duration and effect on annual pilot throughput
  cannot yet be quantified from the available reporting."
- redundant duration phrasing -> "at least five years" OR "five years or
  more", never "at least five or more years".
- dismissive rhetoric -> neutral analytical register: "remains a limited-scale
  contribution", not "remains a token addition". Do not replace one loaded
  word with another.
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
