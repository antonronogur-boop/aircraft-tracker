# -*- coding: utf-8 -*-
"""COMMAND AIR INTELLIGENCE BRIEF v2 — 4 vezetoi oldal + Sources & Legend.

ONALLO TERMEK. A brief a heti jelentes MAR ELKESZULT, QA-n atment
objektumaibol epul (developments, key_judgements, priority_watch,
intelligence_gaps, since_last_week, programme maturity), de a reszletes
jelentes NELKUL is erthetonek kell lennie. Ezert a nyomonkovetes elsodlegesen
az EREDETI FORRASRA mutat (S-xx -> eredeti cikk), nem egy masik Aircraft
Tracker oldalra. A D-xx / KJ-xx kulcsok csak a belso auditnyomban maradnak.

Nem masodik pipeline. Ket determinisztikus reteg kerul fole:
  * HUNGARY RELEVANCE (ac_hungary) — kulon dimenzio a significance mellett;
  * COVERAGE (coverage_audit) — "nincs valtozas" vs "nem latunk oda".

Az egyetlen uj, magasabb szintu szoveg az EXECUTIVE SYNTHESIS (bottom line,
"why Hungary should care", rovid vezetoi atfogalmazas). Ez jelolt, minden
mondata hivatkozik, nem hozhat uj szamot vagy uj orszagot, nem hozhatja
vissza a visszatartott iteletet — es ha a validacio elbuktatja, a
determinisztikus valtozat marad.

v2 szabalyok (PO, 2026-11):
  * page 1: legfeljebb 3 PRIMARY KJ; LOW/MINIMAL HU-relevancia csak kivetellel
    (significance 5 + high confidence, vagy a PO strategic watch listaja);
    a tobbi fontos globalis tetel SECONDARY WATCH sor.
  * NINCS levagott vezetoi mondat: a szoveg mindig egesz mondatokbol all
    (nincs "…"). Ha valami hosszu, a modell rovidit (validalt), kulonben az
    egesz mondat marad, es a layout alkalmazkodik.
  * page 2 ures helye: REGIONAL COLLECTION REQUIREMENTS (gap -> kerdes ->
    elvart megfigyeles), nem toltelekhir.
  * page 3: kompakt regiok + CAPABILITY MATURITY MATRIX + Executive change
    table.
  * page 4: OUTLOOK & EXPECTED OBSERVABLES (nem esemenynaptar).
  * page 5: SOURCE REGISTER (kattinthato eredeti cim) + teljes LEGEND.
  * minden oldalon azonos micro-legend.

A PDF (web print) es a Word (.docx) export ugyanebbol az adatmodellbol
renderel — a tartalom igy azonos a ket formatumban.
"""
import json
import re
from pathlib import Path

import ac_hungary as hu

BRIEF_SCHEMA = "command_brief_v2"
ROOT = Path(__file__).resolve().parent.parent

HORIZON_ORDER = {"immediate": 0, "<12 months": 1, "1-3 years": 2,
                 ">3 years": 3, "unknown": 4}
PRE_CONTRACT = {"requirement", "rfi_sources_sought", "rfp", "bid", "selection",
                "national_approval", "export_approval"}

# Szovegkeretek KARAKTERBEN — de SOSEM vagunk mondat kozepen. Ha egy mondat
# egymagaban hosszabb, egeszben marad (es a vezetoi szerkeszto rovidit).
BUDGET = {
    "statement": (280, 1), "what_changed": (240, 2), "assessment": (260, 2),
    "why_hu": (230, 2), "next_observable": (170, 1), "alternative": (190, 1),
    "row_what": (230, 2), "row_effect": (210, 2), "row_next": (150, 1),
    "row_hu": (170, 1), "item_assessment": (200, 1), "watch_why": (170, 1),
    "watch_next": (170, 1), "gap": (260, 2), "outlook": (170, 1),
    "secondary": (170, 1),
}
MAX_PRIMARY = 3
MAX_SECONDARY = 3
MAX_SYNTHESIS = 2
MAX_PAGE2_ROWS = 6
MAX_REQUIREMENTS = 8
MAX_P3_ITEMS = 3
MAX_MATURITY = 8
MAX_GLOBAL_ITEMS = 4
MAX_WATCH = 5
MAX_GAPS = 5
MAX_OUTLOOK = 5
MAX_CHANGE_ROWS = 6

STATUS_LINE = "EDITABLE EXPORT — GENERATED FROM AIRCRAFT TRACKER"

MICRO_LEGEND = ("HU = relevance to Hungary / MH / NATO Central-Eastern Europe · "
                "SIG = air-power significance 1–5 · CONF = analytic confidence · "
                "S-xx = source (p. 5) · dashed border = collection gap · "
                "no hotspot ≠ no activity")

MATURITY_COLUMNS = ["Intent", "Committed", "Contracted", "Fielding", "IOC",
                    "FOC"]
STAGE_TO_COLUMN = {
    "requirement": "Intent", "rfi_sources_sought": "Intent", "rfp": "Intent",
    "bid": "Intent", "other": "Intent",
    "selection": "Committed", "national_approval": "Committed",
    "export_approval": "Committed",
    "contract_signed": "Contracted", "production": "Contracted",
    "upgrade_programme": "Contracted",
    "delivery": "Fielding", "ioc": "IOC", "foc": "FOC",
}
STAGE_LABELS = {
    "requirement": "requirement", "rfi_sources_sought": "RFI", "rfp": "RFP",
    "bid": "bid", "selection": "selection",
    "national_approval": "national approval",
    "export_approval": "export approval",
    "contract_signed": "contract", "production": "production",
    "delivery": "delivery", "ioc": "IOC", "foc": "FOC",
    "upgrade_programme": "upgrade", "retirement": "retirement",
    "loss": "loss", "other": "other",
}
DOMAIN_LABELS = {
    "fighter_strike": "Fighter / strike", "attack_helicopter": "Attack helicopter",
    "air_mobility_rotary": "Rotary lift", "air_mobility_fixed": "Airlift",
    "uncrewed_cca": "Uncrewed / CCA", "counter_uas": "Counter-UAS",
    "isr_aew_sigint": "ISR / AEW", "tanker": "Tanker", "training": "Training",
    "maritime_patrol": "Maritime patrol", "other": "Other",
}

# A TELJES jelmagyarazat — allando, hetrol hetre nem valtozik. A web, a PDF
# es a Word ugyanezt a szoveget rendereli.
LEGEND = [
    {"title": "Hungary relevance (HU)", "items": [
        ["HIGH", "Directly affects Hungary, its airspace, MH capability "
                 "planning or NATO's Central/Eastern European air posture."],
        ["MEDIUM", "Affects the regional air picture or Allied posture "
                   "around Hungary, but not Hungary directly."],
        ["LOW", "A weak or indirect tie (distant actor, supplier link, "
                "doctrinal interest)."],
        ["MINIMAL", "No direct link to Hungary, MH or NATO Central/Eastern "
                    "Europe identified."]]},
    {"title": "Air-power significance (SIG)", "items": [
        ["1/5", "Routine; no capability effect."],
        ["2/5", "Minor or administrative change."],
        ["3/5", "A real but limited capability change."],
        ["4/5", "A major national capability change."],
        ["5/5", "A change with regional or global strategic weight."]]},
    {"title": "Analytic confidence (CONF)", "items": [
        ["LOW", "First indication; thin or single-source reporting."],
        ["MODERATE", "Credible reporting; not independently confirmed, or a "
                     "single evidence lineage."],
        ["HIGH", "Multiple independent lineages or authoritative primary "
                 "evidence."]]},
    {"title": "Effect horizon", "items": [
        ["immediate", "The effect exists now."],
        ["<12 months", "Earliest operational effect within a year."],
        ["1–3 years", "Earliest operational effect in one to three years."],
        [">3 years", "No near-term operational effect."],
        ["unknown", "Timing is not established in reporting."]]},
    {"title": "Collection status", "items": [
        ["ADEQUATE", "At least 4 events from at least 2 sources in 60 days."],
        ["PARTIAL", "Some reporting, below the adequate threshold."],
        ["GAP", "No reporting reached the collection in 60 days; absence of "
                "reporting is not evidence of inactivity."],
        ["NO MATERIAL CHANGE IDENTIFIED", "Collection was at least PARTIAL "
                                          "and nothing material was "
                                          "assessed."]]},
    {"title": "Analytical terminology", "items": [
        ["FACT", "What the source states, attributed."],
        ["ASSESSMENT", "Our judgement of what the fact means."],
        ["CAPABILITY DELTA", "What changes in capability terms."],
        ["POLICY / INTENT", "A stated plan or requirement; no commitment."],
        ["FIELDING", "Aircraft or systems are being delivered to units."],
        ["IOC", "Initial operational capability: a first unit can conduct "
                "the mission."],
        ["FOC", "Full operational capability at planned scale."],
        ["OPERATIONAL", "Employed in its role (IOC or beyond)."],
        ["NEXT OBSERVABLE", "The next concrete, checkable sign that would "
                            "confirm or move the assessment."],
        ["INTELLIGENCE GAP", "A question collection could not answer that "
                             "would change the assessment."]]},
]
PRINCIPLES = [
    "significance ≠ confidence: how much it matters is not how sure we are.",
    "procurement ≠ operational capability: a contract or delivery is not "
    "combat power.",
    "delivery ≠ IOC: aircraft handed over are not a declared operational "
    "unit.",
    "multiple articles ≠ independent evidence lineage: outlets restating "
    "one release are one lineage.",
    "official statement ≠ independent confirmation: state-controlled "
    "sources count as one lineage and are always attributed.",
]


# --------------------------------------------------------------------------
# Szoveg: csak egesz mondatok
# --------------------------------------------------------------------------

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“])")


def sentence(text):
    """Nyers mezo -> mondat: nagy kezdobetu, zaro irasjel."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    if t[-1] not in ".!?":
        t = t.rstrip(";:,—- ") + "."
    return t


def fit(text, limit, max_sentences=None):
    """Egesz mondatok a keretig. SOHA nem vag mondatot es nem tesz '…'-t:
    ha az elso mondat egymagaban hosszabb, egeszben visszaadjuk."""
    t = sentence(text)
    if not t:
        return ""
    sents = _SENT_SPLIT.split(t)
    if max_sentences:
        sents = sents[:max_sentences]
    out = sents[0]
    for x in sents[1:]:
        cand = out + " " + x
        if len(cand) > limit:
            break
        out = cand
    return out


def _fit(key, text):
    lim, n = BUDGET[key]
    return fit(text, lim, n)


def _ref(i):
    return "D-{:02d}".format(i + 1)


def _sig(d):
    try:
        return max(1, min(5, int(d.get("significance") or 1)))
    except (TypeError, ValueError):
        return 1


def _countries_rx(countries_by_id):
    pairs = []
    for cid, c in countries_by_id.items():
        for n in [c.get("name")] + list(c.get("aliases") or []):
            if n and len(n) >= 4 and not n.isupper():
                pairs.append((n, cid))
    pairs.sort(key=lambda p: -len(p[0]))
    if not pairs:
        return None, {}
    rx = re.compile(r"\b(" + "|".join(re.escape(p[0]) for p in pairs) + r")\b")
    return rx, {p[0]: p[1] for p in pairs}


def named_country_ids(text, countries_by_id, _cache={}):
    key = id(countries_by_id)
    if key not in _cache:
        _cache.clear()
        _cache[key] = _countries_rx(countries_by_id)
    rx, by_name = _cache[key]
    if rx is None:
        return []
    out = []
    for m in rx.finditer(text or ""):
        cid = by_name.get(m.group(1))
        if cid and cid not in out:
            out.append(cid)
    return out


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


# --------------------------------------------------------------------------
# 1. Fejlemenyek annotalasa (ref, orszag, HU-relevancia) — a REPORT-ba is
# --------------------------------------------------------------------------

def annotate_developments(payload, countries_by_id, events_by_id=None,
                          cfg=None):
    cfg = cfg or hu.load_config()
    name_to_id = {c.get("name"): cid for cid, c in countries_by_id.items()
                  if c.get("name")}
    annex = {a.get("event_id"): a for a in (payload.get("annex_events") or [])}
    for i, d in enumerate(payload.get("developments") or []):
        d["ref"] = d.get("ref") or _ref(i)
        ids = list(d.get("country_ids") or [])
        if not ids:
            for eid in d.get("event_ids") or []:
                e = (events_by_id or {}).get(eid)
                cid = (e or {}).get("country_id")
                if not cid:
                    cid = name_to_id.get((annex.get(eid) or {}).get("country")
                                         or "")
                if cid and cid not in ids:
                    ids.append(cid)
        if not ids:
            ids = named_country_ids(d.get("title") or "", countries_by_id)[:1]
        d["country_ids"] = ids
        d["countries"] = [(countries_by_id.get(c) or {}).get("name") or c
                          for c in ids]
        # Mindig ujraszamoljuk: a HU-modell verzioja valtozhat.
        d["hu_relevance"] = hu.score_item(d, ids, countries_by_id, cfg)
    for i, b in enumerate(payload.get("background_items") or []):
        b["ref"] = b.get("ref") or "B-{:02d}".format(i + 1)
    return payload.get("developments") or []


def is_material(d):
    """Anyagi-e a fejlemeny a vezetoi brief szamara (nincs toltelek)."""
    sig = _sig(d)
    level = (d.get("hu_relevance") or {}).get("level")
    no_change = "no capability change" in str(
        d.get("capability_delta") or "").lower()
    if no_change and sig < 3 and level != "HIGH":
        return False
    return sig >= 3 or (level == "HIGH" and sig >= 2)


def _barred_event_ids(payload):
    out = set()
    for j in payload.get("judgements_requiring_review") or []:
        out |= set(j.get("supporting_event_ids") or [])
    return out


def _system_alternative(d):
    """'What would make this wrong' a bizonyitek ALLAPOTABOL (jelolt)."""
    stage = (d or {}).get("lifecycle_stage")
    if ((d or {}).get("independent_lineages") or 1) <= 1:
        return ("All supporting reporting traces to a single evidence chain, "
                "so independent confirmation could still overturn it.")
    if stage in PRE_CONTRACT:
        return ("The reporting describes a plan or authorisation, not a "
                "contract, and the programme may stall before signature.")
    if (d or {}).get("novelty") in ("continuation", "confirmation_of_known"):
        return ("This may restate an already-known programme rather than "
                "mark a new decision.")
    if stage in ("contract_signed", "production"):
        return ("A signed contract can still slip or be re-scoped; first "
                "delivery and IOC dates are the test.")
    if stage in ("delivery", "ioc", "foc"):
        return ("Delivery is not operational capability; crews, weapons and "
                "sustainment decide when the effect is real.")
    if stage == "loss":
        return ("The cause is not established, and the loss may be an "
                "accident rather than adversary action.")
    return ("The activity may be routine rather than a change in posture; "
            "its duration or repetition is the test.")


def _hu_view(h):
    return {"level": h.get("level"), "score": h.get("score"),
            "factors": [{"label": f["label"], "points": f["points"]}
                        for f in h.get("factors") or []],
            "rationale": h.get("rationale")}


# --------------------------------------------------------------------------
# 2. SOURCE REGISTER — S-xx az EREDETI forrasra
# --------------------------------------------------------------------------

def _host(url):
    m = re.match(r"^[a-z]+://([^/:?#]+)", str(url or "").strip().lower())
    return m.group(1)[4:] if m and m.group(1).startswith("www.") else (
        m.group(1) if m else "")


class SourceRegister(object):
    """Az eredeti cikkek nyilvantartasa. Az S-szamok a brief olvasasi
    sorrendjeben keletkeznek (page 1 -> page 4), igy a lista kovetheto."""

    def __init__(self, payload, events_by_id=None, articles_by_id=None,
                 sources_by_id=None, countries_by_id=None):
        import ac_intel  # lusta: csak a lineage-szabaly miatt
        self._intel = ac_intel
        self.events = events_by_id or {}
        self.articles = articles_by_id or {}
        self.sources = sources_by_id or {}
        self.countries = countries_by_id or {}
        self.annex = {a.get("event_id"): a
                      for a in (payload.get("annex_events") or [])}
        self.cfg = _load_json(ROOT / "config" / "coverage_sources.json", {})
        cat = _load_json(ROOT / "data" / "sources.json", [])
        self.catalog = {}
        for s in cat if isinstance(cat, list) else []:
            h = _host(s.get("homepage") or s.get("rss_url"))
            if h:
                self.catalog[h] = s
        # Jelolt (meg nem gyujtott) hivatalos forrasok domainje -> tier.
        self.candidate_tiers = {}
        for c in self.cfg.get("candidates") or []:
            h = _host(c.get("homepage"))
            if h:
                self.candidate_tiers[h] = (c.get("tier"), c.get("name"))
        self.entries, self.by_key, self.lineage_labels = [], {}, {}

    def _article_for(self, eid):
        e = self.events.get(eid) or {}
        a = self.articles.get(e.get("article_id") or "") or {}
        ax = self.annex.get(eid) or {}
        url = a.get("url") or ax.get("article_url")
        title = a.get("title") or ax.get("article_title")
        if not (url or title):
            return None, None
        key = e.get("article_id") or url or title
        return key, {
            "article_id": e.get("article_id"), "url": url, "title": title,
            "publish_date": a.get("publish_date"),
            "source_id": a.get("source_id"),
            "event": e or ax,
        }

    def _describe(self, info):
        url = info["url"]
        host = _host(url)
        src = self.sources.get(info.get("source_id") or "") or {}
        cat = self.catalog.get(host) or {}
        state = self._intel.state_group_of_url(url)
        tiers = self.cfg.get("existing_source_tiers") or {}
        sid = info.get("source_id") or cat.get("source_id")
        cand = None
        for h, v in self.candidate_tiers.items():
            if host == h or host.endswith("." + h):
                cand = v
        tier_key = ("mod" if state else tiers.get(sid or "")
                    or (cand or (None,))[0]
                    or self.cfg.get("default_tier") or "specialist_defence")
        rank = (self.cfg.get("tier_rank") or {}).get(tier_key, 3)
        label = (self.cfg.get("tier_labels") or {}).get(tier_key, tier_key)
        if state:
            label = "State-controlled official (attributed; not independent)"
        return {
            "source_name": src.get("source_name") or cat.get("source_name")
            or (cand or (None, None))[1] or host or "—",
            "source_id": sid,
            "source_type": label,
            "tier": "Tier {}".format(rank),
            "language": src.get("language") or ("en" if cat else "—"),
            "state_controlled": bool(state),
            # Lineage: allami csoport > azonositott primer forras > cikk.
            "_chain": ("state:" + state if state else
                       "origin:" + str(info["event"].get(
                           "originating_evidence_id"))
                       if (info["event"] or {}).get("originating_evidence_id")
                       else "article:" + str(info.get("article_id")
                                             or url or info.get("title"))),
        }

    def ids_for_events(self, event_ids, used_by):
        out = []
        for eid in event_ids or []:
            key, info = self._article_for(eid)
            if key is None:
                continue
            ent = self.by_key.get(key)
            if ent is None:
                desc = self._describe(info)
                chain = desc.pop("_chain")
                if chain not in self.lineage_labels:
                    self.lineage_labels[chain] = "L-{:02d}".format(
                        len(self.lineage_labels) + 1)
                ev = info["event"] or {}
                cid = ev.get("country_id")
                country = ((self.countries.get(cid) or {}).get("name")
                           if cid else ev.get("country")) or "—"
                ent = dict(desc, **{
                    "id": "S-{:02d}".format(len(self.entries) + 1),
                    "title": info["title"] or info["url"],
                    "url": info["url"],
                    "publication_date": str(info.get("publish_date")
                                            or "")[:10] or None,
                    "event_date": str(ev.get("event_date") or "")[:10]
                    or None,
                    "country": country,
                    "lineage": self.lineage_labels[chain],
                    "used_by": [],
                })
                self.entries.append(ent)
                self.by_key[key] = ent
            if used_by and used_by not in ent["used_by"]:
                ent["used_by"].append(used_by)
            if ent["id"] not in out:
                out.append(ent["id"])
        return out

    def for_dev(self, d, used_by):
        return self.ids_for_events(d.get("event_ids") or [], used_by)


# --------------------------------------------------------------------------
# 3. Page 1 — PRIMARY (max 3) + SECONDARY WATCH + CEE terkep
# --------------------------------------------------------------------------

def _strategic_exception(item_text, sig, confidence, cfg):
    if sig >= 5 and confidence == "high":
        return "strategic exception: significance 5 at high confidence"
    for pat in ((cfg.get("strategic_watch") or {}).get("patterns") or []):
        try:
            if re.search(pat, item_text or "", re.I):
                return "strategic exception: PO strategic watch ({})".format(
                    pat)
        except re.error:
            continue
    return None


def page1(payload, devs, countries_by_id, cfg, reg):
    kjs = payload.get("key_judgements") or []
    barred = _barred_event_ids(payload)
    by_event = {}
    for d in devs:
        for eid in d.get("event_ids") or []:
            by_event.setdefault(eid, []).append(d)

    cands, covered = [], set()
    for k in kjs:
        sup = []
        for eid in k.get("supporting_event_ids") or []:
            for d in by_event.get(eid, []):
                if d not in sup:
                    sup.append(d)
        if sup:
            best = sorted(sup, key=lambda d: hu.rank_key(
                d.get("hu_relevance"), _sig(d), d.get("confidence"),
                d.get("effect_timing")))[0]
            h = best.get("hu_relevance") or {}
            sig = max(_sig(d) for d in sup)
        else:
            best = None
            ids = named_country_ids(" ".join([k.get("judgement") or "",
                                              k.get("basis") or ""]),
                                    countries_by_id)
            h = hu.score_item(k, ids, countries_by_id, cfg)
            sig = 3
        covered |= {d["ref"] for d in sup}
        cands.append({"kind": "kj", "k": k, "sup": sup, "best": best,
                      "h": h, "sig": sig, "conf": k.get("confidence"),
                      "horizon": k.get("effect_timing")
                      or (best or {}).get("effect_timing") or "unknown"})
    for d in devs:
        h = d.get("hu_relevance") or {}
        if d["ref"] in covered or not is_material(d):
            continue
        cands.append({"kind": "dev", "d": d, "h": h, "sig": _sig(d),
                      "conf": d.get("confidence"),
                      "horizon": d.get("effect_timing") or "unknown",
                      "barred": bool(set(d.get("event_ids") or []) & barred)})
    for c in cands:
        c["rank"] = hu.rank_key(c["h"], c["sig"], c["conf"], c["horizon"])
    cands.sort(key=lambda c: c["rank"])

    primary, secondary, n_xs = [], [], 0
    for c in cands:
        lvl = c["h"].get("level")
        text = (c["k"].get("judgement") if c["kind"] == "kj"
                else (c["d"].get("title") or "") + " " +
                (c["d"].get("fact") or ""))
        reason = None
        if lvl in ("HIGH", "MEDIUM"):
            reason = "Hungary relevance {}".format(lvl)
        else:
            reason = _strategic_exception(text, c["sig"], c["conf"], cfg)
        # Uj (XS) itelet csak QA-n atment, nem visszatartott alapbol.
        if c["kind"] == "dev" and (c.get("barred") or n_xs >= MAX_SYNTHESIS
                                   or lvl not in ("HIGH", "MEDIUM")):
            reason = None
        if reason and len(primary) < MAX_PRIMARY:
            if c["kind"] == "dev":
                n_xs += 1
            c["reason"] = reason
            primary.append(c)
        else:
            secondary.append(c)

    items = []
    for c in primary:
        if c["kind"] == "kj":
            k, best, sup = c["k"], c["best"], c["sup"]
            alt = k.get("alternative_explanation")
            items.append({
                "id": k.get("id"), "origin": "report_key_judgement",
                "statement": _fit("statement", k.get("judgement")),
                "what_changed": _fit("what_changed",
                                     (best or {}).get("capability_delta")
                                     or (best or {}).get("fact")
                                     or k.get("basis")),
                "assessment": _fit("assessment", k.get("assessment")),
                "next_observable": _fit("next_observable", (
                    k.get("indicators") or (best or {}).get(
                        "indicators_to_watch") or [None])[0]),
                "alternative_explanation": _fit(
                    "alternative", alt or _system_alternative(best)),
                "alternative_origin": "report" if alt
                else "system_evidence_state",
                "headline": (best or {}).get("title"),
                "refs": [k.get("id")] + [d["ref"] for d in sup],
                "sources": [s for d in sup
                            for s in reg.for_dev(d, k.get("id"))],
                "countries": sorted({x for d in sup
                                     for x in d.get("countries") or []}),
            })
        else:
            d = c["d"]
            xid = "XS-{:02d}".format(len([i for i in items
                                          if i["origin"] ==
                                          "executive_synthesis"]) + 1)
            items.append({
                "id": xid, "origin": "executive_synthesis",
                "statement": _fit("statement", d.get("title")),
                "what_changed": _fit("what_changed",
                                     d.get("capability_delta")
                                     or d.get("fact")),
                "assessment": _fit("assessment", d.get("so_what")),
                "next_observable": _fit("next_observable", (
                    d.get("indicators_to_watch") or [None])[0]),
                "alternative_explanation": _fit("alternative",
                                                _system_alternative(d)),
                "alternative_origin": "system_evidence_state",
                "headline": d.get("title"),
                "refs": [d["ref"]], "traces_to": [d["ref"]],
                "sources": reg.for_dev(d, xid),
                "countries": d.get("countries") or [],
            })
        h = c["h"]
        items[-1].update({
            "hu_relevance": _hu_view(h),
            "significance": c["sig"],
            "significance_label": hu.significance_label(c["sig"]),
            "confidence": c["conf"], "horizon": c["horizon"],
            "why_hungary": _fit("why_hu", h.get("rationale")),
            "why_hungary_origin": "hu_model",
            "primary_reason": c["reason"],
        })
        items[-1]["sources"] = list(dict.fromkeys(items[-1]["sources"]))

    sec = []
    for c in secondary:
        if len(sec) >= MAX_SECONDARY:
            break
        # Secondary watch = globalisan fontos, de alacsony HU-relevancia. A
        # regionalis tetelek a page 2-n jelennek meg, nem itt.
        if c["sig"] < 4 or c["h"].get("level") in ("HIGH", "MEDIUM"):
            continue
        if c["kind"] == "kj":
            src_d = c["best"]
            line = (src_d or {}).get("title") or c["k"].get("judgement")
            ident = c["k"].get("id")
            refs = [ident] + [d["ref"] for d in c["sup"]]
            srcs = [s for d in c["sup"] for s in reg.for_dev(d, "p.1 watch")]
            countries = sorted({x for d in c["sup"]
                                for x in d.get("countries") or []})
        else:
            d = c["d"]
            line, ident = d.get("title"), d["ref"]
            refs, srcs = [d["ref"]], reg.for_dev(d, "p.1 watch")
            countries = d.get("countries") or []
        sec.append({
            "id": ident, "line": _fit("secondary", line),
            "countries": countries, "significance": c["sig"],
            "hu_level": c["h"].get("level"), "confidence": c["conf"],
            "horizon": c["horizon"], "refs": refs,
            "sources": list(dict.fromkeys(srcs)),
        })
    return items, sec


def cee_hotspots(devs, coverage, cfg, countries_by_id):
    cee = cfg["_cee"]
    spots = {}
    for d in devs:
        if not is_material(d):
            continue
        h = d.get("hu_relevance") or {}
        targets = [c for c in d.get("country_ids") or [] if c in cee]
        fids = {f["id"] for f in h.get("factors") or []}
        if not targets and fids & {"eastern_flank_posture",
                                   "airspace_incident", "air_policing"}:
            # Csak szovetseges legterpozicio / incidens: egy etiop Su-35
            # vasarlas nem teszi Oroszorszagot hotspotta.
            named = named_country_ids(" ".join([d.get("title") or "",
                                                d.get("fact") or ""]),
                                      countries_by_id)
            targets = [c for c in named if c in cee][:2]
        for cid in targets:
            s = spots.setdefault(cid, {
                "country_id": cid,
                "name": (countries_by_id.get(cid) or {}).get("name") or cid,
                "level": "MINIMAL", "score": 0, "significance": 0,
                "refs": []})
            if hu.LEVEL_RANK.get(h.get("level"), 4) < \
                    hu.LEVEL_RANK.get(s["level"], 4):
                s["level"] = h.get("level")
            s["score"] = max(s["score"], h.get("score") or 0)
            s["significance"] = max(s["significance"], _sig(d))
            s["refs"].append(d["ref"])
    gaps = [c["country_id"] for c in (coverage or {}).get("priority") or []
            if c.get("status") == "GAP"]
    return {
        "hotspots": sorted(spots.values(),
                           key=lambda s: (hu.LEVEL_RANK.get(s["level"], 4),
                                          -s["score"])),
        "collection_gaps": gaps,
        "home": "hun",
        "caption": "Central and Eastern Europe — material developments "
                   "coloured by Hungary relevance (not air-power "
                   "significance). Dashed outline: collection gap. No hotspot "
                   "does not mean no activity.",
    }


# --------------------------------------------------------------------------
# 4. Page 2 — kozvetlen es kozeli regio + collection requirements
# --------------------------------------------------------------------------

GROUP_ORDER = [("non_nato_priority", "Non-NATO priority"),
               ("neighbours", "Neighbour"),
               ("extended_nato", "Extended regional NATO")]


def page2(devs, countries_by_id, coverage, cfg, used, reg):
    g = cfg.get("brief_groups") or {}
    member = {}
    for key, _ in GROUP_ORDER:
        for cid in g.get(key) or []:
            member.setdefault(cid, key)
    member["hun"] = "home"
    rows = []
    for d in sorted(devs, key=lambda d: hu.rank_key(
            d.get("hu_relevance"), _sig(d), d.get("confidence"),
            d.get("effect_timing"))):
        if not is_material(d) or len(rows) >= MAX_PAGE2_ROWS:
            continue
        h = d.get("hu_relevance") or {}
        cid = next((c for c in d.get("country_ids") or [] if c in member),
                   None)
        group = member.get(cid) if cid else None
        affected = cid
        if group is None:
            fids = {f["id"] for f in h.get("factors") or []}
            if fids & {"eastern_flank_posture", "airspace_incident",
                       "air_policing"} and h.get("level") in ("HIGH",
                                                              "MEDIUM"):
                group = "extended_nato"
                cid = (d.get("country_ids") or [None])[0]
                named = [c for c in named_country_ids(
                    " ".join([d.get("title") or "", d.get("fact") or ""]),
                    countries_by_id) if c in member]
                affected = named[0] if named else None
        if group is None or cid is None:
            continue
        name = (countries_by_id.get(cid) or {}).get("name") or cid
        if affected and affected != cid:
            name = "{} → {}".format(name, (countries_by_id.get(affected)
                                            or {}).get("name"))
        cov = ((coverage or {}).get("countries") or {}).get(
            affected or cid) or {}
        rows.append({
            "ref": d["ref"], "group": group, "country": name,
            "country_id": cid, "affected_country_id": affected,
            "what_changed": _fit("row_what", d.get("fact") or d.get("title")),
            "effect": _fit("row_effect", d.get("capability_delta")),
            "hu_relevance": h.get("level"), "hu_score": h.get("score"),
            "hu_why": _fit("row_hu", h.get("rationale")),
            "significance": _sig(d),
            "significance_label": hu.significance_label(_sig(d)),
            "confidence": d.get("confidence"),
            "horizon": d.get("effect_timing") or "unknown",
            "next_observable": _fit("row_next", (d.get("indicators_to_watch")
                                                 or [None])[0]),
            "coverage": cov.get("status"),
            "sources": reg.for_dev(d, "p.2 " + name.split(" → ")[-1]),
        })
        used.add(d["ref"])

    with_rows = {r.get("affected_country_id") or r["country_id"]
                 for r in rows}
    cov = (coverage or {}).get("countries") or {}
    listed = []
    for key, _ in GROUP_ORDER:
        for cid in g.get(key) or []:
            if cid not in listed:
                listed.append(cid)
    no_change, gaps = [], []
    for cid in listed:
        if cid in with_rows:
            continue
        name = (countries_by_id.get(cid) or {}).get("name") or cid
        st = (cov.get(cid) or {}).get("status")
        if st == "GAP":
            gaps.append(name)
        else:
            no_change.append({"name": name, "coverage": st or "unknown"})

    # REGIONAL COLLECTION REQUIREMENTS: gap -> kerdes -> elvart megfigyeles.
    # A felszabadult helyet ez tolti ki, nem gyenge hirek.
    req_cfg = (_load_json(ROOT / "config" / "collection_requirements.json",
                          {}).get("countries") or {})
    reqs = []
    room = max(3, MAX_REQUIREMENTS - len(rows))
    for st_want in ("GAP", "PARTIAL", "ADEQUATE", None):
        for cid in listed:
            if len(reqs) >= room or cid in with_rows:
                continue
            st = (cov.get(cid) or {}).get("status")
            if st != st_want or cid not in req_cfg:
                continue
            q = req_cfg[cid]
            reqs.append({
                "country": (countries_by_id.get(cid) or {}).get("name")
                or cid,
                "status": st or "unknown",
                "gap": ("No reporting reached the collection in 60 days."
                        if st == "GAP" else
                        "No material change identified this week."),
                "question": sentence(q.get("question")),
                "observable": sentence(q.get("observable")),
            })
    return {
        "rows": rows,
        "no_material_change": no_change,
        "collection_gap": gaps,
        "collection_requirements": reqs,
        "note": ("Geography sets collection priority, not inclusion: a "
                 "country appears in the table only if a material "
                 "development was assessed. 'No material change identified' "
                 "is stated only where collection was at least PARTIAL; "
                 "elsewhere it is a collection gap."),
    }


# --------------------------------------------------------------------------
# 5. Page 3 — kompakt regiok + maturity matrix + change table
# --------------------------------------------------------------------------

def _item(d, reg, page="p.3"):
    h = d.get("hu_relevance") or {}
    return {
        "ref": d["ref"],
        "country": ", ".join(d.get("countries") or []) or "—",
        "domain": DOMAIN_LABELS.get(d.get("capability_domain") or "",
                                    d.get("capability_domain")),
        "what_changed": sentence(d.get("title")),
        "assessment": _fit("item_assessment", d.get("so_what")
                           or d.get("capability_delta")),
        "significance": _sig(d),
        "significance_label": hu.significance_label(_sig(d)),
        "confidence": d.get("confidence"),
        "horizon": d.get("effect_timing") or "unknown",
        "hu_relevance": h.get("level"),
        "sources": reg.for_dev(d, "{} {}".format(
            page, ", ".join(d.get("countries") or []) or d["ref"])),
    }


def _regions(d, countries_by_id):
    return [(countries_by_id.get(c) or {}).get("region")
            for c in d.get("country_ids") or []]


def page3_sections(devs, countries_by_id, coverage, cfg, used, reg):
    g = cfg.get("brief_groups") or {}
    nato = cfg["_nato"]
    regional = (set(g.get("non_nato_priority") or [])
                | set(g.get("neighbours") or [])
                | set(g.get("extended_nato") or []) | {"hun"})
    secs = {"middle_east": [], "africa": [], "wider_nato": []}
    for d in sorted(devs, key=lambda d: (-_sig(d), hu.rank_key(
            d.get("hu_relevance"), _sig(d), d.get("confidence"),
            d.get("effect_timing")))):
        if d["ref"] in used or not is_material(d):
            continue
        ids = d.get("country_ids") or []
        regs = _regions(d, countries_by_id)
        key = None
        if any(c in nato and c not in regional for c in ids) or "eur" in ids:
            key = "wider_nato"
        elif any(r in (g.get("middle_east_regions") or []) for r in regs):
            key = "middle_east"
        elif any(r in (g.get("africa_regions") or []) for r in regs):
            key = "africa"
        if key and len(secs[key]) < MAX_P3_ITEMS:
            secs[key].append(_item(d, reg))
            used.add(d["ref"])
    regs_cov = (coverage or {}).get("regions") or {}

    def cov_of(names):
        sts = [regs_cov.get(n, {}).get("status") for n in names]
        sts = [s for s in sts if s]
        if not sts:
            return None
        if all(s == "GAP" for s in sts):
            return "GAP"
        return "ADEQUATE" if all(s == "ADEQUATE" for s in sts) else "PARTIAL"

    titles = {"middle_east": "Middle East", "africa": "Africa",
              "wider_nato": "Wider NATO"}
    cov_names = {"middle_east": g.get("middle_east_regions") or [],
                 "africa": g.get("africa_regions") or [],
                 "wider_nato": ["Western Europe", "Northern Europe",
                                "North America"]}
    return [{
        "key": k, "title": titles[k], "items": secs[k],
        "coverage": cov_of(cov_names[k]),
        "empty": (None if secs[k] else
                  ("COLLECTION GAP" if cov_of(cov_names[k]) == "GAP"
                   else "NO MATERIAL CHANGE IDENTIFIED")),
    } for k in ("middle_east", "africa", "wider_nato")]


def maturity_matrix(devs):
    """A meglevo eletciklus-erettseg (STAGE -> Intent..Operational) nezete,
    az Operational IOC/FOC-ra bontva. Nincs uj adatmodell."""
    rows = []
    for d in sorted(devs, key=lambda d: hu.rank_key(
            d.get("hu_relevance"), _sig(d), d.get("confidence"),
            d.get("effect_timing"))):
        if not is_material(d) or len(rows) >= MAX_MATURITY:
            continue
        stage = d.get("lifecycle_stage") or "other"
        withdrawal = stage in ("retirement", "loss")
        rows.append({
            "ref": d["ref"],
            "label": d.get("display_label") or d.get("title"),
            "country": ", ".join(d.get("countries") or []) or "—",
            "stage": STAGE_LABELS.get(stage, stage),
            "column": None if withdrawal else STAGE_TO_COLUMN.get(stage,
                                                                  "Intent"),
            "withdrawal": withdrawal,
            "hu_relevance": (d.get("hu_relevance") or {}).get("level"),
            "horizon": d.get("effect_timing") or "unknown",
        })
    return {"columns": MATURITY_COLUMNS, "rows": rows,
            "caption": "Capability maturity of this week's material "
                       "developments: the filled cell is the stage reached "
                       "as evidenced; earlier cells are implied, not "
                       "observed. Losses and retirements are shown as "
                       "withdrawal, outside the introduction chain."}


def change_table(payload, devs, countries_by_id, cfg):
    diff = payload.get("since_last_week") or {}
    by_prog, by_label = {}, {}
    for d in devs:
        if d.get("programme_id"):
            by_prog[d["programme_id"]] = d
        by_label[d.get("display_label") or d.get("title")] = d
    rows = []
    for r in diff.get("programmes") or []:
        d = by_prog.get(r.get("programme_id") or "") or by_label.get(
            r.get("programme"))
        if d:
            h = d.get("hu_relevance") or {}
            country = ", ".join(d.get("countries") or []) or "—"
            cap = d.get("display_label") or d.get("title")
            conf = d.get("confidence")
            ref = d["ref"]
        else:
            pid = r.get("programme_id") or ""
            cid = pid.split("-")[0] if pid else None
            ids = [cid] if cid in countries_by_id else named_country_ids(
                r.get("programme") or "", countries_by_id)[:1]
            h = hu.score_item({"title": r.get("programme")}, ids,
                              countries_by_id, cfg)
            country = ", ".join((countries_by_id.get(c) or {}).get("name")
                                or c for c in ids) or "—"
            cap = r.get("programme")
            conf = (r.get("current") or "").split("·")[-1].strip() or None
            if conf in ("not reported", "—"):
                conf = None
            ref = None
        rows.append({
            "country": country, "capability": cap,
            "previous": r.get("previous"), "current": r.get("current"),
            "delta": r.get("change"), "moved": bool(r.get("moved")),
            "hu_relevance": h.get("level"), "hu_score": h.get("score"),
            "confidence": conf, "ref": ref,
        })
    rows.sort(key=lambda x: (not x["moved"],
                             hu.LEVEL_RANK.get(x["hu_relevance"], 4),
                             -(x["hu_score"] or 0)))
    overflow = max(0, len(rows) - MAX_CHANGE_ROWS)
    rows = rows[:MAX_CHANGE_ROWS]
    for i, x in enumerate(rows):
        x["priority"] = i + 1
    return {"previous_week": diff.get("previous_week"), "rows": rows,
            "overflow": overflow,
            "note": diff.get("note") or "",
            "source": "since_last_week (previous published report)"}


# --------------------------------------------------------------------------
# 6. Page 4 — globalis kep, watch, gapek, OUTLOOK & EXPECTED OBSERVABLES
# --------------------------------------------------------------------------

def page4(payload, devs, countries_by_id, coverage, cfg, used, reg,
          primary, secondary):
    g = cfg.get("brief_groups") or {}
    glob_ids = set(g.get("global_strategic") or [])
    glob_regs = set(g.get("global_regions") or [])
    items = []
    for d in sorted(devs, key=lambda d: (-_sig(d), HORIZON_ORDER.get(
            d.get("effect_timing"), 4))):
        if d["ref"] in used or not is_material(d):
            continue
        ids = set(d.get("country_ids") or [])
        regs = set(_regions(d, countries_by_id))
        if ids & glob_ids or regs & glob_regs or _sig(d) >= 4:
            items.append(_item(d, reg, "p.4"))
            used.add(d["ref"])
        if len(items) >= MAX_GLOBAL_ITEMS:
            break

    watch = []
    for w in payload.get("priority_watch") or []:
        ids = named_country_ids(" ".join([w.get("issue") or "",
                                          w.get("why_it_matters") or ""]),
                                countries_by_id)
        h = hu.score_item(w, ids, countries_by_id, cfg)
        watch.append({
            "question": sentence(w.get("issue")).rstrip("."),
            "why": _fit("watch_why", w.get("why_it_matters")),
            "next_observable": _fit("watch_next", w.get("next_observable")),
            "horizon": w.get("horizon"),
            "impact": w.get("impact_if_confirmed"),
            "hu_relevance": h.get("level"),
            "_k": ({"high": 0, "medium": 1, "low": 2}.get(
                w.get("impact_if_confirmed"), 3),
                hu.LEVEL_RANK.get(h.get("level"), 4)),
        })
    watch.sort(key=lambda x: x["_k"])
    watch = watch[:MAX_WATCH]
    for x in watch:
        x.pop("_k", None)

    gaps = [{"text": _fit("gap", x), "origin": "report"}
            for x in (payload.get("intelligence_gaps") or []) if x]
    cov_gaps = [c["name"] for c in (coverage or {}).get("priority") or []
                if c.get("status") == "GAP"]
    if cov_gaps:
        gaps.append({"text": "No reporting reached the collection on {} in "
                             "{} days, so quiet cannot be told from "
                             "unobserved there.".format(
                                 ", ".join(cov_gaps[:6]),
                                 (coverage or {}).get("days", 60)),
                     "origin": "coverage_audit"})
    gaps = gaps[:MAX_GAPS]

    # OUTLOOK: a fo tetelek kovetkezo, ellenorizheto jele (nem naptar).
    outlook, seen = [], set()
    by_ref = {d["ref"]: d for d in devs}
    order = ([r for x in primary for r in x.get("refs") or []
              if r in by_ref]
             + [r for x in secondary for r in x.get("refs") or []
                if r in by_ref]
             + [d["ref"] for d in sorted(devs, key=lambda d: hu.rank_key(
                 d.get("hu_relevance"), _sig(d), d.get("confidence"),
                 d.get("effect_timing"))) if is_material(d)])
    for ref in order:
        if ref in seen or len(outlook) >= MAX_OUTLOOK:
            continue
        seen.add(ref)
        d = by_ref[ref]
        obs = (d.get("indicators_to_watch") or [None])[0]
        if not obs:
            continue
        outlook.append({
            "subject": d.get("display_label") or d.get("title"),
            "country": ", ".join(d.get("countries") or []) or "—",
            "expected_observable": _fit("outlook", obs),
            "hu_relevance": (d.get("hu_relevance") or {}).get("level"),
            "sources": reg.for_dev(d, "p.4 outlook"),
        })
    return {
        "global": {"items": items,
                   "empty": None if items else "NO MATERIAL CHANGE IDENTIFIED"},
        "priority_watch": watch,
        "intelligence_gaps": gaps,
        "outlook": outlook,
        "outlook_note": ("Expected observables for the next 7–30 days: what "
                         "would confirm, move or disprove this week's "
                         "assessments. An intelligence outlook, not an event "
                         "calendar."),
    }


def global_hotspots(devs, countries_by_id):
    spots = {}
    for d in devs:
        if not is_material(d):
            continue
        for cid in d.get("country_ids") or []:
            if cid == "eur":
                continue
            s = spots.setdefault(cid, {
                "country_id": cid,
                "name": (countries_by_id.get(cid) or {}).get("name") or cid,
                "significance": 0, "refs": []})
            s["significance"] = max(s["significance"], _sig(d))
            s["refs"].append(d["ref"])
    return {"hotspots": sorted(spots.values(),
                               key=lambda s: -s["significance"]),
            "caption": "Global hotspots coloured by air-power significance "
                       "(1–5) — not by Hungary relevance. An unmarked country "
                       "is not necessarily quiet."}


# --------------------------------------------------------------------------
# 7. Bottom line — determinisztikus (mindig elkeszul)
# --------------------------------------------------------------------------

def deterministic_bottom_line(primary, secondary, p2, payload, devs):
    sents = []
    material = [d for d in devs if is_material(d)]
    lv = [(d.get("hu_relevance") or {}).get("level") for d in material]
    n_high, n_med = lv.count("HIGH"), lv.count("MEDIUM")
    if not material:
        sents.append({"text": "No material change in the air picture "
                              "relevant to Hungary was identified this week.",
                      "items": []})
    elif n_high or n_med:
        parts = []
        if n_high:
            parts.append("{} of HIGH".format(n_high))
        if n_med:
            parts.append("{} of MEDIUM".format(n_med))
        sents.append({"text": "Of {} material air-power developments this "
                              "week, {} relevance to Hungary.".format(
                                  len(material), " and ".join(parts)),
                      "items": []})
    else:
        sents.append({"text": "None of the {} material air-power developments "
                              "this week is of HIGH or MEDIUM relevance to "
                              "Hungary.".format(len(material)), "items": []})
    for k in primary:
        head = k.get("headline") or k.get("statement")
        hz = k.get("horizon")
        text = "{} ({} confidence, {}).".format(
            sentence(head).rstrip("."), k.get("confidence") or "unstated",
            "effect horizon not established" if hz in (None, "", "unknown")
            else "effect " + hz)
        sents.append({"text": text, "items": [k["id"]]})
    if secondary:
        labels = [s["line"].rstrip(".") for s in secondary[:2]]
        sents.append({"text": "Outside the region, the most significant "
                              "change{} {} — globally important, but of low "
                              "direct relevance to Hungary.".format(
                                  "s were" if len(labels) > 1 else " was",
                                  "; ".join(labels)),
                      "items": [s["id"] for s in secondary[:2]]})
    changed = sorted({r["country"].split(" → ")[-1]
                      for r in p2.get("rows") or []})
    quiet = [x["name"] for x in p2.get("no_material_change") or []]
    if changed:
        sents.append({"text": "In Hungary's immediate and near region, "
                              "material change was assessed for {}{}.".format(
                                  ", ".join(changed[:6]),
                                  "; no material change was identified for "
                                  "{}".format(", ".join(quiet[:6]))
                                  if quiet else ""),
                      "items": [r["ref"] for r in p2["rows"]][:6]})
    elif quiet:
        sents.append({"text": "No material change was identified in "
                              "Hungary's immediate region ({}).".format(
                                  ", ".join(quiet[:6])), "items": []})
    if p2.get("collection_gap"):
        sents.append({"text": "Collection gaps remain for {}; absence of "
                              "reporting there is not evidence of "
                              "inactivity.".format(
                                  ", ".join(p2["collection_gap"][:5])),
                      "items": []})
    return sents[:7]


# --------------------------------------------------------------------------
# 8. Executive synthesis + vezetoi szerkeszto — validalt modellhivas
# --------------------------------------------------------------------------

SYNTHESIS_PROMPT = """You write the executive layer of a COMMAND AIR
INTELLIGENCE BRIEF for a senior Hungarian Defence Forces (MH) commander.

You receive ONLY material that already passed analytical QA: primary items
(KJ-xx / XS-xx), secondary watch items and developments (D-xx), each with its
Hungary-relevance factors, plus a list of over-long executive fields.

Return STRICT JSON only:
{
 "bottom_line": [{"text": "<one sentence>", "refs": ["KJ-01"]}],
 "why_hungary": {"<item id>": "<one or two sentences>"},
 "condensed": {"<field key>": "<shorter complete sentence(s)>"}
}

RULES:
- bottom_line: 5 to 7 complete sentences. Lead with what matters MOST TO
  HUNGARY / MH / NATO's Central-Eastern European air posture. Logic: what
  changed -> why it matters -> what it means for Hungary -> what to watch.
- EVERY sentence cites at least one ref from the input.
- NO NEW FACTS: only figures, dates, names and countries from the cited items.
- CONFIDENCE DICTATES THE VERB: low -> "first indication that"; moderate ->
  "indicates/suggests"; high -> "we assess".
- FACT is not ASSESSMENT; procurement is not operational capability;
  delivery is not IOC.
- No trend words (accelerating, surge, pivot), no superlatives.
- why_hungary: concrete relevance (airspace, QRA/air policing, regional
  balance, NATO posture, MH capability planning, interoperability), based on
  the listed hu_factors only.
- condensed: rewrite each listed field within its char budget as COMPLETE
  sentences. Keep every hedge and negation (may, not, unconfirmed, cannot).
  Never cut a sentence; never end with an ellipsis."""


def _numbers(text):
    return set(re.findall(r"\d+(?:[.,]\d+)?", text or ""))


def _item_text(x):
    keys = ("statement", "what_changed", "assessment", "why_hungary",
            "next_observable", "title", "fact", "capability_delta", "so_what",
            "judgement", "basis", "line", "headline")
    return " ".join(str(x.get(k) or "") for k in keys)


_HEDGE_RX = re.compile(r"\b(not|no|cannot|unconfirmed|unclear|may|might|"
                       r"could|unknown|undisclosed|unverified)\b", re.I)


def validate_sentence(text, refs, ref_text, ref_countries, countries_by_id,
                      withheld_kw):
    import ac_intel  # lusta import
    if not refs or any(r not in ref_text for r in refs):
        return False, "uncited or unknown ref"
    if "…" in text or "..." in text:
        return False, "ellipsis"
    src = " ".join(ref_text[r] for r in refs)
    extra = _numbers(text) - _numbers(src)
    if extra:
        return False, "number not in cited items: {}".format(
            ", ".join(sorted(extra)))
    allowed = {"hun"}
    for r in refs:
        allowed |= set(ref_countries.get(r) or [])
    named = set(named_country_ids(text, countries_by_id))
    if named - allowed:
        return False, "country not in cited items: {}".format(
            ", ".join(sorted(named - allowed)))
    for rx in (ac_intel.TREND_RX, ac_intel.CAPABILITY_OVERREACH_RX,
               ac_intel.SUPERL_RX):
        if ac_intel._flag(rx, text):
            return False, "QA language rule"
    toks = ac_intel._kw(text)
    for kw in withheld_kw:
        if kw and len(toks & kw) >= 4:
            return False, "echoes a withheld judgement"
    return True, None


def _over_budget(brief):
    """Vezetoi mezok, amelyek egesz mondatkent is a keret folott vannak."""
    out = {}
    for k in brief["page1"]["primary"]:
        for f, key in (("statement", "statement"),
                       ("what_changed", "what_changed"),
                       ("assessment", "assessment"),
                       ("why_hungary", "why_hu"),
                       ("next_observable", "next_observable"),
                       ("alternative_explanation", "alternative")):
            lim = BUDGET[key][0]
            if len(k.get(f) or "") > lim:
                out["{}|{}".format(k["id"], f)] = {"text": k[f], "max": lim}
    for r in brief["page2"]["rows"]:
        for f, key in (("what_changed", "row_what"), ("effect", "row_effect")):
            lim = BUDGET[key][0]
            if len(r.get(f) or "") > lim:
                out["{}|{}".format(r["ref"], f)] = {"text": r[f], "max": lim}
    return out


def synthesize(client, brief, payload, devs, countries_by_id):
    if client is None:
        return None
    import ac_intel  # noqa: E402
    dev_by_ref = {d["ref"]: d for d in devs}
    ref_text, ref_countries = {}, {}
    for x in brief["page1"]["primary"] + brief["page1"]["secondary_watch"]:
        ref_text[x["id"]] = _item_text(x) + " " + " ".join(
            _item_text(dev_by_ref[r]) for r in x.get("refs") or []
            if r in dev_by_ref)
        ids = set()
        for r in x.get("refs") or []:
            ids |= set((dev_by_ref.get(r) or {}).get("country_ids") or [])
        ref_countries[x["id"]] = sorted(ids)
    for d in devs:
        if is_material(d):
            ref_text[d["ref"]] = _item_text(d)
            ref_countries[d["ref"]] = list(d.get("country_ids") or [])
    withheld_kw = [ac_intel._kw(j.get("judgement") or "")
                   for j in payload.get("judgements_requiring_review") or []]
    over = _over_budget(brief)
    req = {
        "primary": [{"id": x["id"], "origin": x["origin"],
                     "statement": x["statement"],
                     "what_changed": x["what_changed"],
                     "assessment": x["assessment"],
                     "confidence": x["confidence"], "horizon": x["horizon"],
                     "significance": x["significance"],
                     "hu_level": x["hu_relevance"]["level"],
                     "hu_factors": [f["label"] for f in
                                    x["hu_relevance"]["factors"]]}
                    for x in brief["page1"]["primary"]],
        "secondary_watch": [{"id": s["id"], "line": s["line"],
                             "significance": s["significance"],
                             "hu_level": s["hu_level"]}
                            for s in brief["page1"]["secondary_watch"]],
        "developments": [{"ref": d["ref"], "title": d.get("title"),
                          "capability_delta": d.get("capability_delta"),
                          "so_what": d.get("so_what"),
                          "countries": d.get("countries"),
                          "significance": _sig(d),
                          "confidence": d.get("confidence"),
                          "effect_timing": d.get("effect_timing"),
                          "hu_level": (d.get("hu_relevance") or {}).get(
                              "level")}
                         for d in devs if is_material(d)][:14],
        "regional_no_change": [x["name"] for x in
                               brief["page2"]["no_material_change"]],
        "collection_gaps": brief["page2"]["collection_gap"],
        "over_budget_fields": over,
    }
    try:
        out = ac_intel._call(client, SYNTHESIS_PROMPT, req, 4000)
    except Exception as exc:  # noqa: BLE001
        print("  [warn] executive synthesis unavailable: {}".format(
            str(exc)[:120]))
        return None
    if not isinstance(out, dict):
        return None
    kept, dropped = [], []
    for s in out.get("bottom_line") or []:
        if not isinstance(s, dict):
            continue
        text = sentence(s.get("text"))
        refs = [r for r in (s.get("refs") or []) if isinstance(r, str)]
        ok, why = validate_sentence(text, refs, ref_text, ref_countries,
                                    countries_by_id, withheld_kw)
        if ok:
            kept.append({"text": text, "items": refs})
        else:
            dropped.append({"text": text, "items": refs, "reason": why})
    why_hu = {}
    for rid, text in (out.get("why_hungary") or {}).items():
        if rid not in ref_text or not isinstance(text, str):
            continue
        text = fit(text, BUDGET["why_hu"][0] + 40, 2)
        ok, _ = validate_sentence(text, [rid], ref_text, ref_countries,
                                  countries_by_id, withheld_kw)
        if ok:
            why_hu[rid] = text
    condensed = {}
    for key, text in (out.get("condensed") or {}).items():
        if key not in over or not isinstance(text, str):
            continue
        orig = over[key]["text"]
        text = sentence(text)
        item_id = key.split("|")[0]
        ok = (len(text) < len(orig) and len(text) <= over[key]["max"] * 1.1
              and "…" not in text and "..." not in text
              and _numbers(text) <= _numbers(orig)
              and set(named_country_ids(text, countries_by_id))
              <= set(named_country_ids(orig, countries_by_id))
              and (bool(_HEDGE_RX.search(text))
                   or not _HEDGE_RX.search(orig)))
        if ok and (item_id in ref_text or item_id in dev_by_ref):
            condensed[key] = text
    return {"bottom_line": kept[:7], "dropped": dropped,
            "why_hungary": why_hu, "condensed": condensed}


# --------------------------------------------------------------------------
# 9. Osszeallitas
# --------------------------------------------------------------------------

def build_command_brief(payload, countries_by_id, coverage=None, cfg=None,
                        client=None, events_by_id=None, window=None,
                        articles_by_id=None, sources_by_id=None):
    """A brief kanonikus adatmodellje. A web, a PDF es a Word ebbol
    renderel. A payload developments-et annotalja (ref, orszag,
    HU-relevancia); a brief az EREDETI forrasokra (S-xx) hivatkozik."""
    cfg = cfg or hu.load_config()
    devs = annotate_developments(payload, countries_by_id, events_by_id, cfg)
    reg = SourceRegister(payload, events_by_id, articles_by_id,
                         sources_by_id, countries_by_id)
    used = set()
    primary, secondary = page1(payload, devs, countries_by_id, cfg, reg)
    for x in primary:
        used |= {r for r in x.get("refs") or [] if r.startswith("D-")}
    p2 = page2(devs, countries_by_id, coverage, cfg, used, reg)
    sections = page3_sections(devs, countries_by_id, coverage, cfg, used, reg)
    p4 = page4(payload, devs, countries_by_id, coverage, cfg, used, reg,
               primary, secondary)
    meta = payload.get("report_meta") or {}
    rest = meta.get("restatement")
    brief = {
        "schema": BRIEF_SCHEMA,
        "week_label": payload.get("week_label") or meta.get("week_label"),
        "title": "Command Air Intelligence Brief",
        "classification": "UNCLASSIFIED // OSINT",
        "status_line": STATUS_LINE,
        "meta": {
            "week_label": payload.get("week_label") or meta.get("week_label"),
            "period_start": meta.get("period_start"),
            "period_end": meta.get("period_end"),
            "timezone": meta.get("timezone") or "Europe/Budapest",
            "window_label": meta.get("window_label") or "{} → {}".format(
                meta.get("period_start"), meta.get("period_end")),
            "generated_utc": meta.get("generated_utc"),
            "methodology_version": meta.get("methodology_version"),
            "hu_model_version": cfg.get("version"),
            "brief_version": "v2",
            "report_status": meta.get("status"),
            "revision": ({"number": rest.get("number") or 1,
                          "reason": rest.get("reason"),
                          "restated_utc": rest.get("restated_utc")}
                         if rest else None),
        },
        "micro_legend": MICRO_LEGEND,
        "page1": {
            "bottom_line": None,
            "primary": primary,
            "primary_empty": (None if primary else
                              "No development of HIGH or MEDIUM relevance to "
                              "Hungary was assessed this week."),
            "secondary_watch": secondary,
            "map_cee": cee_hotspots(devs, coverage, cfg, countries_by_id),
        },
        "page2": p2,
        "page3": {"sections": sections,
                  "maturity": maturity_matrix(devs),
                  "change_table": change_table(payload, devs,
                                               countries_by_id, cfg)},
        "page4": dict(p4, map_global=global_hotspots(devs, countries_by_id)),
        "page5": None,
        "coverage_summary": {
            "priority": [{"name": c["name"], "status": c["status"],
                          "events_window": c["events_window"],
                          "official_source": c["official_source"]}
                         for c in (coverage or {}).get("priority") or []],
            "summary": (coverage or {}).get("summary"),
            "note": (coverage or {}).get("note"),
        },
    }

    det = deterministic_bottom_line(primary, secondary, p2, payload, devs)
    syn = synthesize(client, brief, payload, devs, countries_by_id)
    if syn and len(syn["bottom_line"]) >= 3:
        bl = {"origin": "executive_synthesis", "sentences": syn["bottom_line"],
              "dropped_by_validation": syn["dropped"],
              "note": "Executive synthesis — every sentence cites its source "
                      "items; numbers and countries are checked against "
                      "them."}
    else:
        bl = {"origin": "deterministic", "sentences": det,
              "dropped_by_validation": (syn or {}).get("dropped") or [],
              "note": "Assembled deterministically from the QA-passed "
                      "judgements, developments and coverage audit."}
    if syn:
        for x in primary:
            t = syn["why_hungary"].get(x["id"])
            if t:
                x["why_hungary"], x["why_hungary_origin"] = (
                    t, "executive_synthesis")
        for key, text in syn["condensed"].items():
            ident, field = key.split("|", 1)
            for x in primary:
                if x["id"] == ident and field in x:
                    x[field] = text
                    x.setdefault("edited_fields", []).append(field)
            for r in p2["rows"]:
                if r["ref"] == ident and field in r:
                    r[field] = text
                    r.setdefault("edited_fields", []).append(field)
    # A bottom line forrasai = a hivatkozott tetelek forrasai.
    src_of = {x["id"]: x.get("sources") or [] for x in primary + secondary}
    for r in p2["rows"]:
        src_of[r["ref"]] = r.get("sources") or []
    for s in bl["sentences"]:
        s["sources"] = list(dict.fromkeys(
            x for i in s.get("items") or [] for x in src_of.get(i, [])))
    brief["page1"]["bottom_line"] = bl

    brief["page5"] = {
        "sources": reg.entries,
        "source_note": ("Each S-xx links to the original publication; the "
                        "title is shown in its original language. Lineage "
                        "groups publications that restate one evidence "
                        "chain — several articles on one lineage are one "
                        "piece of evidence. State-controlled sources are "
                        "attributed statements, not independent "
                        "confirmation."),
        "legend": LEGEND,
        "principles": PRINCIPLES,
    }

    # --- traceability ---
    valid_items = ({d["ref"] for d in devs}
                   | {k.get("id") for k in payload.get("key_judgements")
                      or []}
                   | {x["id"] for x in primary})
    valid_sources = {e["id"] for e in reg.entries}
    used_items, used_sources = set(), set()
    for x in primary + secondary:
        used_items |= set(x.get("refs") or [])
        used_sources |= set(x.get("sources") or [])
    for r in p2["rows"]:
        used_items.add(r["ref"])
        used_sources |= set(r["sources"])
    for s in sections:
        for i in s["items"]:
            used_items.add(i["ref"])
            used_sources |= set(i["sources"])
    for i in p4["global"]["items"]:
        used_items.add(i["ref"])
        used_sources |= set(i["sources"])
    for o in p4["outlook"]:
        used_sources |= set(o["sources"])
    for s in bl["sentences"]:
        used_items |= set(s.get("items") or [])
        used_sources |= set(s.get("sources") or [])
    exec_items = ([("primary", x) for x in primary]
                  + [("row", r) for r in p2["rows"]]
                  + [("item", i) for s in sections for i in s["items"]]
                  + [("item", i) for i in p4["global"]["items"]])
    brief["traceability"] = {
        "analyst_refs_used": sorted(r for r in used_items if r),
        "unresolved_refs": sorted(r for r in used_items
                                  if r and r not in valid_items),
        "sources_used": sorted(used_sources),
        "unresolved_sources": sorted(used_sources - valid_sources),
        "items_without_source": [x.get("id") or x.get("ref")
                                 for kind, x in exec_items
                                 if not x.get("sources")],
        "executive_synthesis_items": [x["id"] for x in primary
                                      if x["origin"] == "executive_synthesis"],
        "withheld_judgements_excluded": [
            j.get("id") for j in payload.get("judgements_requiring_review")
            or []],
        "note": ("The brief stands alone: each executive item cites its "
                 "original sources (S-xx, page 5). Analyst references "
                 "(D-xx, KJ-xx) link it to the detailed weekly report for "
                 "audit. XS-xx items are executive synthesis traced to the "
                 "listed D-xx."),
    }
    return brief
