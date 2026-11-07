# -*- coding: utf-8 -*-
"""HUNGARY RELEVANCE — determinisztikus, kulon dimenzio.

Ket kerdes, ket kulon skala:
  * AIR POWER SIGNIFICANCE (1-5) — mennyire valtoztat a legiero-kepen
    altalaban. Ezt az elemzoi reteg adja (developments[].significance).
  * HUNGARY RELEVANCE (0-100 -> HIGH/MEDIUM/LOW/MINIMAL) — mennyire szamit
    Magyarorszagnak / az MH-nak / a NATO kozep-keleti legterpoziciojanak.

A HU-relevancia NEM tavolsag. A foldrajz csak az alap; erre jonnek a
tenyezok (air policing/QRA, keleti szarny, legterincidens, legvedelem,
regionalis eroegyensuly, NATO-enablerek, MH-platformok, regionalis
logisztika, gyakorlat, horizont). Egy amerikai F-35-telepites Romaniaba
igy lehet HIGH, egy jelentos japan beszerzes pedig LOW.

Minden alkalmazott tenyezo pontszammal es indoklassal bekerul a jelentesbe:
a pontszam mindig visszakovetheto. Modellhivas NINCS.
"""
import json
import re
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / \
    "hungary_relevance.json"

LEVEL_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "MINIMAL": 3}
SIG_LABELS = {5: "VERY HIGH", 4: "HIGH", 3: "MEDIUM", 2: "LOW", 1: "MINIMAL"}

_CFG = None


def load_config(path=None):
    global _CFG
    if path is None and _CFG is not None:
        return _CFG
    cfg = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    cfg["_hu_rx"] = re.compile(cfg["hungary_markers_rx"])
    cfg["_platforms"] = [(re.compile(p["rx"], re.I), p["label"])
                         for p in cfg.get("mh_platforms") or []]
    for f in cfg.get("factors") or []:
        f["_rx"] = re.compile(f["text_rx"], re.I) if f.get("text_rx") else None
    cfg["_nato"] = set(cfg.get("nato_members") or [])
    g = cfg.get("brief_groups") or {}
    cfg["_cee"] = (set(g.get("non_nato_priority") or [])
                   | set(g.get("neighbours") or [])
                   | set(g.get("extended_nato") or []) | {"hun", "mda"})
    if path is None:
        _CFG = cfg
    return cfg


def significance_label(sig):
    try:
        return SIG_LABELS.get(int(sig), "MINIMAL")
    except (TypeError, ValueError):
        return "MINIMAL"


def level_for(score, cfg=None):
    cfg = cfg or load_config()
    for lv in cfg["levels"]:
        if score >= lv["min"]:
            return lv["level"]
    return "MINIMAL"


def _text_of(item):
    """EVIDENCIA-szoveg: amit a forras allit (cim, tény, kepesseg-valtozas),
    NEM a sajat elemzesunk (so_what, indicators). Kulonben a modell sajat
    "Hungary's southern border" mondata emelne a HU-relevanciat — a
    pontszam onmagat igazolna."""
    parts = []
    for k in ("title", "display_label", "fact", "capability_delta",
              "summary", "judgement", "basis", "issue", "why_it_matters"):
        v = item.get(k)
        if v:
            parts.append(str(v))
    return " ".join(parts)


def _country_name_rx(countries_by_id, ids):
    names = []
    for cid in ids:
        c = countries_by_id.get(cid) or {}
        for n in [c.get("name")] + list(c.get("aliases") or []):
            if n and len(n) >= 4:
                names.append(re.escape(n))
    if not names:
        return None
    return re.compile(r"\b(" + "|".join(sorted(set(names), key=len,
                                               reverse=True)) + r")\b")


def geography(cid, countries_by_id, cfg):
    g = (cfg.get("geography") or {}).get(cid)
    if g:
        return g["points"], g["tier"], g["why"]
    c = countries_by_id.get(cid) or {}
    d = cfg.get("default_points") or {}
    if cid in cfg["_nato"]:
        return d.get("nato_member", 8), "wider_nato", \
            "NATO ally — Alliance-wide capability change"
    if c.get("region") in (cfg.get("europe_regions") or []):
        return d.get("europe", 5), "europe", "European state"
    return d.get("other", 0), "distant", "outside Hungary's region"


def score_item(item, country_ids, countries_by_id, cfg=None):
    """HU-relevancia egy fejlemenyre (vagy barmely, hasonlo mezoju tetelre).

    item: development dict (title, fact, capability_delta, so_what,
          capability_domain, lifecycle_stage, effect_timing, ...).
    country_ids: a fejlemeny szereploi (country_id lista; az elso a fo
          szereplo, ha tobb van, a legmagasabb foldrajzi pontszam szamit).
    Visszaad: {"score","level","tier","primary_country","factors":[...],
               "rationale","version"}
    """
    cfg = cfg or load_config()
    text = _text_of(item)
    ids = [c for c in (country_ids or []) if c]
    factors = []

    # --- 1. foldrajz: a legrelevansabb szereplo szamit ---
    best = (0, "distant", "outside Hungary's region", None)
    for cid in ids:
        pts, tier, why = geography(cid, countries_by_id, cfg)
        if pts > best[0] or best[3] is None:
            best = (pts, tier, why, cid)
    geo_pts, tier, geo_why, primary = best
    if primary is not None or geo_pts:
        name = (countries_by_id.get(primary or "") or {}).get("name") or primary
        factors.append({"id": "geography", "label": "Geography / actor",
                        "points": geo_pts,
                        "why": "{}: {}".format(name, geo_why) if name
                        else geo_why})

    # --- 2. Magyarorszag kozvetlenul ---
    if "hun" not in ids and cfg["_hu_rx"].search(text):
        factors.append({"id": "hungary_named", "label": "Names Hungary / MH",
                        "points": 40,
                        "why": "the reporting names Hungary or the Hungarian "
                               "Defence Forces directly"})

    # --- 3. MH-platform ---
    for rx, label in cfg["_platforms"]:
        if rx.search(text):
            factors.append({"id": "mh_platform", "label": "MH platform",
                            "points": 15,
                            "why": "{} — lessons, sustainment, user-group and "
                                   "interoperability effects carry over to "
                                   "MH".format(label)})
            break

    domain = item.get("capability_domain")
    stage = item.get("lifecycle_stage")
    actor_nato = any(c in cfg["_nato"] for c in ids)
    regional_actor = any(c in cfg["_cee"] for c in ids)
    others = [c for c in cfg["_cee"] if c not in ids and c != "hun"]
    cee_rx = _country_name_rx(countries_by_id, others)

    for f in cfg.get("factors") or []:
        hit = False
        if f.get("names_cee_country"):
            m = cee_rx.search(text) if cee_rx else None
            if m:
                hit = True
                why = "{} — {}".format(f["why"], m.group(1))
        else:
            # JEL (szoveg VAGY domain) ES minden KAPU (tier, stadium,
            # NATO-szereplo, regionalis szereplo).
            signals = []
            if f.get("_rx") is not None:
                signals.append(bool(f["_rx"].search(text)))
            if f.get("domains"):
                signals.append(domain in f["domains"])
            gates = []
            if f.get("tiers"):
                gates.append(tier in f["tiers"])
            if f.get("exclude_tiers"):
                gates.append(tier not in f["exclude_tiers"])
            if f.get("stages"):
                gates.append(stage in f["stages"])
            if f.get("nato_actor"):
                gates.append(actor_nato)
            if f.get("regional_actor"):
                gates.append(regional_actor)
            if f.get("min_significance"):
                try:
                    sig = int(item.get("significance") or 0)
                except (TypeError, ValueError):
                    sig = 0
                gates.append(sig >= int(f["min_significance"]))
            hit = ((any(signals) if signals else True) and all(gates)
                   and bool(signals or gates))
            why = f["why"]
        if hit:
            factors.append({"id": f["id"], "label": f["label"],
                            "points": f["points"], "why": why})

    # --- horizont ---
    hm = (cfg.get("horizon_modifier") or {}).get(
        item.get("effect_timing") or "unknown", 0)
    if hm and factors:
        factors.append({"id": "horizon", "label": "Horizon",
                        "points": hm,
                        "why": "effect {}".format(item.get("effect_timing"))})

    score = max(0, min(100, sum(f["points"] for f in factors)))
    level = level_for(score, cfg)
    ranked = sorted([f for f in factors
                     if f["points"] > 0 and f["id"] != "horizon"],
                    key=lambda f: -f["points"])
    rationale = "; ".join(f["why"] for f in ranked[:2])
    if rationale:
        rationale = rationale[0].upper() + rationale[1:] + "."
    if score < 15:
        rationale = ("No direct link to Hungary, MH or NATO's central-eastern "
                     "air posture identified{}.".format(
                         " ({})".format(ranked[0]["why"]) if ranked else ""))
    return {"score": score, "level": level, "tier": tier,
            "primary_country": primary, "factors": factors,
            "rationale": rationale, "version": cfg.get("version")}


def rank_key(hu, significance, confidence, effect_timing):
    """Rangsor: HU relevance -> significance -> confidence -> immediacy."""
    conf = {"high": 0, "moderate": 1, "low": 2}.get(confidence or "", 3)
    hz = {"immediate": 0, "<12 months": 1, "1-3 years": 2, ">3 years": 3}.get(
        effect_timing or "", 4)
    try:
        sig = int(significance or 1)
    except (TypeError, ValueError):
        sig = 1
    return (LEVEL_RANK.get((hu or {}).get("level"), 4),
            -((hu or {}).get("score") or 0), -sig, conf, hz)
