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
           "contract_evidenced", "merge_candidates", "variant_key",
           "resolved_stage", "quantity_scope"]


# --------------------------------------------------------------------------
# STADIUM-FELOLDAS — a legacy esemenyek lifecycle_stage mezoje URES
# --------------------------------------------------------------------------
#
# Az elso eles dry run megmutatta, hogy a 274 esemeny tobbsegen a
# lifecycle_stage NULL (az add_capability_fields.sql elotti extrakciok). Ez a
# modul korabban NYERSEN olvasta a mezot, igy szinte minden esemeny
# stadium nelkulinek latszott, es a programok eletciklusa sosem lepett elore.
#
# A feloldas ugyanaz a fallback, amit a riport-reteg is hasznal. (Nem
# importaljuk az ac_intel-t: az importalja EZT a modult.)
_STAGE_FALLBACK = {
    "order": "contract_signed", "delivery": "delivery",
    "upgrade": "upgrade_programme", "selection": "selection",
    "negotiation": "requirement", "retirement": "retirement",
    "incident": "loss", "export_sale": "contract_signed",
}
_VALID_STAGES = {
    "requirement", "rfi_sources_sought", "rfp", "bid", "selection",
    "national_approval", "export_approval", "contract_signed", "production",
    "delivery", "ioc", "foc", "upgrade_programme", "retirement", "loss",
    "other"}


def resolved_stage(event):
    """Az esemeny eletciklus-stadiuma, az event_type fallbackkel."""
    s = event.get("lifecycle_stage")
    if s in _VALID_STAGES:
        return s
    return _STAGE_FALLBACK.get(event.get("event_type") or "", "other")


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
    # Veszteseg/kopas. NEM beszerzesi program: sajat fajta, hogy egy lezuhant
    # gep ne allithassa egy beszerzes eletciklusat es darabszamat. Az eles dry
    # run 'usa-kc135-2025' programja hat esemenybol ot vesztesegre epult, es a
    # "kanonikus darabszam" 1 lett — egy lezuhant tankerbol.
    "attrition":       "Attrition / losses",
}

# Ezek a fajtak SOSEM tartanak kanonikus programmeretet.
NO_CANONICAL_QUANTITY = {"attrition", "infrastructure", "sustainment_mro"}

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
    stage = resolved_stage(event)
    # A VESZTESEG NEM BESZERZES. Enelkul egy F-35B baleset a "usa-f35-2026
    # acquisition" program eletciklusat allitotta 'loss'-ra, es a darabszamat
    # 1-re — mindketto ertelmetlen egy beszerzesi programon.
    if stage == "loss" or event.get("event_type") == "incident" \
            or ATTRITION_RX.search(text):
        return "attrition"
    if stage == "retirement" or event.get("event_type") == "retirement":
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
    # FEJLESZTESI program. A GCAP-nal a harom nemzet 4,6 milliard fontos
    # FEJLESZTESI szerzodest itelt oda — az nem gepbeszerzes, es nincs is
    # gepdarabszama. Beszerzesnek konyvelve ugy latszott, mintha egy szerzodott
    # beszerzesnek hianyozna a darabszama.
    #
    # DE: a "development" szo egy VALODI gepbeszerzes szovegeben is szerepelhet
    # ("a szerzodes a fejlesztest es 31 gep szallitasat is tartalmazza"). Az
    # eles futasban igy lett egy 31 gepes spanyol NH90-rendeles "development":
    #     esp-nh90-develo-2025  +31
    # Ezert a fejlesztesi minositeshez az is kell, hogy NE legyen a szovegben
    # program-szintu GEPDARABSZAM.
    if re.search(r"\bdevelopment (?:contract|programme|program|phase|"
                 r"agreement)\b|\b(?:demonstrator|technology demonstrator|"
                 r"prototype (?:contract|phase))\b", text, re.I):
        _q = event.get("quantity_claimed")
        if _q in (None, ""):
            _q = event.get("quantity")
        try:
            _q = int(_q) if _q not in (None, "") else None
        except (TypeError, ValueError):
            _q = None
        _airframe_qty = False
        if _q and _q > 0:
            _scope, _ = quantity_scope(event, summary, _q)
            _airframe_qty = _scope == "programme"
        if not _airframe_qty:
            return "development"
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
    # A "signed" es a "contract" kozott allhat ertek, datum vagy fel- es
    # alanyszerkezet: "signed a $2.5 billion contract with Saab", "signed an
    # initial production contract". Az eles adaton pontosan ez a forma bukott
    # el a korabbi szigorú mintan.
    # A kozbeszurt reszt bovan engedjuk: a vedelmi sajtoban a kettos
    # valutaertek ZAROJELES formaja altalanos, es a korabbi szukebb karakter-
    # keszlet ezen bukott el:
    #   "jointly awarded a £4.6 billion ($6.1 billion) 18-month development
    #    contract to the Edgewing consortium"
    # Itt a "($6.1" token nem illeszkedett, igy a teljes minta elbukott, es egy
    # 4,6 milliard fontos odaiteles "nincs alairasi nyelvezet"-kent latszott.
    r"\b(?:signed|inked|concluded)\s+(?:[\w$€£¥.,%()/–-]+\s+){0,9}"
    r"(?:contracts?|agreements?|deals?|orders?)\b"
    r"|\bcontract (?:was |has been )?signed\b"
    r"|\bcontract award(?:ed)?\b"
    r"|\bawarded\s+(?:[\w$€£¥.,%()/–-]+\s+){0,9}(?:contracts?|orders?)\b"
    r"|\bfirm[- ]fixed[- ]price\b|\bdefinitis(?:ed|ation)\b|\bdefinitiz(?:ed|ation)\b"
    r"|\bplaced\s+(?:an |the )?(?:firm )?order\b"
    # A "Ukraine ordered 16 Gripen E" beszerzesi akcio. A "16 on order"
    # viszont ALLAPOT, nem akcio — ezert a puszta "on order" nem eleg.
    r"|\b(?:has |have |had )?ordered\b"
    r"|\bletter of (?:offer and )?acceptance signed\b|\bloa signed\b"
    r"|\bexercised\s+(?:an?\s+)?option\b", re.I)
# A szerzodes-evidenciat TAGADO szerkezetek. A bovitett minta kulonben
# atengedne a "no contract has been signed" es "yet to be signed" formakat.
CONTRACT_NEGATED_RX = re.compile(
    r"\b(?:no|not|never|nor)\b[^.]{0,40}\b(?:signed|awarded|contract)\b"
    r"|\b(?:yet|still) to be (?:signed|awarded|finalis|finaliz)"
    r"|\b(?:contract|deal|agreement)\s+(?:has|have)\s+not\b"
    r"|\bunsigned\b|\bpending signature\b|\bawaiting (?:signature|contract)\b"
    r"|\bexpected to (?:be )?sign\b|\bplans? to sign\b|\bwill sign\b"
    r"|\bhopes? to sign\b|\baims? to sign\b", re.I)
NEGOTIATION_RX = re.compile(
    r"\b(in (?:talks|negotiations?)|negotiat\w+|under discussion|"
    r"reportedly (?:agreed|plans)|memorandum of understanding|"
    r"letter of intent|expressed interest|is considering|"
    r"unconfirmed|not (?:been )?confirmed|no (?:official )?confirmation)\b",
    re.I)

FIRM_STAGES = {"contract_signed", "production", "delivery", "ioc", "foc"}


# --------------------------------------------------------------------------
# DARABSZAM-HATOKOR — a legsulyosabb hiba, amit az eles dry run mutatott meg
# --------------------------------------------------------------------------
#
# A korabbi valtozat MINDEN esemeny darabszamat a PROGRAM teljes meretere
# vonatkozo allitasnak tekintette, es a legutolsot fogadta el. Az eles adaton
# ez a kovetkezoket termelte:
#
#   tur-kaan-2026   148 -> 1     mert "a masodik prototipus (P1) gurulasi
#                                 proban" esemeny darabszama 1
#   usa-kc135-2025  -> 1         mert hat esemeny kozul ot LEZUHANT tankerrol
#                                 szolt (1, 2, 1, 1 gep)
#   usa-f35-2026    4 -> 1 -> 12 -> 152, kozben egy F-35B BALESET allitotta 1-re
#
# Egy lezuhant gep darabszama nem a program merete. Egy elso negy atadott gep
# sem. Egy prototipus sem.
#
# Harom kulon fogalom, amit szet kell valasztani:
#
#   PROGRAMME  — a program teljes merete ("148 planned serial production",
#                "Programme of Record for 140", "contract for 96")
#   TRANCHE    — egy reszszallitas vagy tetel ("first four", "another 12",
#                "second prototype", "initial batch")
#   ATTRITION  — veszteseg vagy kivonas ("crashed", "destroyed", "lost")
#
# CSAK a PROGRAMME hatokoru darabszam allithatja a canonical_quantity-t. Ha a
# hatokor bizonytalan, NEM allitunk semmit: a None jobb, mint egy rossz szam,
# amire evekig epul az elemzes.

# A program TELJES meretere utalo megfogalmazasok.
PROGRAMME_TOTAL_RX = re.compile(
    r"\b(?:total(?:ling|ing)?(?: planned)?|planned (?:serial )?production "
    r"order|programme of record|program of record|in total|all told|"
    r"overall (?:order|requirement|programme|program)|"
    r"fleet of|requirement for|plans? to (?:procure|acquire|buy|order)|"
    r"intends to (?:procure|acquire|buy|order)|"
    r"(?:signed|awarded|placed)[^.]{0,40}\b(?:contract|order|deal|agreement)"
    r"[^.]{0,30}\bfor\b|contract (?:covering|covers|for)|"
    r"order for|acquisition of|procure(?:ment of)?|"
    r"up to|as many as|a total of)\b", re.I)

# Reszszallitas / tetel / egyedi gep — NEM a program merete.
TRANCHE_RX = re.compile(
    r"\b(?:first|initial|second|third|fourth|fifth|next|final|last)\s+"
    r"(?:\w+\s+){0,2}(?:\d+|two|three|four|five|six|batch|tranche|lot|"
    r"aircraft|airframes?|jets?|helicopters?|examples?|prototypes?|"
    r"deliveries|units?)\b"
    r"|\b(?:another|additional|further|a further)\s+\d+\b"
    # A "Tranche 5", "Lot 18", "Block 70" TIPUSJELOLES, nem reszszallitas.
    # Az eles adaton a "20 Eurofighter Typhoon Tranche 5 aircraft" firm
    # szerzodest ejtette el, mert a "tranche" szo reszszallitasnak latszott.
    # Ezert a batch/tranche/lot csak akkor szamit reszszallitasnak, ha
    # MENNYISEGKENT all (elotte hatarozo, utana nem sorszam).
    r"|\b(?:a|the|first|second|third|next|initial|further|final|new)\s+"
    r"(?:batch|tranche|lot)\b(?!\s*\d)"
    r"|\b(?:batch|tranche|lot)\s+of\s+\d+"
    r"|\binstal(?:l)?ment\b"
    r"|\b(?:prototype|pre[- ]?production|test article|"
    r"production[- ]representative)\b"
    r"|\b(?:received|took delivery of|handed over|delivered)\s+"
    r"(?:its\s+)?(?:first|initial)?\s*\d*\b"
    r"|\bbegan\s+(?:taxi|flight|ground)\s+(?:trials?|tests?)\b"
    r"|\bconducted its first\b|\breactivated\b", re.I)

# Veszteseg / kivonas — sosem a program merete.
ATTRITION_RX = re.compile(
    r"\b(?:crash(?:ed|es)?|destroyed|was lost|were lost|lost with|"
    r"shot down|written off|write[- ]off|damaged beyond|"
    r"mid[- ]air collision|fatalit)\w*\b", re.I)

# SAJTOBECSLES / SPEKULACIO. Ez gyengebb evidencia, mint egy bejelentett
# programtotal — enelkul egy "local reports suggest as many as 250" mondat
# ugyanolyan sulyt kapott, mint egy hivatalos bejelentes, es FELULIRTA azt.
ESTIMATE_RX = re.compile(
    r"\b(?:local (?:reports?|media)|reportedly|report(?:s|ed) suggest\w*|"
    r"speculat\w+|rumour\w*|rumor\w*|unconfirmed report\w*|"
    r"sources? (?:say|said|suggest|indicate)|is understood to|"
    r"appears? to|it is believed|believed to|"
    r"may (?:acquire|buy|order|procure|eventually)|"
    r"could (?:acquire|buy|order|procure)|"
    r"analysts? (?:say|said|estimate|suggest))\b", re.I)

# Kifejezett CSOKKENTES: ilyenkor egy kisebb szam JOGOSAN irja felul a nagyobbat.
REDUCTION_RX = re.compile(
    r"\b(?:cut|cuts|reduc\w+|trimm\w+|scal\w+ back|descop\w+|truncat\w+|"
    r"lower\w+ the (?:order|buy|programme|program)|"
    r"from \d+ to \d+|down from \d+)\b", re.I)

# Azok a stadiumok, amelyekben a darabszam ELVILEG a programra vonatkozhat.
PROGRAMME_SCOPE_STAGES = {
    "requirement", "rfi_sources_sought", "rfp", "bid", "selection",
    "national_approval", "export_approval", "contract_signed",
    "upgrade_programme"}
# Ezekben a darabszam tipikusan reszszallitas vagy egyedi gep.
TRANCHE_SCOPE_STAGES = {"production", "delivery", "ioc", "foc", "other"}
ATTRITION_SCOPE_STAGES = {"loss", "retirement"}


# --------------------------------------------------------------------------
# NEM-GEP MERTEKEGYSEG — a darabszam nem mindig repulogep
# --------------------------------------------------------------------------
# Az eles adat: "Germany's Bundestag authorized the purchase of 90 LITENING 5
# targeting pods" -> a nemet Eurofighter-program "merete" 90 lett. Es:
# "the export license for 80 GE F110 engines". Egy celzokonteneres vagy
# hajtomuves darabszam sosem a gepallomany merete.
NON_AIRFRAME_UNIT_RX = re.compile(
    r"\b(?:pods?|engines?|missiles?|munitions?|rounds?|bombs?|"
    r"radars?|sensors?|seekers?|turrets?|guns?|cannons?|launchers?|"
    r"kits?|simulators?|ground stations?|"
    r"consoles?|racks?|pylons?|fuel tanks?|"
    r"spare parts?|spares|shipsets?|antennas?|transmitters?|"
    r"personnel|pilots?|crews?|technicians?|instructors?|students?|"
    r"squadrons?|wings?|bases?|hangars?|facilities|facility|"
    r"million|billion|dollars?|euros?|usd|eur|percent|per cent)\b", re.I)

# GEP-egysegek. Erre azert van szukseg, mert a szam utan gyakran ELOBB all a
# gep-fonev, mint egy tavolabbi nem-gep szo: "12 aircraft to follow as the
# squadron transitions" — itt a 12 GEPET szamol, nem szazadot. A dontest az
# dönti el, MELYIK egyseg-fonev all KOZELEBB a szamhoz.
AIRFRAME_UNIT_RX = re.compile(
    r"\b(?:aircraft|airframes?|jets?|fighters?|helicopters?|helos?|"
    r"planes?|aeroplanes?|airplanes?|examples?|tankers?|bombers?|"
    r"transports?|airlifters?|rotorcraft|uavs?|drones?|"
    r"interceptors?|gunships?|prototypes?|units? of the type|"
    r"[A-Z]{1,3}-\d{1,3}[A-Za-z]?s?)\b")


def _number_windows(text, q, width=70):
    """A darabszam elofordulasainak KOZVETLEN kornyezete.

    A mondat-szintu vizsgalat teved, ha egy mondatban tobb szam van:
    "USMC VMFA-115 conducted its first F-35C flight ... 12 aircraft" —
    a mondatban a "first" es a "12" is szerepel. A dontest a SZAM melletti
    szavak hozzak meg, nem az egesz mondat.
    """
    out = []
    if q is None:
        return out
    needle = str(int(q))
    low = text or ""
    for m in re.finditer(r"(?<![\d,.])" + re.escape(needle) + r"(?![\d,.])",
                        low):
        out.append(low[max(0, m.start() - width):m.end() + width])
    return out


def _number_tails(text, q, width=45):
    """A darabszam UTAN kovetkezo szoveg. Az egyseg-fonev itt all:
    '90 LITENING 5 targeting pods' -> ' LITENING 5 targeting pods'."""
    out = []
    if q is None:
        return out
    needle = str(int(q))
    low = text or ""
    for m in re.finditer(r"(?<![\d,.])" + re.escape(needle) + r"(?![\d,.])",
                        low):
        out.append(low[m.end():m.end() + width])
    return out


def quantity_scope(event, summary=None, quantity=None):
    """Mire vonatkozik EZ a darabszam?

    -> ('programme'|'tranche'|'attrition'|'non_airframe'|'unknown', indoklas)

    A dontes SORRENDBEN: a szam kozvetlen kornyezete, majd a mondat, majd a
    stadium. A szam melletti szavak a legerosebb jelzes — enelkul egy tobb
    szamot tartalmazo mondat rossz hatokort ad.
    """
    text = " ".join(str(x or "") for x in (summary, event.get("summary")))
    stage = resolved_stage(event)
    if quantity is None:
        quantity = event.get("quantity_claimed")
        if quantity in (None, ""):
            quantity = event.get("quantity")
    try:
        quantity = int(quantity) if quantity not in (None, "") else None
    except (TypeError, ValueError):
        quantity = None

    windows = _number_windows(text, quantity)

    # 1. Veszteseg mindent felulir. Egy lezuhant gep nem programmeret.
    if stage in ATTRITION_SCOPE_STAGES or ATTRITION_RX.search(text):
        return "attrition", ("attrition/withdrawal event — the count is "
                             "airframes lost or retired, not programme size")

    # 2. MERTEKEGYSEG: melyik egyseg-fonev all KOZELEBB a szamhoz?
    #    "90 LITENING 5 targeting pods"  -> pods  (nem gep)
    #    "80 GE F110 engines"            -> engines (nem gep)
    #    "12 aircraft ... the squadron"  -> aircraft (gep) — a 'squadron'
    #                                       tavolabb van, ezert nem dont
    for tail in _number_tails(text, quantity):
        non = NON_AIRFRAME_UNIT_RX.search(tail)
        air = AIRFRAME_UNIT_RX.search(tail)
        if non and (not air or non.start() < air.start()):
            return "non_airframe", ("the unit immediately after this figure is "
                                    "'{}', not airframes".format(
                                        non.group(0).lower()))
        if air and (not non or air.start() < non.start()):
            break  # gep-egyseg: a hatokort a tovabbi szabalyok dontik el

    # 3. A SZAM KOZVETLEN kornyezete dont, ha egyertelmu.
    for w in windows:
        prog_hit = PROGRAMME_TOTAL_RX.search(w)
        tranche_hit = TRANCHE_RX.search(w)
        if prog_hit and not tranche_hit:
            return "programme", ("the figure sits in programme-total language "
                                 "('{}')".format(prog_hit.group(0).lower()))
        if tranche_hit and not prog_hit:
            return "tranche", ("the figure sits in tranche or single-airframe "
                               "language ('{}')".format(
                                   tranche_hit.group(0).lower()))

    # 4. Mondat-szint, ha a szam kornyezete nem dontott.
    if TRANCHE_RX.search(text) and not PROGRAMME_TOTAL_RX.search(text):
        return "tranche", ("the reporting describes a tranche, prototype or "
                           "individual airframe, not the programme total")
    if PROGRAMME_TOTAL_RX.search(text) and not TRANCHE_RX.search(text):
        return "programme", "the reporting states a programme-level total"

    # 5. Ha MINDKETTO jelen van es a szam kornyezete sem dontott, a
    #    konzervativ olvasat a reszszallitas: inkabb ne allitsuk a programmeretet.
    if TRANCHE_RX.search(text) and PROGRAMME_TOTAL_RX.search(text):
        return "tranche", ("the reporting mixes tranche and programme-total "
                           "language and the figure's context is ambiguous — "
                           "read conservatively as a tranche")

    # 6. Stadium alapjan, ha a szoveg egyaltalan nem dontott.
    if stage in PROGRAMME_SCOPE_STAGES:
        return "programme", ("pre-contract or contract stage with no tranche "
                             "language — read as programme scope")
    if stage in TRANCHE_SCOPE_STAGES:
        return "tranche", ("execution-stage event ({}) — the count is a "
                           "delivery or production quantity".format(stage))
    return "unknown", "cannot establish whether the count is programme-wide"


def contract_evidenced(event, summary=None):
    """Van-e ELFOGADHATO szerzodes-evidencia?

    Ez a fuggveny az uzbeg hiba kapuja. A W34-ben az elemzoi reteg helyesen
    'negotiation / low confidence / nincs hivatalos megerositesa' allapotot
    irt, az ORBAT megis 'Contract signed x24'-et mutatott. Egy allitas nem
    lehet ket allapotban.

    Visszaad: (bool, indoklas)
    """
    text = " ".join(str(x or "") for x in (summary, event.get("summary")))
    # A stadiumot FELOLDVA olvassuk: a legacy esemenyeken a lifecycle_stage
    # NULL, es nyers olvasassal minden ilyen esemeny "unset"-nek latszott.
    stage = resolved_stage(event)
    if stage not in FIRM_STAGES:
        return False, ("lifecycle stage '{}' is not a contracted stage"
                       .format(stage or "unset"))
    # A tagadas eloszor: egy "no contract has been signed" mondat nem lehet
    # szerzodes-evidencia, barmilyen alairasi szo szerepel is benne.
    has_evidence = bool(CONTRACT_EVIDENCE_RX.search(text))
    if has_evidence and CONTRACT_NEGATED_RX.search(text):
        return False, ("the reporting explicitly states no contract is signed "
                       "yet, despite a '{}' label".format(stage))
    if NEGOTIATION_RX.search(text) and not has_evidence:
        return False, ("stage says '{}' but the reporting describes talks or "
                       "an unconfirmed claim — treated as not contracted"
                       .format(stage))
    if not has_evidence and not event.get("contract_date"):
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

    # A HATOKOR ELOBB DONT. Egy atadott reszszallitas nem NOVELI a rendelesi
    # allomanyt (epp ellenkezoleg: atvezet aktivba), egy lezuhant gep pedig
    # egyaltalan nem beszerzesi tetel.
    # A PROGRAMFAJTA ELOSZOR. Egy MRO-, infrastruktura- vagy kikepzesi
    # programnak nincs gepallomanya, tehat nem is mozgathatja a rendelesi
    # allomanyt. Az eles futas ezt mutatta:
    #
    #   event 273 / pol-ah64-sustai-2026: +96
    #
    # A lengyel AH-64E MRO-kozpontrol szolo megallapodas 96 GEPET adott a
    # rendelesi allomanyhoz, mert a szoveg a tamogatott 96 helikoptert emliti.
    # Ez ugyanaz a duplikacio, csak az MRO-programon keresztul.
    kind = (programme or {}).get("programme_kind") or "acquisition"
    if kind in NO_CANONICAL_QUANTITY or kind in NO_AIRFRAME_ARRIVAL:
        return 0, ("on-order unchanged: a {} programme holds no airframes — "
                   "the quantity in this reporting refers to the fleet it "
                   "supports, not to aircraft being ordered".format(
                       PROGRAMME_KINDS.get(kind, kind).lower()))

    scope, scope_why = quantity_scope(event, summary)
    if scope == "attrition":
        return 0, ("on-order unchanged: " + scope_why)
    if scope == "non_airframe":
        return 0, ("on-order unchanged: " + scope_why)
    if scope == "tranche":
        return 0, ("on-order unchanged: " + scope_why + " — a delivery moves "
                   "airframes from on-order to active rather than adding to it")
    if scope == "unknown":
        return 0, ("on-order unchanged: " + scope_why)

    ok, why = contract_evidenced(event, summary)
    if not ok:
        return 0, "on-order unchanged: " + why

    if programme is None:
        # PROGRAMME NELKUL NEM MOZDULHAT A BASELINE. Az eles futas ket ilyen
        # sort adott:
        #     event 282 / None: +12
        #     event 278 / None: +2
        # Ha az esemenyt nem tudtuk programhoz kotni (nincs orszag- vagy
        # tipus-feloldas), akkor azt sem tudjuk, hogy ujramondas-e egy meglevo
        # programrol. A biztonsagos valasz a nulla: az ismeretlen nem novekedes.
        return 0, ("on-order unchanged: this event is not attached to a "
                   "programme, so it cannot be distinguished from a restatement "
                   "of one — resolve the country/type first")

    # Az on_order KIZAROLAG a SZERZODOTT allomanybol szarmazhat. Egy tervezett
    # programtotal ("148 planned serial production") nem rendelesi allomany.
    base = programme.get("contracted_quantity")
    if base in (None, ""):
        base = programme.get("canonical_quantity")
    try:
        base = int(base) if base not in (None, "") else None
    except (TypeError, ValueError):
        base = None

    # A LENGYEL APACHE-KAPU. Ha a program mar ismeri ezt a darabszamot, az
    # ujabb cikk MEGERSITES, nem uj rendeles.
    if base is not None and q <= base:
        return 0, ("on-order unchanged: programme {} already records {} "
                   "contracted aircraft — this reporting restates part of the "
                   "same programme, it is not an additional order".format(
                       programme.get("programme_id"), base))
    if base is not None and q > base:
        return q - base, ("contracted quantity revised {} -> {}; only the "
                          "difference enters on-order".format(base, q))
    return q, ("programme had no contracted quantity — {} recorded".format(q))


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


def seen_or(event, now):
    """Az esemeny megfigyelesi datuma, vegso esetben a mostani nap."""
    return (_iso(event.get("new_evidence_at")) or _iso(event.get("event_date"))
            or now.strftime("%Y-%m-%d"))


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
    # A stadiumot FELOLDVA olvassuk. A nyers mezo a legacy esemenyeken NULL,
    # ezert a programok eletciklusa korabban sosem lepett elore (az eles dry
    # run minden nagy programon 'stage=None'-t mutatott).
    ev_stage = resolved_stage(event)
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

    # --- 2. kanonikus darabszam: HATOKOR-TUDATOSAN, felulirassal ---
    q = event.get("quantity_claimed")
    if q in (None, ""):
        q = event.get("quantity")
    try:
        q = int(q) if q not in (None, "") else None
    except (TypeError, ValueError):
        q = None
    if q and q > 0:
        scope, scope_why = quantity_scope(event, summary)
        prog_kind = p.get("programme_kind") or "acquisition"
        text = " ".join(str(x or "") for x in (summary, event.get("summary")))

        if prog_kind in NO_CANONICAL_QUANTITY:
            # Egy veszteseg- vagy tamogatasi programnak nincs "programmerete".
            obs = list(p.get("observed_quantities") or [])
            obs.append({"quantity": q, "scope": scope, "as_of": seen_or(event, now),
                        "source": article_id})
            patch["observed_quantities"] = obs[-40:]
            changes.append(
                "quantity {} recorded as an observation only — a {} programme "
                "carries no canonical size".format(
                    q, PROGRAMME_KINDS.get(prog_kind, prog_kind).lower()))
        elif scope == "non_airframe":
            obs = list(p.get("observed_quantities") or [])
            obs.append({"quantity": q, "scope": scope, "as_of": seen_or(event, now),
                        "source": article_id})
            patch["observed_quantities"] = obs[-40:]
            changes.append(
                "quantity {} NOT applied — {}".format(q, scope_why))
        elif scope != "programme":
            # EZ A JAVITAS LENYEGE. Egy reszszallitas, prototipus vagy
            # lezuhant gep darabszama nem allithatja a program meretet.
            obs = list(p.get("observed_quantities") or [])
            obs.append({"quantity": q, "scope": scope, "as_of": seen_or(event, now),
                        "source": article_id})
            patch["observed_quantities"] = obs[-40:]
            changes.append(
                "quantity {} NOT applied to the programme total — {}".format(
                    q, scope_why))
        else:
            # ==============================================================
            # KET KULON DARABSZAM: SZERZODOTT es TERVEZETT
            # ==============================================================
            # Az eles dry run ezt mutatta meg:
            #   tur-kaan-2026    szerzodes 20,  tervezett sorozatgyartas 148
            #   ukr-gripen-2025  szerzodes 16,  LOI-plafon "up to 150"
            #   deu-eurofighter  szerzodes 20,  szelesebb program ~90
            #
            # A korabbi valtozat ezeket ELLENTMONDASNAK vette, es az egyiket
            # eldobta. Pedig MINDKETTO igaz — csak nem ugyanaz a dolog. Ez
            # ugyanaz a hibaosztaly, mint az osszeadas, csak harmadik alakban:
            # nem halmozas, nem feluliras, hanem OSSZEMOSAS.
            #
            #   contracted_quantity — ami firm szerzodes alatt van
            #   planned_quantity    — a bejelentett/tervezett teljes program
            #   canonical_quantity  — a szarmaztatott fejszam: contracted,
            #                         ha van, kulonben planned
            #
            # Az on_order KIZAROLAG a contracted-bol szarmazhat.
            ok, _why = contract_evidenced(event, summary)
            is_ceiling = bool(re.search(r"\b(?:up to|as many as|as much as)\b",
                                        text, re.I))
            target = "contracted" if (ok and not is_ceiling) else "planned"
            # A BASIS a forras erossege, nem a megfogalmazas hataroza. Egy
            # "local reports suggest as many as 250" mondat programtotal-
            # nyelvezetu, de sajtobecsles — nem irhat felul egy bejelentest.
            if ok and not is_ceiling:
                new_basis = "contract"
            elif ESTIMATE_RX.search(text):
                new_basis = "estimate"
            elif PROGRAMME_TOTAL_RX.search(text):
                new_basis = "announced"
            else:
                new_basis = "reported"

            cur = p.get("{}_quantity".format(target))
            try:
                cur = int(cur) if cur not in (None, "") else None
            except (TypeError, ValueError):
                cur = None
            old_basis = p.get("{}_basis".format(target)) or "unknown"
            rank = {"contract": 3, "announced": 2, "reported": 1,
                    "estimate": 1, "unknown": 0}
            stronger = rank.get(new_basis, 0) > rank.get(old_basis, 0)
            equal = rank.get(new_basis, 0) == rank.get(old_basis, 0)
            reduction = bool(REDUCTION_RX.search(text))
            label = ("contracted quantity" if target == "contracted"
                     else "planned programme total")

            if cur is None:
                patch["{}_quantity".format(target)] = q
                patch["{}_basis".format(target)] = new_basis
                patch["{}_as_of".format(target)] = (
                    _iso(event.get("event_date")) or now.strftime("%Y-%m-%d"))
                changes.append("{} set to {} ({}) — {}".format(
                    label, q, new_basis, scope_why))
            elif q == cur:
                changes.append("{} {} restates the existing figure — NOT "
                               "added".format(label, q))
            elif stronger or (equal and q > cur) or reduction:
                hist = list(p.get("superseded_quantities") or [])
                hist.append({"quantity": cur, "basis": old_basis,
                             "field": target,
                             "as_of": _iso(p.get("{}_as_of".format(target))),
                             "superseded_at": now.strftime("%Y-%m-%d"),
                             "source": article_id})
                patch["superseded_quantities"] = hist
                patch["{}_quantity".format(target)] = q
                patch["{}_basis".format(target)] = new_basis
                patch["{}_as_of".format(target)] = (
                    _iso(event.get("event_date")) or now.strftime("%Y-%m-%d"))
                changes.append("{} revised {} -> {} ({}); previous value "
                               "retained in history".format(
                                   label, cur, q,
                                   "{} supersedes {}".format(
                                       new_basis, old_basis) if stronger
                                   else "explicit reduction reported"
                                   if reduction else
                                   "larger figure at equal basis"))
            elif q < cur:
                # EGY PLAFON ALATTI KISEBB SZAM NEM ELLENTMONDAS.
                # Az ukran Gripen "up to 150" szandeknyilatkozat alatt a 20 es a
                # 16 gepes tetel normalis reszhalmaz. A korabbi valtozat mind a
                # harmat "konfliktuskent" jelezte elemzoi dontesre, holott
                # semmi nem mond ellent semminek.
                obs = list(p.get("observed_quantities") or [])
                obs.append({"quantity": q, "scope": "within_planned",
                            "basis": new_basis, "against": cur,
                            "as_of": seen_or(event, now), "source": article_id})
                patch["observed_quantities"] = obs[-40:]
                changes.append(
                    "{} of {} sits within the recorded {} — recorded as a "
                    "batch or interim figure, not a contradiction".format(
                        label, q, cur))
            else:
                # Valodi ellentmondas: a szam NAGYOBB a rogzitettnel, de
                # gyengebb evidencian all.
                conflicts = list(p.get("quantity_conflicts") or [])
                conflicts.append({
                    "quantity": q, "basis": new_basis, "field": target,
                    "against": cur, "as_of": seen_or(event, now),
                    "source": article_id,
                    "note": ("larger {} on weaker evidence than the recorded "
                             "{} — kept {} and flagged".format(
                                 label, cur, cur))})
                patch["quantity_conflicts"] = conflicts[-20:]
                changes.append(
                    "{} {} exceeds the recorded {} on weaker evidence — KEPT "
                    "at {}, flagged for review".format(label, q, cur, cur))

            # A szarmaztatott fejszam: a firm szerzodes elonyt kap.
            contracted = patch.get("contracted_quantity",
                                   p.get("contracted_quantity"))
            planned = patch.get("planned_quantity", p.get("planned_quantity"))
            if contracted not in (None, ""):
                patch["canonical_quantity"] = contracted
                patch["quantity_basis"] = "contract"
                patch["canonical_source"] = "contracted"
            elif planned not in (None, ""):
                patch["canonical_quantity"] = planned
                patch["quantity_basis"] = (
                    patch.get("planned_basis") or p.get("planned_basis")
                    or "reported")
                patch["canonical_source"] = "planned"
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

def _quantity_reading(p):
    """Egy mondat, ami MEGMONDJA, hogyan kell a ket szamot olvasni.

    Enelkul az olvaso vagy osszeadja oket, vagy ellentmondasnak veszi. A
    "20 contracted of a planned 148" nem ellentmondas, hanem a program allapota.
    """
    c, pl = p.get("contracted_quantity"), p.get("planned_quantity")
    if c not in (None, "") and pl not in (None, ""):
        if int(pl) > int(c):
            return ("{} under firm contract of a planned {} — these are "
                    "different measures and are never summed".format(c, pl))
        if int(pl) == int(c):
            return "{} contracted, matching the planned total".format(c)
        return ("{} under contract against a planned {} — the planned figure "
                "is lower than the contracted one; verify".format(c, pl))
    if c not in (None, ""):
        return "{} under firm contract; no wider programme total stated".format(c)
    if pl not in (None, ""):
        return ("{} planned or announced; no firm contract quantity "
                "evidenced".format(pl))
    return "no programme quantity established in the reporting"


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
        # A KET DARABSZAM KULON. A riport mindkettot mutatja, es sosem adja
        # ossze oket: a torok KAAN 20 szerzodott gepe es a 148 tervezett
        # sorozatgyartasa ket kulonbozo allitas, nem ellentmondas.
        "contracted_quantity": p.get("contracted_quantity"),
        "contracted_basis": p.get("contracted_basis"),
        "planned_quantity": p.get("planned_quantity"),
        "planned_basis": p.get("planned_basis"),
        "canonical_quantity": p.get("canonical_quantity"),
        "canonical_source": p.get("canonical_source"),
        "quantity_basis": p.get("quantity_basis"),
        "quantity_reading": _quantity_reading(p),
        "quantity_conflicts": p.get("quantity_conflicts") or [],
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
