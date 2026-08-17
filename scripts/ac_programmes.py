# -*- coding: utf-8 -*-
"""ac_programmes.py — programme-identitas es allapotfrissites.

EZ A MODUL AZ, AMI A LENGYEL APACHE-DUPLIKACIOT MEGSZUNTETI.

A hiba anatomiaja
-----------------
W33:  Poland AH-64E — on order 190, "this period: contract signed x94"
      -> a key judgement mar 284 gepes "programme of record"-rol beszelt
W34:  Poland AH-64E — on order 286, "this period: contract signed x96"

Egyetlen valos program letezik: a 2024 augusztusaban alairt lengyel AH-64E
beszerzes (96 gep). A 190-es szam es a heti 94/96 ugyanannak a programnak
kulonbozo forras-allitasai — nem harom kulonbozo rendeles.

A javitas nem az, hogy okosabban osszegzunk. A javitas az, hogy NEM OSSZEGZUNK:

    on_order = programme.canonical_quantity        (a program allapota)
    NEM:
    on_order = previous_on_order + article_quantity  (esemenyek osszege)

Mit tesz ez a modul
-------------------
  1. programme_key()      — stabil, deterministikus programazonosito kepzese
  2. find_programme()     — egy uj esemeny hozzarendelese meglevo programhoz
  3. apply_event()        — a program allapotanak FRISSITESE (nem osszegzese)
  4. on_order_delta()     — mennyivel mozdulhat a baseline (alapertelmezesben 0)
  5. programme_view()     — riport-baratsagos allapot + a valtozas indoklasa

Egyetlen szabaly vezerli az egeszet: EGY UJABB CIKK NEM UJ REPULOGEP.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ac_match  # noqa: E402

__all__ = ["programme_key", "find_programme", "apply_event", "on_order_delta",
           "programme_view", "PROGRAMME_KINDS", "kind_from_event",
           "contract_evidenced", "merge_candidates", "variant_key"]


# --------------------------------------------------------------------------
# Programfajtak
# --------------------------------------------------------------------------

PROGRAMME_KINDS = {
    "acquisition":     "Acquisition",
    "upgrade":         "Upgrade programme",
    "sustainment_mro": "Sustainment / MRO",
    "infrastructure":  "Infrastructure",
    "training":        "Training / pipeline",
    "retirement":      "Withdrawal",
    "lease":           "Lease / interim",
    "development":     "Development",
}

# Egy MRO/depot/infrastruktura-programnak NINCS "first aircraft delivery"
# milestoneja. A W34 timeline ezert irt hibasan "2028 Poland AH-64E MRO deal
# (first delivery)"-t: a 2028-as elso atadas a BESZERZESI programhoz tartozik.
NO_AIRFRAME_ARRIVAL = {"sustainment_mro", "infrastructure", "training"}

MRO_RX = re.compile(
    r"\b(mro|depot|sustainment|maintenance,? repair|overhaul|"
    r"service cent(?:re|er)|offset agreement|logistics support|"
    r"performance[- ]based logistics|spare parts)\b", re.I)
INFRA_RX = re.compile(
    r"\b(hangar|infrastructur|base construction|runway|shelter|"
    r"facility|facilities|simulator (?:centre|center|facility))\b", re.I)
TRAINING_RX = re.compile(
    r"\b(training (?:contract|programme|program|package|centre|center)|"
    r"pilot training|conversion course|aircrew training)\b", re.I)
LEASE_RX = re.compile(r"\b(lease|leasing|interim solution|wet[- ]lease)\b", re.I)
UPGRADE_RX = re.compile(
    r"\b(upgrade|modernis|moderniz|retrofit|mid[- ]life|service life "
    r"extension|slep|capability insertion|block \d+ upgrade)\b", re.I)


def kind_from_event(event, summary=None):
    """A programfajta az esemeny tartalmabol. A sorrend szamit: egy
    'AH-64E MRO agreement' MRO-program, nem beszerzes."""
    text = " ".join(str(x or "") for x in (
        summary, event.get("summary"), event.get("milestone_kind")))
    stage = event.get("lifecycle_stage") or ""
    if stage in ("retirement",) or event.get("event_type") == "retirement":
        return "retirement"
    if MRO_RX.search(text):
        return "sustainment_mro"
    if INFRA_RX.search(text):
        return "infrastructure"
    if TRAINING_RX.search(text):
        return "training"
    if LEASE_RX.search(text):
        return "lease"
    if stage == "upgrade_programme" or UPGRADE_RX.search(text):
        return "upgrade"
    if stage in ("requirement", "rfi_sources_sought", "rfp", "bid") \
            and re.search(r"\b(develop|prototype|demonstrator)\b", text, re.I):
        return "development"
    return "acquisition"


# --------------------------------------------------------------------------
# 1. Programazonosito
# --------------------------------------------------------------------------

def _slug(value, maxlen=18):
    s = re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    return s[:maxlen]


def variant_key(value):
    """A varians KANONIKUS kulcsa a tipusjelbol, nem a teljes szovegbol.

    Enelkul a program 'HH-60W' varianssal es az esemeny 'HH-60W Jolly Green II'
    variansaval ket kulonbozo kulcsot ad (a slug csonkolasa miatt), es az
    esemeny sosem talal ra a sajat programjara — vagyis minden het uj programot
    nyitna, ami eppen az a duplikacio, amit meg akarunk szuntetni.

    >>> variant_key("HH-60W Jolly Green II")
    'hh-60w'
    >>> variant_key("HH-60W")
    'hh-60w'
    >>> variant_key("AH-64E Apache Guardian")
    'ah-64e'
    >>> variant_key("Block 70")
    'block70'
    """
    if not value:
        return ""
    d = ac_match.extract_designation(value)
    if d:
        return "{}-{}{}".format(d[0], d[1], d[2])
    return _slug(value, 12)


def programme_key(country_id, type_id, variant=None, service=None,
                  kind="acquisition", anchor_year=None):
    """Stabil, ember altal olvashato programazonosito.

    Formatum:  <orszag>-<tipus><varians>-<fajta>-<horgony-ev>
    Pelda:     pol-ah64e-2024        (lengyel AH-64E beszerzes)
               pol-ah64e-mro-2026    (a hozza tartozo MRO-program KULON)
               usa-vc25b-2018        (VC-25B)
               usa-hh60w-usaf-2020   (USAF HH-60W, NEM UH-60)

    Miert kell a horgony-ev: ugyanaz az orszag ugyanabbol a tipusbol tobb,
    egymastol fuggetlen batchet vehet evekkel kesobb (Poland F-35 batch 1 /
    batch 2). A horgony-ev a program INDULASA (elso evidencia), nem az
    aktualis het — igy a kesobbi cikkek ugyanahhoz a kulcshoz vezetnek.

    Miert kell a varians es a service: a HH-60W (USAF CSAR) es a UH-60M
    (US Army) nem ugyanaz a program. Enelkul all elo a "26 HH-60W esemeny /
    UH-60 Active 2000 baseline" tipusu ORBAT-hiba.
    """
    parts = [_slug(country_id, 6) or "xxx"]
    core = _slug(type_id, 10) or "unk"
    # A varians a TIPUSJELBOL normalizalva, nem a teljes marketingnevbol:
    # a "HH-60W Jolly Green II" es a "HH-60W" ugyanazt a kulcsot adja.
    var = _slug(variant_key(variant), 10)
    # A varians csak akkor kerul a kulcsba, ha tobbletinformacio: az "ah-64"
    # + "AH-64E" -> 'ah64e', de az "ah-64" + "AH-64" nem duplikal.
    if var and var != core:
        core = var if var.startswith(core) else core + var
    parts.append(core)
    svc = _slug(service, 6)
    if svc:
        parts.append(svc)
    if kind and kind != "acquisition":
        parts.append(_slug(kind, 6))
    if anchor_year:
        parts.append(str(int(anchor_year)))
    return "-".join(p for p in parts if p)


# --------------------------------------------------------------------------
# 2. Hozzarendeles meglevo programhoz
# --------------------------------------------------------------------------

def _year_of(value):
    m = re.search(r"(\d{4})", str(value or ""))
    if not m:
        return None
    y = int(m.group(1))
    return y if 1950 <= y <= 2060 else None


def find_programme(event, programmes, summary=None):
    """Melyik meglevo programhoz tartozik ez az esemeny?

    Visszaad: (programme_dict vagy None, indoklas).

    A hozzarendeles KONZERVATIV: ha nem biztos, uj programot javasol es
    review-ba kuldi, mert egy hibasan OSSZEVONT program ugyanolyan karos,
    mint egy hibasan SZETVALASZTOTT.

    Az egyezes feltetelei — mind kell:
      * ugyanaz az orszag
      * ugyanaz a katalogus-tipus
      * kompatibilis varians (az egyik ures, vagy azonos csalad-utotag)
      * kompatibilis haderonem
      * ugyanaz a programfajta (beszerzes != MRO != upgrade)
    """
    cid, tid = event.get("country_id"), event.get("type_id")
    if not cid or not tid:
        return None, "no country/type foreign key — cannot attach to a programme"
    kind = kind_from_event(event, summary)
    # A varianst a TIPUSJELERE normalizaljuk, kulonben a "HH-60W Jolly Green
    # II" nem talal ra a "HH-60W" varianssal rogzitett sajat programjara.
    ev_var = variant_key(event.get("variant_raw") or event.get("variant") or "")
    ev_svc = _slug(event.get("service") or "", 6)

    candidates = []
    for p in programmes:
        if p.get("review_status") not in (None, "active"):
            continue
        if p.get("country_id") != cid or p.get("type_id") != tid:
            continue
        if (p.get("programme_kind") or "acquisition") != kind:
            continue
        p_var = variant_key(p.get("variant") or "")
        p_svc = _slug(p.get("service") or "", 6)
        # Varians-kompatibilitas: ures oldal illeszkedik barmire, kulonben
        # azonossag kell. Igy a HH-60W esemeny nem esik be egy UH-60M
        # programba, meg ha a katalogus-csalad azonos is.
        if p_var and ev_var and p_var != ev_var:
            continue
        if p_svc and ev_svc and p_svc != ev_svc:
            continue
        score = 0
        if p_var and ev_var and p_var == ev_var:
            score += 2
        if p_svc and ev_svc and p_svc == ev_svc:
            score += 1
        candidates.append((score, p))

    if not candidates:
        return None, "no existing programme matches country+type+variant+kind"
    candidates.sort(key=lambda x: -x[0])
    best = candidates[0][1]
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return best, ("ambiguous: {} programmes match equally — attached to "
                      "{} and flagged for review".format(
                          len(candidates), best.get("programme_id")))
    return best, "matched on country+type+variant+kind"


# --------------------------------------------------------------------------
# 3. Szerzodes-evidencia
# --------------------------------------------------------------------------

CONTRACT_EVIDENCE_RX = re.compile(
    r"\b(signed (?:a |the )?(?:contract|agreement|deal)|contract (?:was )?"
    r"signed|contract award(?:ed)?|awarded a contract|firm[- ]fixed[- ]price|"
    r"definitised|definitized|placed (?:an |the )?order|"
    r"letter of (?:offer and )?acceptance signed|loa signed)\b", re.I)
NEGOTIATION_RX = re.compile(
    r"\b(in (?:talks|negotiations?)|negotiat\w+|under discussion|"
    r"reportedly (?:agreed|plans)|memorandum of understanding|"
    r"letter of intent|expressed interest|is considering|"
    r"unconfirmed|not (?:been )?confirmed|no (?:official )?confirmation)\b",
    re.I)

FIRM_STAGES = {"contract_signed", "production", "delivery", "ioc", "foc"}


def contract_evidenced(event, summary=None):
    """Van-e ELFOGADHATO szerzodes-evidencia?

    Ez a fuggveny az uzbeg hiba kapuja. A W34-ben az elemzoi reteg helyesen
    'negotiation / low confidence / nincs hivatalos megerositesa' allapotot
    irt, az ORBAT megis 'Contract signed x24'-et mutatott. Egy allitas nem
    lehet ket allapotban.

    Visszaad: (bool, indoklas)
    """
    text = " ".join(str(x or "") for x in (summary, event.get("summary")))
    stage = event.get("lifecycle_stage") or ""
    if stage not in FIRM_STAGES:
        return False, ("lifecycle stage '{}' is not a contracted stage"
                       .format(stage or "unset"))
    if NEGOTIATION_RX.search(text) and not CONTRACT_EVIDENCE_RX.search(text):
        return False, ("stage says '{}' but the reporting describes talks or "
                       "an unconfirmed claim — treated as not contracted"
                       .format(stage))
    if not CONTRACT_EVIDENCE_RX.search(text) and not event.get("contract_date"):
        return False, ("no signing language, contract date or award reference "
                       "in the reporting")
    return True, "contract evidence present"


def on_order_delta(event, programme=None, summary=None):
    """Mennyivel mozdulhat az ORBAT on_order allomanya EBBOL az esemenybol?

    ALAPERTELMEZESBEN NULLA. Ez a modul legfontosabb dontese.

    Visszaad: (delta, indoklas)

    Ket kulonallo ok teheti nem nullava:
      * van elfogadott szerzodes-evidencia, ES
      * az esemeny NEM ugyanannak a programnak az ujraallitasa (kulonben a
        lengyel Apache-nal minden heti cikk ujra hozzaadna a 96-ot)
    """
    q = event.get("quantity_claimed")
    if q in (None, ""):
        q = event.get("quantity")
    try:
        q = int(q)
    except (TypeError, ValueError):
        return 0, "no quantity reported"
    if q <= 0:
        return 0, "non-positive quantity"

    ok, why = contract_evidenced(event, summary)
    if not ok:
        return 0, "on-order unchanged: " + why

    if programme is None:
        return q, ("new programme with contract evidence — {} enters on-order"
                   .format(q))

    canon = programme.get("canonical_quantity")
    try:
        canon = int(canon) if canon not in (None, "") else None
    except (TypeError, ValueError):
        canon = None

    # A LENGYEL APACHE-KAPU. Ha a program mar ismeri ezt a darabszamot, az
    # ujabb cikk MEGERSITES, nem uj rendeles.
    if canon is not None and q <= canon:
        return 0, ("on-order unchanged: programme {} already records {} "
                   "aircraft — this reporting restates part of the same "
                   "programme, it is not an additional order".format(
                       programme.get("programme_id"), canon))
    if canon is not None and q > canon:
        return q - canon, ("programme quantity revised {} -> {}; only the "
                           "difference enters on-order".format(canon, q))
    return q, "programme had no canonical quantity — {} recorded".format(q)


# --------------------------------------------------------------------------
# 4. Allapotfrissites
# --------------------------------------------------------------------------

STAGE_ORDER = ["requirement", "rfi_sources_sought", "rfp", "bid", "selection",
               "national_approval", "export_approval", "contract_signed",
               "production", "delivery", "ioc", "foc"]
_STAGE_RANK = {s: i for i, s in enumerate(STAGE_ORDER)}
# A kivonas es a veszteseg NEM a bevezetesi lancon van; sosem "elore lepes".
PARALLEL_STAGES = {"upgrade_programme", "retirement", "loss", "other"}


def _iso(value):
    if not value:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    return m.group(0) if m else None


def apply_event(programme, event, summary=None, article_id=None, now=None):
    """A program allapotanak FRISSITESE egy uj esemenybol.

    A program allapota nem esemenyek osszege, hanem a legjobb evidencia
    szerinti aktualis kep. Ez a fuggveny sosem ad ossze darabszamot.

    Visszaad: (patch_dict, valtozasok_listaja). A patch a programra
    alkalmazando mezoket tartalmazza; ures patch = nincs allapotvaltozas
    (az esemeny megerosites).
    """
    now = now or datetime.utcnow()
    patch, changes = {}, []
    p = dict(programme or {})

    # --- 1. eletciklus: csak ELORE lephet, es csak evidenciaval ---
    ev_stage = event.get("lifecycle_stage") or ""
    cur_stage = p.get("lifecycle_stage") or ""
    if ev_stage in _STAGE_RANK:
        # A contract_signed stadiumhoz szerzodes-evidencia kell. Enelkul a
        # program NEM lep szerzodott allapotba, barmit is mond a cimke.
        if ev_stage in FIRM_STAGES:
            ok, why = contract_evidenced(event, summary)
            if not ok:
                changes.append("lifecycle NOT advanced to {}: {}".format(
                    ev_stage, why))
                ev_stage = ""
        if ev_stage and (cur_stage not in _STAGE_RANK
                         or _STAGE_RANK[ev_stage] > _STAGE_RANK[cur_stage]):
            patch["lifecycle_stage"] = ev_stage
            changes.append("lifecycle {} -> {}".format(
                cur_stage or "unset", ev_stage))
    elif ev_stage in PARALLEL_STAGES and not cur_stage:
        patch["lifecycle_stage"] = ev_stage
        changes.append("lifecycle set to {}".format(ev_stage))

    # --- 2. kanonikus darabszam: FELULIRAS, nem osszegzes ---
    q = event.get("quantity_claimed")
    if q in (None, ""):
        q = event.get("quantity")
    try:
        q = int(q) if q not in (None, "") else None
    except (TypeError, ValueError):
        q = None
    if q and q > 0:
        canon = p.get("canonical_quantity")
        try:
            canon = int(canon) if canon not in (None, "") else None
        except (TypeError, ValueError):
            canon = None
        ok, _why = contract_evidenced(event, summary)
        new_basis = "contract" if ok else "reported"
        old_basis = p.get("quantity_basis") or "unknown"
        # Erosebb alapu allitas felulirja a gyengebbet; azonos alapon a
        # frissebb nyer. A felulirt ertek MEGORZODIK.
        rank = {"contract": 3, "announced": 2, "reported": 1,
                "estimate": 1, "unknown": 0}
        if canon is None:
            patch["canonical_quantity"] = q
            patch["quantity_basis"] = new_basis
            changes.append("canonical quantity set to {} ({})".format(
                q, new_basis))
        elif q != canon and rank.get(new_basis, 0) >= rank.get(old_basis, 0):
            hist = list(p.get("superseded_quantities") or [])
            hist.append({"quantity": canon, "basis": old_basis,
                         "as_of": _iso(p.get("quantity_as_of")),
                         "superseded_at": now.strftime("%Y-%m-%d"),
                         "source": article_id})
            patch["superseded_quantities"] = hist
            patch["canonical_quantity"] = q
            patch["quantity_basis"] = new_basis
            changes.append("canonical quantity revised {} -> {} ({} supersedes "
                           "{}); previous value retained in history".format(
                               canon, q, new_basis, old_basis))
        else:
            changes.append("quantity {} restates the existing {} — NOT added"
                           .format(q, canon))
        if "canonical_quantity" in patch:
            patch["quantity_as_of"] = _iso(event.get("event_date")) \
                or now.strftime("%Y-%m-%d")

    # --- 3. kepesseg-idorend: a legkorabbi hitelesen jelentett ev nyer ---
    for src, dst in (("first_delivery_year", "first_delivery_year"),
                     ("delivery_start_year", "delivery_start_year"),
                     ("delivery_end_year", "delivery_end_year"),
                     ("expected_ioc_year", "ioc_year"),
                     ("foc_year", "foc_year"),
                     ("meaningful_scale_year", "meaningful_scale_year")):
        y = event.get(src)
        try:
            y = int(y) if y not in (None, "") else None
        except (TypeError, ValueError):
            y = None
        if y and not p.get(dst):
            patch[dst] = y
            changes.append("{} set to {}".format(dst, y))

    # --- 4. szerzodes datuma ---
    if not p.get("contract_date"):
        ok, _ = contract_evidenced(event, summary)
        if ok and _iso(event.get("event_date")):
            patch["contract_date"] = _iso(event.get("event_date"))
            patch["contract_evidence"] = article_id
            changes.append("contract date recorded {}".format(
                patch["contract_date"]))

    # --- 5. ertek: csak azonos ertektipuson belul frissitunk ---
    v, vt = event.get("value_usd_m"), event.get("value_type")
    if v not in (None, "") and vt:
        if not p.get("value_usd_m") or (
                vt == "firm" and p.get("value_type") != "firm"):
            patch["value_usd_m"] = v
            patch["value_type"] = vt
            if event.get("value_currency_year"):
                patch["value_currency_year"] = event.get("value_currency_year")
            changes.append("value recorded {} ({})".format(v, vt))

    # --- 6. evidencia-szamlalok ---
    seen = _iso(event.get("new_evidence_at")) or _iso(event.get("event_date")) \
        or now.strftime("%Y-%m-%d")
    if not p.get("first_reported_at"):
        patch["first_reported_at"] = _iso(event.get("first_reported_at")) or seen
    patch["last_evidence_at"] = seen
    patch["evidence_count"] = int(p.get("evidence_count") or 0) + 1

    hist = list(p.get("claim_history") or [])
    hist.append({"as_of": seen, "stage": event.get("lifecycle_stage"),
                 "quantity": q, "article_id": article_id,
                 "evidence_kind": event.get("evidence_kind") or "new_event",
                 "note": (str(summary or event.get("summary") or ""))[:180]})
    patch["claim_history"] = hist[-40:]
    patch["updated_at"] = now.isoformat()

    if not changes:
        changes.append("no state change — this reporting confirms the existing "
                       "programme record")
    return patch, changes


# --------------------------------------------------------------------------
# 5. Riport-nezet
# --------------------------------------------------------------------------

def programme_view(programme, this_period_events=None):
    """A program allapota a jelentes szamara, a HETI valtozas kulon jelolve.

    Kritikus: a 'canonical_quantity' es a 'this_period' KULON mezok, es a
    riport soha nem adja ossze oket. A W33 ORBAT azert volt felrevezeto, mert
    'On order 190' es 'This period contract signed x94' egymas mellett
    olvasva 284-et sugallt.
    """
    p = programme or {}
    evs = this_period_events or []
    delta = sum(int(e.get("on_order_delta") or 0) for e in evs)
    claimed = [int(e["quantity_claimed"]) for e in evs
               if e.get("quantity_claimed") not in (None, "")]
    kinds = {e.get("evidence_kind") or "new_event" for e in evs}
    return {
        "programme_id": p.get("programme_id"),
        "title": p.get("title"),
        "kind": p.get("programme_kind") or "acquisition",
        "kind_label": PROGRAMME_KINDS.get(
            p.get("programme_kind") or "acquisition", "Programme"),
        "country_id": p.get("country_id"),
        "type_id": p.get("type_id"),
        "variant": p.get("variant"),
        "service": p.get("service"),
        "canonical_quantity": p.get("canonical_quantity"),
        "quantity_basis": p.get("quantity_basis"),
        "lifecycle_stage": p.get("lifecycle_stage"),
        "contract_date": p.get("contract_date"),
        "first_delivery_year": p.get("first_delivery_year"),
        "ioc_year": p.get("ioc_year"),
        "foc_year": p.get("foc_year"),
        "meaningful_scale_year": p.get("meaningful_scale_year"),
        "confidence": p.get("confidence"),
        "independent_lineages": p.get("independent_lineages") or 1,
        "first_reported_at": p.get("first_reported_at"),
        "last_evidence_at": p.get("last_evidence_at"),
        "evidence_count": p.get("evidence_count") or 0,
        "supersessions": len(p.get("superseded_quantities") or []),
        # --- a HETI reteg, explicit szemantikaval ---
        "this_period": {
            "events": len(evs),
            "on_order_delta": delta,
            "quantity_claimed_max": max(claimed) if claimed else None,
            "evidence_kinds": sorted(kinds),
            # Ez a mondat az, amit a jelentes kiir. Enelkul az olvaso
            # osszeadja a ket szamot.
            "reading": (
                "no change to the programme baseline; this period's reporting "
                "restates or confirms the existing record"
                if delta == 0 else
                "programme baseline moves by {:+d} on the strength of this "
                "period's contract evidence".format(delta)),
        },
        "no_airframe_arrival": (p.get("programme_kind")
                                in NO_AIRFRAME_ARRIVAL),
    }


# --------------------------------------------------------------------------
# 6. Duplikatum-gyanu meglevo programok kozott
# --------------------------------------------------------------------------

def merge_candidates(programmes):
    """Gyanus programparok: ugyanaz az orszag+tipus+fajta, kompatibilis
    varianssal. Ezeket EMBERNEK kell eldontenie — a modul csak jelez.

    Ez a backfill legfontosabb kimenete: a mar felhalmozott duplikaciot
    (pl. tobb lengyel AH-64E program) igy lehet egyesiteni."""
    out = []
    for i, a in enumerate(programmes):
        for b in programmes[i + 1:]:
            if a.get("country_id") != b.get("country_id"):
                continue
            if a.get("type_id") != b.get("type_id"):
                continue
            if (a.get("programme_kind") or "acquisition") != \
                    (b.get("programme_kind") or "acquisition"):
                continue
            av = variant_key(a.get("variant") or "")
            bv = variant_key(b.get("variant") or "")
            if av and bv and av != bv:
                continue
            as_, bs = _slug(a.get("service") or ""), _slug(b.get("service") or "")
            if as_ and bs and as_ != bs:
                continue
            out.append({
                "a": a.get("programme_id"), "b": b.get("programme_id"),
                "country_id": a.get("country_id"), "type_id": a.get("type_id"),
                "a_quantity": a.get("canonical_quantity"),
                "b_quantity": b.get("canonical_quantity"),
                "a_stage": a.get("lifecycle_stage"),
                "b_stage": b.get("lifecycle_stage"),
                "reason": "same country + type + programme kind with "
                          "compatible variant/service — likely the same "
                          "programme recorded twice",
            })
    return out
