# -*- coding: utf-8 -*-
"""COMMAND AIR INTELLIGENCE BRIEF — 4 oldal egy magyar katonai vezetonek.

NEM uj pipeline es NEM masodik igazsag. A brief kizarolag a heti jelentes MAR
ELKESZULT, QA-n atment payloadjabol epul (developments, key_judgements,
priority_watch, intelligence_gaps, since_last_week, stats), plusz ket
determinisztikus reteg:

  * HUNGARY RELEVANCE (ac_hungary) — kulon dimenzio a significance mellett;
  * COVERAGE (coverage_audit) — "nincs valtozas" vs "nem latunk oda".

Logika minden tetelnel:
  INFORMATION -> CHANGE -> SIGNIFICANCE -> ASSESSMENT -> HU/NATO RELEVANCE
  -> OUTLOOK.

Az egyetlen uj, magasabb szintu szoveg az EXECUTIVE SYNTHESIS: a HU bottom
line es a tetelenkenti "why Hungary should care" mondat. Ez:
  * kifejezetten jelolt (origin = "executive_synthesis");
  * minden mondata hivatkozik (D-xx / KJ-xx), es a hivatkozas ellenorzott;
  * nem vihet be uj szamot vagy uj orszagot a hivatkozott tetelekhez kepest;
  * nem hozhat vissza visszatartott (QA-n elbukott) iteletet;
  * ha a validacio nem eleg mondatot hagy meg, DETERMINISZTIKUS fallback
    lep be — a brief modell nelkul is teljes.

Minden tetel visszamutat a reszletes jelentesre: web-en horgony (#D-03,
#KJ-01), PDF-ben determinisztikus hivatkozas ("Detailed assessment -> D-03").
"""
import re

import ac_hungary as hu

BRIEF_SCHEMA = "command_brief_v1"

HORIZON_ORDER = {"immediate": 0, "<12 months": 1, "1-3 years": 2,
                 ">3 years": 3, "unknown": 4}
PRE_CONTRACT = {"requirement", "rfi_sources_sought", "rfp", "bid", "selection",
                "national_approval", "export_approval"}

# Szovegkeretek: a 4 oldal fix. Ha valami nem fer bele, az a reszletes
# jelentesben van — a brief nem no oldalszamban.
CAPS = {
    "statement": 230, "what_changed": 260, "assessment": 320,
    "why_hu": 230, "next_observable": 150, "alternative": 190,
    "row_what": 200, "row_effect": 190, "row_next": 120,
    "item_assessment": 230, "bottom_line_sentence": 300,
    "watch": 150, "gap": 210,
}
MAX_KJ = 5
MAX_SYNTHESIS = 3   # legfeljebb ennyi uj (XS) itelet a page 1-en
MAX_PAGE2_ROWS = 8
MAX_P3_ITEMS = 4
MAX_GLOBAL_ITEMS = 4
MAX_WATCH = 5
MAX_GAPS = 5
MAX_CHANGE_ROWS = 8


# --------------------------------------------------------------------------
# Segedfuggvenyek
# --------------------------------------------------------------------------

def clip(text, limit, max_sentences=None):
    """Mondathataron vag; ha egy mondat is tul hosszu, szohataron + '…'."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return ""
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", s)
    if max_sentences:
        sents = sents[:max_sentences]
    out = ""
    for x in sents:
        cand = (out + " " + x).strip()
        if len(cand) <= limit:
            out = cand
        else:
            break
    if out:
        return out
    first = sents[0]
    if len(first) <= limit:
        return first
    cut = first[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


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


def detail_ref(refs):
    """Determinisztikus PDF-kereszthivatkozas a reszletes jelentesre."""
    refs = [r for r in refs if r]
    if not refs:
        return None
    return "Detailed assessment → " + ", ".join(refs)


# --------------------------------------------------------------------------
# 1. A fejlemenyek annotalasa (ref, orszag, HU-relevancia) — a REPORT-ba is
# --------------------------------------------------------------------------

def annotate_developments(payload, countries_by_id, events_by_id=None,
                          cfg=None):
    """Minden developmenthez: ref (D-01..), country_ids, hu_relevance.

    A payload developments-et HELYBEN egesziti ki, hogy a reszletes jelentes
    ugyanazt a HU-relevanciat es ugyanazt a hivatkozasi kulcsot mutassa, mint
    a brief. Regebbi payloadnal (nincs country_ids) az annex-esemenyekbol,
    vegso esetben a cimben nevezett orszagbol szarmaztat.
    """
    cfg = cfg or hu.load_config()
    name_to_id = {}
    for cid, c in countries_by_id.items():
        if c.get("name"):
            name_to_id[c["name"]] = cid
    annex = {a.get("event_id"): a for a in (payload.get("annex_events") or [])}
    for i, d in enumerate(payload.get("developments") or []):
        d["ref"] = d.get("ref") or _ref(i)
        ids = list(d.get("country_ids") or [])
        if not ids:
            for eid in d.get("event_ids") or []:
                e = (events_by_id or {}).get(eid)
                cid = (e or {}).get("country_id")
                if not cid:
                    a = annex.get(eid) or {}
                    cid = name_to_id.get(a.get("country") or "")
                if cid and cid not in ids:
                    ids.append(cid)
        if not ids:
            ids = named_country_ids(d.get("title") or "", countries_by_id)[:1]
        d["country_ids"] = ids
        d["countries"] = [(countries_by_id.get(c) or {}).get("name") or c
                          for c in ids]
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
    """A visszatartott (QA-n elbukott) iteletek esemenyei: ezekbol a brief
    NEM epithet uj, magasabb szintu iteletet."""
    out = set()
    for j in payload.get("judgements_requiring_review") or []:
        out |= set(j.get("supporting_event_ids") or [])
    return out


def _system_alternative(d):
    """'What would make this wrong' — a bizonyitek ALLAPOTABOL, nem a
    modelltol. Jelolt: alternative_origin = system_evidence_state."""
    stage = d.get("lifecycle_stage")
    if (d.get("independent_lineages") or 1) <= 1:
        return ("All supporting reporting traces to a single evidence chain; "
                "the claim may not survive independent confirmation.")
    if stage in PRE_CONTRACT:
        return ("The reporting describes a plan or authorisation, not a "
                "contract; the programme may stall before signature.")
    if d.get("novelty") in ("continuation", "confirmation_of_known"):
        return ("This may restate an already-known programme rather than "
                "mark a new decision.")
    if stage in ("contract_signed", "production"):
        return ("A signed contract can still slip or be re-scoped; first "
                "delivery and IOC dates are the test.")
    if stage in ("delivery", "ioc", "foc"):
        return ("Delivery is not operational capability: crews, weapons and "
                "sustainment decide when the effect is real.")
    if stage == "loss":
        return ("The cause is not established; the loss may be an accident "
                "rather than adversary action.")
    return ("The activity may be routine rather than a change in posture; "
            "its duration or repetition is the test.")


def _hu_view(h):
    return {"level": h.get("level"), "score": h.get("score"),
            "factors": [{"label": f["label"], "points": f["points"]}
                        for f in h.get("factors") or []],
            "rationale": h.get("rationale")}


# --------------------------------------------------------------------------
# 2. Page 1 — Key judgements (HU rangsor) + CEE terkep hotspotjai
# --------------------------------------------------------------------------

def page1_judgements(payload, devs, countries_by_id, cfg):
    kjs = payload.get("key_judgements") or []
    barred = _barred_event_ids(payload)
    by_event = {}
    for d in devs:
        for eid in d.get("event_ids") or []:
            by_event.setdefault(eid, []).append(d)

    items, covered = [], set()
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
            what = best.get("capability_delta") or best.get("fact")
            nxt = (k.get("indicators") or best.get("indicators_to_watch")
                   or [None])[0]
        else:
            best = None
            ids = named_country_ids(
                " ".join([k.get("judgement") or "", k.get("basis") or ""]),
                countries_by_id)
            h = hu.score_item(k, ids, countries_by_id, cfg)
            sig = 3
            what = k.get("basis")
            nxt = (k.get("indicators") or [None])[0]
        covered |= {d["ref"] for d in sup}
        alt = k.get("alternative_explanation")
        items.append({
            "id": k.get("id"),
            "origin": "report_key_judgement",
            "statement": clip(k.get("judgement"), CAPS["statement"]),
            "hu_relevance": _hu_view(h),
            "significance": sig,
            "significance_label": hu.significance_label(sig),
            "confidence": k.get("confidence"),
            "horizon": k.get("effect_timing") or (best or {}).get(
                "effect_timing") or "unknown",
            "what_changed": clip(what, CAPS["what_changed"], 2),
            "assessment": clip(k.get("assessment"), CAPS["assessment"], 3),
            "why_hungary": clip(h.get("rationale"), CAPS["why_hu"], 2),
            "why_hungary_origin": "hu_model",
            "next_observable": clip(nxt, CAPS["next_observable"], 1),
            "alternative_explanation": clip(
                alt or (_system_alternative(best) if best else None),
                CAPS["alternative"], 2),
            "alternative_origin": "report" if alt else "system_evidence_state",
            "refs": [k.get("id")] + [d["ref"] for d in sup],
            "headline": (best or {}).get("title"),
            "detail_ref": detail_ref([k.get("id")] + [d["ref"] for d in sup]),
            "countries": sorted({c for d in sup for c in d.get("countries")
                                 or []}),
            "_rank": hu.rank_key(h, sig, k.get("confidence"),
                                 k.get("effect_timing")),
        })

    # EXECUTIVE SYNTHESIS: HIGH/MEDIUM HU-relevanciaju, anyagi fejlemeny, amelyet
    # egyetlen riport-itelet sem fed le. Uj itelet — ezert jelolt, es csak
    # QA-n atment, NEM visszatartott alapanyagbol keszulhet.
    n = 0
    for d in devs:
        h = d.get("hu_relevance") or {}
        if d["ref"] in covered or h.get("level") not in ("HIGH", "MEDIUM") \
                or not is_material(d) or n >= MAX_SYNTHESIS:
            continue
        if set(d.get("event_ids") or []) & barred:
            continue
        n += 1
        items.append({
            "id": "XS-{:02d}".format(n),
            "origin": "executive_synthesis",
            "statement": clip(d.get("title"), CAPS["statement"]),
            "hu_relevance": _hu_view(h),
            "significance": _sig(d),
            "significance_label": hu.significance_label(_sig(d)),
            "confidence": d.get("confidence"),
            "horizon": d.get("effect_timing") or "unknown",
            "what_changed": clip(d.get("capability_delta") or d.get("fact"),
                                 CAPS["what_changed"], 2),
            "assessment": clip(d.get("so_what"), CAPS["assessment"], 3),
            "why_hungary": clip(h.get("rationale"), CAPS["why_hu"], 2),
            "why_hungary_origin": "hu_model",
            "next_observable": clip((d.get("indicators_to_watch") or [None])[0],
                                    CAPS["next_observable"], 1),
            "alternative_explanation": clip(_system_alternative(d),
                                            CAPS["alternative"], 2),
            "alternative_origin": "system_evidence_state",
            "refs": [d["ref"]],
            "detail_ref": detail_ref([d["ref"]]),
            "countries": d.get("countries") or [],
            "traces_to": [d["ref"]],
            "_rank": hu.rank_key(h, _sig(d), d.get("confidence"),
                                 d.get("effect_timing")),
        })

    items.sort(key=lambda x: x["_rank"])
    items = items[:MAX_KJ]
    n = 0
    for x in items:
        x.pop("_rank", None)
        if x["origin"] == "executive_synthesis":
            n += 1
            x["id"] = "XS-{:02d}".format(n)
    return items


def cee_hotspots(devs, coverage, cfg, countries_by_id):
    cee = hu.load_config()["_cee"] if cfg is None else cfg["_cee"]
    spots = {}
    for d in devs:
        if not is_material(d):
            continue
        h = d.get("hu_relevance") or {}
        targets = [c for c in d.get("country_ids") or [] if c in cee]
        # A szereplon kivul az erintett CEE-orszag is hotspot lehet
        # (pl. amerikai telepites Romaniaba): a HU-tenyezo nevezi meg.
        fids = {f["id"] for f in h.get("factors") or []}
        if not targets and fids & {"eastern_flank_posture",
                                   "airspace_incident", "air_policing"}:
            # Csak szovetseges legterpozicio / incidens eseten: egy ethiop
            # Su-35 vasarlas nem teszi Oroszorszagot hotspotta.
            named = named_country_ids(
                " ".join([d.get("title") or "", d.get("fact") or ""]),
                countries_by_id)
            targets = [c for c in named if c in cee][:2]
        for cid in targets:
            s = spots.setdefault(cid, {
                "country_id": cid,
                "name": (countries_by_id.get(cid) or {}).get("name") or cid,
                "level": "MINIMAL", "score": 0, "significance": 0,
                "refs": [], "labels": []})
            if hu.LEVEL_RANK.get(h.get("level"), 4) < \
                    hu.LEVEL_RANK.get(s["level"], 4):
                s["level"] = h.get("level")
            s["score"] = max(s["score"], h.get("score") or 0)
            s["significance"] = max(s["significance"], _sig(d))
            s["refs"].append(d["ref"])
            lab = d.get("display_label") or d.get("title")
            if lab and len(s["labels"]) < 2:
                s["labels"].append(clip(lab, 40))
    gaps = [c["country_id"] for c in (coverage or {}).get("priority") or []
            if c.get("status") == "GAP"]
    return {
        "hotspots": sorted(spots.values(),
                           key=lambda s: (hu.LEVEL_RANK.get(s["level"], 4),
                                          -s["score"])),
        "collection_gaps": gaps,
        "home": "hun",
        "legend": "Colour = Hungary relevance of the material development "
                  "(not air-power significance). Dashed outline = collection "
                  "gap. Hotspots only — no hotspot means no material change "
                  "identified, not no activity.",
    }


# --------------------------------------------------------------------------
# 3. Page 2 — kozvetlen es kozeli regio
# --------------------------------------------------------------------------

def _row(d, cid, countries_by_id, coverage):
    h = d.get("hu_relevance") or {}
    cov = ((coverage or {}).get("countries") or {}).get(cid) or {}
    return {
        "country_id": cid,
        "country": (countries_by_id.get(cid) or {}).get("name") or cid,
        "what_changed": clip(d.get("fact") or d.get("title"),
                             CAPS["row_what"], 2),
        "effect": clip(d.get("capability_delta"), CAPS["row_effect"], 2),
        "hu_relevance": h.get("level"),
        "hu_score": h.get("score"),
        "hu_why": clip(h.get("rationale"), 160, 1),
        "significance": _sig(d),
        "significance_label": hu.significance_label(_sig(d)),
        "confidence": d.get("confidence"),
        "horizon": d.get("effect_timing") or "unknown",
        "next_observable": clip((d.get("indicators_to_watch") or [None])[0],
                                CAPS["row_next"], 1),
        "coverage": cov.get("status"),
        "ref": d["ref"],
        "detail_ref": detail_ref([d["ref"]]),
        "label": d.get("display_label") or d.get("title"),
    }


def page2(devs, countries_by_id, coverage, cfg, used):
    g = cfg.get("brief_groups") or {}
    order = [("non_nato_priority", "Non-NATO priority"),
             ("neighbours", "Neighbours"),
             ("extended_nato", "Extended NATO / Allied posture in CEE")]
    member = {}
    for key, _ in order:
        for cid in g.get(key) or []:
            member.setdefault(cid, key)
    member["hun"] = "home"
    rows = []
    for d in sorted(devs, key=lambda d: hu.rank_key(
            d.get("hu_relevance"), _sig(d), d.get("confidence"),
            d.get("effect_timing"))):
        if not is_material(d):
            continue
        h = d.get("hu_relevance") or {}
        cid = next((c for c in d.get("country_ids") or [] if c in member),
                   None)
        group = member.get(cid) if cid else None
        if group is None:
            # Allied posture in CEE: a szereplo nem CEE, de a tenyezok
            # szerint a keleti szarny legterpoziciojat erinti.
            fids = {f["id"] for f in h.get("factors") or []}
            if fids & {"eastern_flank_posture", "airspace_incident",
                       "air_policing"} and h.get("level") in ("HIGH",
                                                              "MEDIUM"):
                group = "extended_nato"
                cid = (d.get("country_ids") or [None])[0]
        if group is None or cid is None:
            continue
        r = _row(d, cid, countries_by_id, coverage)
        r["group"] = group
        # A regios orszag, amelyet a tetel erint: a szereplo maga, vagy
        # (Allied posture eseten) a forrasban nevezett CEE-orszag.
        if cid in member:
            r["affected_country_id"] = cid
        else:
            named = [c for c in named_country_ids(
                " ".join([d.get("title") or "", d.get("fact") or ""]),
                countries_by_id) if c in member]
            r["affected_country_id"] = named[0] if named else None
            if named:
                r["country"] = "{} → {}".format(
                    r["country"],
                    (countries_by_id.get(named[0]) or {}).get("name"))
        r["affected_country"] = (countries_by_id.get(
            r.get("affected_country_id") or "") or {}).get("name")
        rows.append(r)
        used.add(d["ref"])
    overflow = max(0, len(rows) - MAX_PAGE2_ROWS)
    rows = rows[:MAX_PAGE2_ROWS]

    with_rows = {r.get("affected_country_id") or r["country_id"]
                 for r in rows}
    cov = (coverage or {}).get("countries") or {}
    listed = []
    for key, _ in order:
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
    return {
        "groups": [{"key": k, "title": t,
                    "countries": [(countries_by_id.get(c) or {}).get("name")
                                  or c for c in g.get(k) or []]}
                   for k, t in order],
        "rows": rows,
        "overflow": overflow,
        "no_material_change": no_change,
        "collection_gap": gaps,
        "note": ("Geography sets collection priority, not inclusion: a "
                 "country appears in the table only if a material "
                 "development was assessed. 'No material change identified' "
                 "is stated only where collection is at least PARTIAL; "
                 "elsewhere it is a collection gap."),
    }


# --------------------------------------------------------------------------
# 4. Page 3 — Kozel-Kelet, Afrika, tagabb NATO + vezetoi valtozastabla
# --------------------------------------------------------------------------

def _item(d, countries_by_id):
    h = d.get("hu_relevance") or {}
    return {
        "ref": d["ref"],
        "country": ", ".join(d.get("countries") or []) or "—",
        "domain": d.get("capability_domain"),
        "what_changed": clip(d.get("title"), 150),
        "assessment": clip(d.get("so_what") or d.get("capability_delta"),
                           CAPS["item_assessment"], 2),
        "significance": _sig(d),
        "significance_label": hu.significance_label(_sig(d)),
        "confidence": d.get("confidence"),
        "horizon": d.get("effect_timing") or "unknown",
        "hu_relevance": h.get("level"),
        "hu_why": clip(h.get("rationale"), 150, 1),
        "detail_ref": detail_ref([d["ref"]]),
    }


def _region_of(d, countries_by_id):
    return [(countries_by_id.get(c) or {}).get("region")
            for c in d.get("country_ids") or []]


def page3(devs, countries_by_id, coverage, cfg, used):
    g = cfg.get("brief_groups") or {}
    nato = cfg["_nato"]
    page2_set = (set(g.get("non_nato_priority") or [])
                 | set(g.get("neighbours") or [])
                 | set(g.get("extended_nato") or []) | {"hun"})
    secs = {"middle_east": [], "africa": [], "wider_nato": []}
    for d in sorted(devs, key=lambda d: (-_sig(d), hu.rank_key(
            d.get("hu_relevance"), _sig(d), d.get("confidence"),
            d.get("effect_timing")))):
        if d["ref"] in used or not is_material(d):
            continue
        ids = d.get("country_ids") or []
        regs = _region_of(d, countries_by_id)
        key = None
        if any(c in nato and c not in page2_set for c in ids) or "eur" in ids:
            key = "wider_nato"
        elif any(r in (g.get("middle_east_regions") or []) for r in regs):
            key = "middle_east"
        elif any(r in (g.get("africa_regions") or []) for r in regs):
            key = "africa"
        if key and len(secs[key]) < MAX_P3_ITEMS:
            secs[key].append(_item(d, countries_by_id))
            used.add(d["ref"])
    regs_cov = (coverage or {}).get("regions") or {}

    def cov_of(names):
        sts = [regs_cov.get(n, {}).get("status") for n in names]
        sts = [s for s in sts if s]
        if not sts:
            return None
        return "GAP" if all(s == "GAP" for s in sts) else (
            "ADEQUATE" if all(s == "ADEQUATE" for s in sts) else "PARTIAL")

    titles = {"middle_east": "Middle East", "africa": "Africa",
              "wider_nato": "Wider NATO"}
    cov_names = {"middle_east": g.get("middle_east_regions") or [],
                 "africa": g.get("africa_regions") or [],
                 "wider_nato": ["Western Europe", "Northern Europe",
                                "North America"]}
    return {"sections": [{
        "key": k, "title": titles[k], "items": secs[k],
        "coverage": cov_of(cov_names[k]),
        "empty": (None if secs[k] else
                  ("COLLECTION GAP" if cov_of(cov_names[k]) == "GAP"
                   else "NO MATERIAL CHANGE IDENTIFIED")),
    } for k in ("middle_east", "africa", "wider_nato")]}


def change_table(payload, devs, countries_by_id, cfg):
    diff = payload.get("since_last_week") or {}
    by_prog, by_label = {}, {}
    for d in devs:
        if d.get("programme_id"):
            by_prog[d["programme_id"]] = d
        # since_last_week a programme_id hianyaban a display_label/title
        # alapjan kulcsol — ugyanezzel a cimkevel talaljuk meg a fejlemenyt.
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
            "country": country,
            "capability": clip(cap, 60),
            "previous": r.get("previous"),
            "current": r.get("current"),
            "delta": r.get("change"),
            "moved": bool(r.get("moved")),
            "hu_relevance": h.get("level"),
            "hu_score": h.get("score"),
            "confidence": conf,
            "ref": ref,
            "programme_id": r.get("programme_id"),
        })
    rows.sort(key=lambda x: (not x["moved"],
                             hu.LEVEL_RANK.get(x["hu_relevance"], 4),
                             -(x["hu_score"] or 0)))
    overflow = max(0, len(rows) - MAX_CHANGE_ROWS)
    rows = rows[:MAX_CHANGE_ROWS]
    for i, x in enumerate(rows):
        x["priority"] = i + 1
    return {
        "previous_week": diff.get("previous_week"),
        "rows": rows,
        "overflow": overflow,
        "note": diff.get("note") or "",
        "source": "since_last_week (published previous report) — no "
                  "separate baseline",
    }


# --------------------------------------------------------------------------
# 5. Page 4 — globalis strategiai kep, watch, gapek, kovetkezo 7-30 nap
# --------------------------------------------------------------------------

def page4(payload, devs, countries_by_id, coverage, cfg, used):
    g = cfg.get("brief_groups") or {}
    glob_ids = set(g.get("global_strategic") or [])
    glob_regs = set(g.get("global_regions") or [])
    items = []
    for d in sorted(devs, key=lambda d: (-_sig(d), HORIZON_ORDER.get(
            d.get("effect_timing"), 4))):
        if d["ref"] in used or not is_material(d):
            continue
        ids = set(d.get("country_ids") or [])
        regs = set(_region_of(d, countries_by_id))
        if ids & glob_ids or regs & glob_regs or _sig(d) >= 4:
            items.append(_item(d, countries_by_id))
            used.add(d["ref"])
        if len(items) >= MAX_GLOBAL_ITEMS:
            break

    # Priority watch: a riport sajat (max 5) listaja, HU-rangsorral.
    watch = []
    for w in payload.get("priority_watch") or []:
        ids = named_country_ids(" ".join([w.get("issue") or "",
                                          w.get("why_it_matters") or ""]),
                                countries_by_id)
        h = hu.score_item(w, ids, countries_by_id, cfg)
        watch.append({
            "question": clip(w.get("issue"), 110),
            "why": clip(w.get("why_it_matters"), CAPS["watch"], 1),
            "next_observable": clip(w.get("next_observable"),
                                    CAPS["watch"], 1),
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

    # Intelligence gaps: a riport gapjei + a prioritasi orszagok gyujtesi
    # resei. Csak ami az ertekelest megvaltoztathatja.
    gaps = [{"text": clip(x, CAPS["gap"], 2), "origin": "report"}
            for x in (payload.get("intelligence_gaps") or []) if x]
    cov_gaps = [c["name"] for c in (coverage or {}).get("priority") or []
                if c.get("status") == "GAP"]
    if cov_gaps:
        gaps.append({"text": clip(
            "No reporting reached the collection on {} in {} days: the "
            "brief cannot distinguish quiet from unobserved there.".format(
                ", ".join(cov_gaps[:6]), (coverage or {}).get("days", 60)),
            CAPS["gap"]), "origin": "coverage_audit"})
    no_official = [c["name"] for c in (coverage or {}).get("priority") or []
                   if c.get("status") != "GAP" and not c.get(
                       "official_source")]
    if len(gaps) < 3 and no_official:
        gaps.append({"text": clip(
            "Regional reporting relies on specialist media; no official air "
            "force or MoD source is collected for {}.".format(
                ", ".join(no_official[:6])), CAPS["gap"]),
            "origin": "coverage_audit"})
    gaps = gaps[:MAX_GAPS]

    # Kovetkezo 7-30 nap: csak napokon/heteken beluli, nevezett observable.
    nxt = [{"what": x["next_observable"] or x["question"],
            "why": x["question"], "horizon": x["horizon"]}
           for x in watch if (x.get("horizon") or "") in ("days", "weeks")]
    return {
        "global": {"items": items,
                   "empty": None if items else "NO MATERIAL CHANGE IDENTIFIED"},
        "priority_watch": watch,
        "intelligence_gaps": gaps,
        "next_30_days": nxt,
        "next_30_days_empty": (None if nxt else
                               "No dated, intelligence-relevant event "
                               "identified for the next 7–30 days."),
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
            "legend": "Colour = air-power significance (1–5), independent of "
                      "Hungary relevance."}


def matrix(devs):
    return [{"ref": d["ref"],
             "label": clip(d.get("display_label") or d.get("title"), 28),
             "significance": _sig(d),
             "hu_score": (d.get("hu_relevance") or {}).get("score") or 0,
             "hu_level": (d.get("hu_relevance") or {}).get("level")}
            for d in devs if is_material(d)]


# --------------------------------------------------------------------------
# 6. Bottom line — determinisztikus valtozat (mindig elkeszul)
# --------------------------------------------------------------------------

def deterministic_bottom_line(kjs, p2, payload, devs, coverage):
    sents = []
    material = [d for d in devs if is_material(d)]
    high = [d for d in material
            if (d.get("hu_relevance") or {}).get("level") == "HIGH"]
    if not material:
        sents.append({"text": "No material change in the air picture "
                              "relevant to Hungary was identified this "
                              "period.", "refs": []})
    else:
        lead = sorted(material, key=lambda d: hu.rank_key(
            d.get("hu_relevance"), _sig(d), d.get("confidence"),
            d.get("effect_timing")))[0]
        top_refs = {r for k in kjs[:3] for r in (k.get("refs") or [])}
        if not high and lead["ref"] in top_refs:
            lvl = (lead.get("hu_relevance") or {}).get("level") or "LOW"
            sents.append({"text": "None of the {} material air-power "
                                  "developments this period is of HIGH "
                                  "relevance to Hungary; the most relevant "
                                  "are rated {}.".format(len(material), lvl),
                          "refs": []})
        elif not high:
            lvl = (lead.get("hu_relevance") or {}).get("level") or "LOW"
            sents.append({"text": "None of the {} material air-power "
                                  "developments this period is of HIGH "
                                  "relevance to Hungary; the most relevant "
                                  "({}) is: {}.".format(
                                      len(material), lvl,
                                      clip(lead.get("title"), 140).rstrip(".")),
                          "refs": [lead["ref"]]})
        elif lead["ref"] in top_refs:
            # A vezeto tetel ugyis kovetkezik a KJ-mondatokban — nem ismeteljuk.
            sents.append({"text": "{} of {} material air-power developments "
                                  "this period are of HIGH relevance to "
                                  "Hungary.".format(len(high), len(material)),
                          "refs": []})
        else:
            sents.append({"text": "{} of {} material air-power developments "
                                  "this period are of HIGH relevance to "
                                  "Hungary; the leading item is: {}.".format(
                                      len(high), len(material),
                                      clip(lead.get("title"), 140).rstrip(".")),
                          "refs": [lead["ref"]]})
    for k in kjs[:3]:
        if not k.get("statement"):
            continue
        if k["origin"] != "executive_synthesis" and k.get("headline"):
            # A tenyszeru cim + az itelet jellemzoi; maga az itelet (hedge-
            # ekkel egyutt) a mellette levo KJ-kartyan teljes terjedelmeben.
            text = "{} ({} judgement, {} confidence, {}).".format(
                clip(k["headline"], 170).rstrip(". "), k["id"],
                k.get("confidence") or "unstated",
                k.get("horizon") or "horizon unknown")
            sents.append({"text": text, "refs": [k["id"]]})
            continue
        if k["origin"] == "executive_synthesis":
            wc = k.get("what_changed") or ""
            wc = wc[:1].lower() + wc[1:] if wc[:2] != wc[:2].upper() else wc
            text = "{} — {}".format(k["statement"].rstrip(". "), wc)
        else:
            text = k["statement"]
        # Az elso teljes mondat — inkabb rovidebb, mint felbe vagott.
        text = clip(text, CAPS["bottom_line_sentence"], 1).rstrip()
        if not text.endswith((".", "…")):
            text += "."
        sents.append({"text": text, "refs": [k["id"]]})
    changed = sorted({r.get("affected_country") or r["country"]
                      for r in p2.get("rows") or []})
    quiet = [x["name"] for x in p2.get("no_material_change") or []]
    if changed:
        sents.append({"text": "In Hungary's immediate and near region, "
                              "material change was assessed for {}{}.".format(
                                  ", ".join(changed[:6]),
                                  "; no material change was identified for "
                                  "{}".format(", ".join(quiet[:6]))
                                  if quiet else ""),
                      "refs": sorted({r["ref"] for r in p2["rows"]})[:6]})
    elif quiet:
        sents.append({"text": "No material change was identified in "
                              "Hungary's immediate region ({}).".format(
                                  ", ".join(quiet[:6])), "refs": []})
    if p2.get("collection_gap"):
        sents.append({"text": "Collection gaps remain for {}: absence of "
                              "reporting there is not evidence of "
                              "inactivity.".format(
                                  ", ".join(p2["collection_gap"][:5])),
                      "refs": []})
    bm = ((payload.get("stats") or {}).get("baseline_movement") or {})
    if bm.get("events_moving_baseline") == 0:
        sents.append({"text": "No reported event moved a programme-of-record "
                              "quantity this period.", "refs": []})
    return sents[:7]


# --------------------------------------------------------------------------
# 7. Executive synthesis — modell, szigoru validacioval es fallbackkel
# --------------------------------------------------------------------------

SYNTHESIS_PROMPT = """You write the executive synthesis of a 4-page COMMAND AIR
INTELLIGENCE BRIEF for a senior Hungarian Defence Forces (MH) commander.

You receive ONLY material that already passed analytical QA: key judgements
(KJ-xx) and developments (D-xx), each with its Hungary-relevance factors.

Return STRICT JSON only:
{
 "bottom_line": [
   {"text": "<one sentence>", "refs": ["KJ-01", "D-03"]}
 ],
 "why_hungary": {"<KJ-xx or XS-xx or D-xx>": "<one sentence>"}
}

RULES:
- bottom_line: 5 to 7 sentences. Lead with what matters MOST TO HUNGARY / MH /
  NATO's central-eastern air posture, not with what is globally largest.
  Logic: what changed -> why it matters -> what it means for Hungary ->
  what to watch.
- EVERY sentence cites at least one ref from the input. A sentence you cannot
  cite does not belong in the brief.
- NO NEW FACTS: use only figures, dates, names and countries that appear in
  the cited items. Never introduce a number that is not in them.
- CONFIDENCE DICTATES THE VERB: low -> "first indication that"; moderate ->
  "indicates/suggests"; high -> "we assess".
- Keep FACT and ASSESSMENT apart; procurement is not operational capability;
  delivery is not IOC; a milestone is not a capability.
- No trend words (accelerating, surge, pivot) and no superlatives (most
  capable, largest operator).
- If little changed for Hungary, say so plainly.
- why_hungary: one sentence per item id given in "items", explaining the
  relevance to Hungary/MH/NATO in concrete terms (airspace, QRA/air policing,
  regional balance, NATO posture, MH capability planning, interoperability).
  Base it on the listed hu_factors; do not invent new ones."""


def _numbers(text):
    return set(re.findall(r"\d+(?:[.,]\d+)?", text or ""))


def _item_text(x):
    keys = ("statement", "what_changed", "assessment", "why_hungary",
            "next_observable", "title", "fact", "capability_delta", "so_what",
            "judgement", "basis")
    return " ".join(str(x.get(k) or "") for k in keys)


def validate_sentence(text, refs, ref_text, ref_countries, countries_by_id,
                      withheld_kw):
    """Igaz/hamis + ok. Egy mondat csak akkor marad, ha visszakovetheto."""
    import ac_intel  # lusta import (a modul anthropic-ot nem igenyel)
    if not refs or any(r not in ref_text for r in refs):
        return False, "uncited or unknown ref"
    src = " ".join(ref_text[r] for r in refs)
    extra = _numbers(text) - _numbers(src)
    if extra:
        return False, "number not in cited items: {}".format(
            ", ".join(sorted(extra)))
    allowed = set()
    for r in refs:
        allowed |= set(ref_countries.get(r) or [])
    allowed |= {"hun"}
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


def synthesize(client, brief, payload, devs, countries_by_id):
    """Az executive synthesis. None, ha nincs kliens / hiba / kevés ervenyes
    mondat — ilyenkor a determinisztikus bottom line marad."""
    if client is None:
        return None
    import ac_intel  # noqa: E402
    items = brief["page1"]["key_judgements"]
    dev_by_ref = {d["ref"]: d for d in devs}
    ref_text, ref_countries = {}, {}
    for x in items:
        ref_text[x["id"]] = _item_text(x)
        ids = set()
        for r in x.get("refs") or []:
            ids |= set((dev_by_ref.get(r) or {}).get("country_ids") or [])
        ids |= set(named_country_ids(x.get("statement") or "",
                                     countries_by_id))
        ref_countries[x["id"]] = sorted(ids)
    for d in devs:
        if is_material(d):
            ref_text[d["ref"]] = _item_text(d)
            ref_countries[d["ref"]] = list(d.get("country_ids") or [])
    withheld_kw = [ac_intel._kw(j.get("judgement") or "")
                   for j in payload.get("judgements_requiring_review") or []]
    req = {
        "items": [{"id": x["id"], "origin": x["origin"],
                   "statement": x["statement"],
                   "what_changed": x["what_changed"],
                   "assessment": x["assessment"],
                   "confidence": x["confidence"], "horizon": x["horizon"],
                   "significance": x["significance"],
                   "hu_level": x["hu_relevance"]["level"],
                   "hu_factors": [f["label"] for f in
                                  x["hu_relevance"]["factors"]],
                   "refs": x["refs"]} for x in items],
        "developments": [{"ref": d["ref"], "title": d.get("title"),
                          "capability_delta": d.get("capability_delta"),
                          "so_what": d.get("so_what"),
                          "countries": d.get("countries"),
                          "significance": _sig(d),
                          "confidence": d.get("confidence"),
                          "effect_timing": d.get("effect_timing"),
                          "hu_level": (d.get("hu_relevance") or {}).get(
                              "level"),
                          "hu_factors": [f["label"] for f in (
                              d.get("hu_relevance") or {}).get("factors")
                              or []]}
                         for d in devs if is_material(d)][:14],
        "regional_no_change": [x["name"] for x in
                               brief["page2"]["no_material_change"]],
        "collection_gaps": brief["page2"]["collection_gap"],
    }
    try:
        out = ac_intel._call(client, SYNTHESIS_PROMPT, req, 3000)
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
        text = clip(s.get("text"), CAPS["bottom_line_sentence"] + 60)
        refs = [r for r in (s.get("refs") or []) if isinstance(r, str)]
        ok, why = validate_sentence(text, refs, ref_text, ref_countries,
                                    countries_by_id, withheld_kw)
        (kept if ok else dropped).append(
            {"text": text, "refs": refs} if ok else
            {"text": text, "refs": refs, "reason": why})
    why_hu, why_dropped = {}, []
    for rid, text in (out.get("why_hungary") or {}).items():
        if rid not in ref_text or not isinstance(text, str):
            continue
        text = clip(text, CAPS["why_hu"], 2)
        ok, why = validate_sentence(text, [rid], ref_text, ref_countries,
                                    countries_by_id, withheld_kw)
        if ok:
            why_hu[rid] = text
        else:
            why_dropped.append({"id": rid, "reason": why})
    return {"bottom_line": kept[:7], "dropped": dropped,
            "why_hungary": why_hu, "why_dropped": why_dropped}


# --------------------------------------------------------------------------
# 8. Osszeallitas
# --------------------------------------------------------------------------

def build_command_brief(payload, countries_by_id, coverage=None, cfg=None,
                        client=None, events_by_id=None, window=None):
    """A brief adatmodellje. A payload developments-et annotalja (ref,
    country_ids, hu_relevance), a brief pedig ezekre HIVATKOZIK."""
    cfg = cfg or hu.load_config()
    devs = annotate_developments(payload, countries_by_id, events_by_id, cfg)
    used = set()
    kjs = page1_judgements(payload, devs, countries_by_id, cfg)
    p2 = page2(devs, countries_by_id, coverage, cfg, used)
    p3 = page3(devs, countries_by_id, coverage, cfg, used)
    p4 = page4(payload, devs, countries_by_id, coverage, cfg, used)
    meta = payload.get("report_meta") or {}
    brief = {
        "schema": BRIEF_SCHEMA,
        "week_label": payload.get("week_label") or meta.get("week_label"),
        "title": "Command Air Intelligence Brief",
        "classification": "UNCLASSIFIED // OSINT",
        "period": {
            "start": meta.get("period_start"), "end": meta.get("period_end"),
            "timezone": meta.get("timezone"),
            "window_label": meta.get("window_label"),
        },
        "generated_utc": meta.get("generated_utc"),
        "status": meta.get("status"),
        "methodology_version": meta.get("methodology_version"),
        "hu_model_version": cfg.get("version"),
        "restatement": meta.get("restatement"),
        "page1": {
            "bottom_line": None,
            "key_judgements": kjs,
            "map_cee": cee_hotspots(devs, coverage, cfg, countries_by_id),
        },
        "page2": p2,
        "page3": p3,
        "change_table": change_table(payload, devs, countries_by_id, cfg),
        "page4": p4,
        "map_global": global_hotspots(devs, countries_by_id),
        "matrix": matrix(devs),
        "coverage_summary": {
            "priority": [{"name": c["name"], "status": c["status"],
                          "events_window": c["events_window"],
                          "official_source": c["official_source"]}
                         for c in (coverage or {}).get("priority") or []],
            "summary": (coverage or {}).get("summary"),
            "note": (coverage or {}).get("note"),
        },
    }

    det = deterministic_bottom_line(kjs, p2, payload, devs, coverage)
    syn = synthesize(client, brief, payload, devs, countries_by_id)
    if syn and len(syn["bottom_line"]) >= 3:
        brief["page1"]["bottom_line"] = {
            "origin": "executive_synthesis",
            "sentences": syn["bottom_line"],
            "dropped_by_validation": syn["dropped"],
            "note": ("Executive synthesis — a higher-level reading of the "
                     "QA-passed judgements and developments. Every sentence "
                     "cites its source items; numbers and countries are "
                     "checked against them."),
        }
    else:
        brief["page1"]["bottom_line"] = {
            "origin": "deterministic",
            "sentences": det,
            "dropped_by_validation": (syn or {}).get("dropped") or [],
            "note": ("Assembled deterministically from the QA-passed key "
                     "judgements, developments and coverage audit."
                     + (" The model synthesis did not pass validation." if syn
                        else "")),
        }
    if syn:
        for x in kjs:
            t = syn["why_hungary"].get(x["id"])
            if t:
                x["why_hungary"] = t
                x["why_hungary_origin"] = "executive_synthesis"

    # --- traceability: minden brief-tetel letezo forrasra mutat ---
    valid = {d["ref"] for d in devs} | {
        k.get("id") for k in payload.get("key_judgements") or []} | {
        x["id"] for x in kjs}
    refs = set()
    for x in kjs:
        refs |= set(x.get("refs") or [])
    for r in p2["rows"]:
        refs.add(r["ref"])
    for s in p3["sections"]:
        refs |= {i["ref"] for i in s["items"]}
    refs |= {i["ref"] for i in p4["global"]["items"]}
    for s in brief["page1"]["bottom_line"]["sentences"]:
        refs |= set(s.get("refs") or [])
    brief["traceability"] = {
        "refs_used": sorted(r for r in refs if r),
        "unresolved_refs": sorted(r for r in refs if r and r not in valid),
        "executive_synthesis_items": [x["id"] for x in kjs
                                      if x["origin"] == "executive_synthesis"],
        "withheld_judgements_excluded": [
            j.get("id") for j in payload.get("judgements_requiring_review")
            or []],
        "note": ("Single analytical truth: every brief item is a view of a "
                 "development (D-xx) or key judgement (KJ-xx) in the detailed "
                 "report. XS-xx items are executive synthesis and trace to "
                 "the listed D-xx."),
    }
    return brief
