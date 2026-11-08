# -*- coding: utf-8 -*-
"""RSS / ATOM FORRASFELDERITES a coverage audit jelolt forrasaira.

A config/coverage_sources.json "candidates" listajan vegigmegy (hivatalos
legiero, MoD, beszerzesi ugynokseg, NATO, OEM, szakmedia), es mindegyiknel:
  1. a nyitooldal <link rel="alternate" type="application/rss+xml|atom+xml">
     hivatkozasait keresi;
  2. a szokasos feed-utvonalakat probalja (/feed, /rss, /rss.xml, ...);
  3. minden talalatot ELLENORIZ: valodi RSS/Atom-e, hany eleme van, mikori a
     legfrissebb.

Csak OLVAS, semmit nem vesz fel. Az eredmeny: data/source_discovery.json +
egy tablazat. Ami ellenorzott feed, az a config/source_expansion.json-ba
kerulhet, es a scripts/add_sources.py veszi fel. Ahol nincs feed, ott a
hivatalos hirek oldala "page polling" jelolt marad (RSS preferalt, nem
kotelezo: a tartalom relevanciaja fontosabb a protokollnal).

Usage: python scripts/source_discovery.py [--country srb] [--timeout 15]
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
UA = "AircraftTracker-SourceDiscovery/1.0 (+feed discovery; read-only)"
COMMON_PATHS = ["/feed", "/feed/", "/rss", "/rss.xml", "/feed.xml",
                "/atom.xml", "/index.xml", "/en/rss", "/en/feed", "/_rss",
                "/rss.php", "/news/rss", "/press/rss"]
ALT_RX = re.compile(r"<link[^>]+rel=[\"']alternate[\"'][^>]*>", re.I)
HREF_RX = re.compile(r"href=[\"']([^\"']+)[\"']", re.I)
TYPE_RX = re.compile(r"type=[\"']application/(rss|atom)\+xml[\"']", re.I)


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read(2_000_000), r.headers.get("Content-Type", "")


def check_feed(url, timeout):
    """(ok, info) — valodi feed-e, elemszam, legfrissebb datum, cim."""
    try:
        body, _ = fetch(url, timeout)
        root = ET.fromstring(body)
    except Exception as exc:  # noqa: BLE001
        return False, {"error": type(exc).__name__}
    tag = root.tag.lower()
    items, dates, title = [], [], None
    if tag.endswith("rss") or tag.endswith("rdf"):
        ch = root.find("channel")
        title = (ch.findtext("title") if ch is not None else None)
        items = root.findall(".//item")
        for it in items:
            d = it.findtext("pubDate") or it.findtext(
                "{http://purl.org/dc/elements/1.1/}date")
            try:
                dates.append(parsedate_to_datetime(d).replace(tzinfo=None))
            except Exception:  # noqa: BLE001
                pass
    elif tag.endswith("feed"):
        ns = "{http://www.w3.org/2005/Atom}"
        title = root.findtext(ns + "title")
        items = root.findall(ns + "entry")
        for it in items:
            d = it.findtext(ns + "updated") or it.findtext(ns + "published")
            try:
                dates.append(datetime.fromisoformat(
                    str(d).replace("Z", "+00:00")[:19]))
            except Exception:  # noqa: BLE001
                pass
    else:
        return False, {"error": "not RSS/Atom"}
    return bool(items), {"title": title, "items": len(items),
                         "newest": max(dates).isoformat()[:10] if dates
                         else None}


def discover(cand, timeout):
    home = cand.get("homepage")
    found, tried = [], []
    if cand.get("rss_url"):
        found.append(cand["rss_url"])
    try:
        body, _ = fetch(home, timeout)
        html = body.decode("utf-8", "replace")
        for tag in ALT_RX.findall(html):
            if TYPE_RX.search(tag):
                m = HREF_RX.search(tag)
                if m:
                    found.append(urljoin(home, m.group(1)))
    except Exception as exc:  # noqa: BLE001
        return {"homepage": home, "status": "UNREACHABLE",
                "error": type(exc).__name__, "feeds": []}
    for path in COMMON_PATHS:
        found.append(urljoin(home, path))
    feeds, seen = [], set()
    for url in found:
        if url in seen:
            continue
        seen.add(url)
        ok, info = check_feed(url, timeout)
        tried.append(url)
        if ok:
            feeds.append(dict(info, url=url))
    return {"homepage": home,
            "status": "FEED" if feeds else "NO FEED (page polling candidate)",
            "feeds": feeds, "tried": len(tried)}


def main():
    args = sys.argv[1:]
    only = args[args.index("--country") + 1] if "--country" in args else None
    timeout = int(args[args.index("--timeout") + 1]) if "--timeout" in args \
        else 15
    cfg = json.loads((ROOT / "config" / "coverage_sources.json").read_text(
        encoding="utf-8"))
    out = []
    for cand in cfg.get("candidates") or []:
        if only and cand.get("country_id") != only:
            continue
        res = dict(discover(cand, timeout), name=cand.get("name"),
                   country_id=cand.get("country_id"), tier=cand.get("tier"),
                   language=cand.get("language"), caveat=cand.get("caveat"))
        out.append(res)
        best = res["feeds"][0] if res["feeds"] else {}
        print("{:<5} {:<44} {:<32} {}".format(
            res.get("country_id") or "-", (res["name"] or "")[:44],
            res["status"][:32], "{} ({} items, newest {})".format(
                best.get("url"), best.get("items"), best.get("newest"))
            if best else ""))
    path = ROOT / "data" / "source_discovery.json"
    path.write_text(json.dumps({"run": datetime.utcnow().isoformat()[:19],
                                "results": out}, ensure_ascii=False,
                               indent=2), encoding="utf-8")
    print("\nSaved {}".format(path))


if __name__ == "__main__":
    main()
