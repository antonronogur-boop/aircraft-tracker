# -*- coding: utf-8 -*-
"""Full fleet import from Wikipedia — one inventory table per country.

For every country in data/wiki_sources.json (or matchable by naming
pattern), downloads the Wikipedia article, finds the aircraft-inventory
wikitable(s) ("Aircraft | Origin | Type | Variant | In service | Notes"
format used across air-force articles), and builds complete fleet rows:

  * aircraft names are matched to the catalogue via aliases;
  * UNKNOWN types are auto-added to ac_aircraft_types (marked
    "auto-imported from Wikipedia" — clean them up later at your leisure);
  * "N on order" mentions in the notes become on_order rows;
  * per-country rows replace previous [baseline]/[wiki] rows, while
    [event]-tagged and hand-edited rows are preserved.

Usage (from Aircraft_Tracker/, env vars set):
    pip install beautifulsoup4
    python scripts\\import_wikipedia_fleets.py            (dry run, report only)
    python scripts\\import_wikipedia_fleets.py --apply    (write to Supabase)
    python scripts\\import_wikipedia_fleets.py --apply --only srb,hun,hrv
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_client as db  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
WIKI_TITLES = {k: v for k, v in json.loads(
    (DATA_DIR / "wiki_sources.json").read_text(encoding="utf-8")).items()
    if not k.startswith("_")}
UA = "AircraftTrackerBot/1.0 (private research; contact: repo owner)"

CATEGORY_KEYWORDS = [
    ("uav", ["uav", "ucav", "unmanned", "drone"]),
    ("helicopter", ["helicopter", "rotorcraft", "attack heli", "utility heli"]),
    ("maritime_patrol", ["maritime patrol", "asw", "anti-submarine"]),
    ("special_mission", ["aew", "awacs", "surveillance", "reconnaissance", "electronic warfare",
                         "early warning", "sigint", "command post", "isr"]),
    ("tanker", ["tanker", "refuel"]),
    ("transport", ["transport", "airlift", "cargo", "utility aircraft", "liaison", "vip"]),
    ("bomber", ["bomber"]),
    ("attack", ["attack", "close air support", "ground-attack", "cas"]),
    ("trainer", ["trainer", "training"]),
    ("fighter", ["fighter", "multirole", "interceptor", "air superiority", "combat aircraft"]),
]


def fetch_page(title):
    """Fetch article HTML: REST API first, plain article URL as fallback,
    with retries — Wikipedia intermittently drops requests, and a single
    failure must not mark a country as NO PAGE."""
    quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")
    urls = [
        "https://en.wikipedia.org/api/rest_v1/page/html/{}".format(quoted),
        "https://en.wikipedia.org/wiki/{}".format(quoted),
    ]
    for url in urls:
        for attempt in range(3):
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    break  # real missing title -> try next URL form
                time.sleep(2 * (attempt + 1))
            except Exception:  # noqa: BLE001 — network hiccup
                time.sleep(2 * (attempt + 1))
    return None


def clean(cell):
    text = cell.get_text(" ", strip=True)
    text = re.sub(r"\[\d+\]", "", text)          # footnote refs
    return re.sub(r"\s+", " ", text).strip()


def ints_in(text):
    return [int(x) for x in re.findall(r"\d[\d,]*", text.replace(",", ""))
            if x.isdigit() or x.replace(",", "").isdigit()][:6]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def guess_category(type_text, section_text):
    hay = (type_text + " " + section_text).lower()
    for cat, kws in CATEGORY_KEYWORDS:
        if any(k in hay for k in kws):
            return cat
    return "fighter"


def build_type_index():
    idx = {}
    for t in db.select("ac_aircraft_types", {"select": "type_id,name,designation,aliases"}):
        for v in [t["type_id"], t.get("name"), t.get("designation")] + list(t.get("aliases") or []):
            if v:
                idx[str(v).lower()] = t["type_id"]
    return idx


def match_type(name, idx):
    v = name.strip().lower()
    if v in idx:
        return idx[v]
    for alias, tid in sorted(idx.items(), key=lambda kv: -len(kv[0])):
        if len(alias) >= 4 and alias in v:
            return tid
    return None


def parse_inventory(html):
    """Yield dicts {name, type_text, section, variant, active, on_order}."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for table in soup.find_all("table"):
        cls = " ".join(table.get("class") or [])
        if "wikitable" not in cls:
            continue
        first_tr = table.find("tr")
        if first_tr is None:
            continue
        headers = [clean(x).lower() for x in first_tr.find_all(["th", "td"])[:10]]
        joined = " ".join(headers)
        # Two common formats:
        #   A) "Aircraft | Origin | Type | Variant | In service | Notes"
        #   B) "Type | Image | Origin | Class/Role | Introduced | In service | Total"
        #      ("List of active X military aircraft" pages -- name col is "Type")
        if not headers or ("aircraft" not in joined and "type" not in joined):
            continue
        if not any(("in service" in h) or ("quantity" in h) or ("number" in h)
                   or (h == "total") for h in headers):
            continue
        # column positions
        def col(*names):
            for i, h in enumerate(headers):
                if any(n in h for n in names):
                    return i
            return None
        c_name = col("aircraft")
        name_is_type_col = c_name is None
        if c_name is None:
            c_name = col("type")
        if c_name is None:
            c_name = 0
        c_type = col("role", "class") if name_is_type_col else col("type", "role", "class")
        c_var = col("variant", "version")
        c_serv = col("in service", "quantity", "number")
        if c_serv is None:
            c_serv = col("total")
        c_notes = col("note")
        section = ""
        for tr in table.find_all("tr"):
            if tr is first_tr:
                continue
            tds = tr.find_all(["th", "td"])   # many pages put the aircraft
            if not tds:                        # name in a row-header <th>
                continue
            if all(td.name == "th" for td in tds):
                continue                       # secondary header row
            if len(tds) == 1 and tds[0].get("colspan"):
                section = clean(tds[0])
                continue
            name = clean(tds[c_name]) if c_name < len(tds) else ""
            if not name or len(name) < 2 or name.lower() in ("aircraft", "type", "total") \
                    or name.lower().startswith("total"):
                continue
            def cell(i):
                return clean(tds[i]) if i is not None and i < len(tds) else ""
            serv_text = cell(c_serv)
            notes_text = cell(c_notes)
            active = sum(ints_in(serv_text)) if serv_text else 0
            m = re.search(r"(\d[\d,]*)\s*(?:\+?\s*)?(?:more\s+|additional\s+)?on\s+order",
                          (serv_text + " " + notes_text).lower())
            on_order = int(m.group(1).replace(",", "")) if m else 0
            if active == 0 and on_order == 0:
                continue
            out.append({
                "name": name, "type_text": cell(c_type), "section": section,
                "variant": cell(c_var), "active": active, "on_order": on_order,
            })
    return out


def candidates_for(cid, cname):
    if cid in WIKI_TITLES:
        yield WIKI_TITLES[cid]
    yield "List of active {} military aircraft".format(cname)
    yield "{} Air Force".format(cname)


def main():
    apply = "--apply" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))

    countries = db.select("ac_countries", {"select": "country_id,name"})
    type_idx = build_type_index()
    today = time.strftime("%Y-%m-%d")

    report = []
    new_types = {}
    total_rows = 0

    for c in countries:
        cid, cname = c["country_id"], c["name"]
        if cid == "eur" or (only and cid not in only):
            continue
        html = None
        used_title = None
        for i, title in enumerate(candidates_for(cid, cname)):
            html = fetch_page(title)
            if html and (i == 0 or "wikitable" in html):
                used_title = title
                break
            html = None
            time.sleep(0.5)
        if not html:
            report.append((cid, "NO PAGE", 0, 0))
            continue

        rows = parse_inventory(html)
        if not rows:
            report.append((cid, used_title, 0, 0))
            continue

        # aggregate per (type_id, status)
        agg = {}
        unmatched = 0
        for r in rows:
            tid = match_type(r["name"], type_idx)
            if tid is None:
                # auto-add catalogue entry
                tid = slugify(r["name"])
                if tid not in new_types and tid not in type_idx.values():
                    new_types[tid] = {
                        "type_id": tid, "name": r["name"][:120],
                        "designation": r["variant"][:80] or None,
                        "category": guess_category(r["type_text"], r["section"]),
                        "manufacturer": None, "origin_country": None,
                        "role": (r["type_text"] or r["section"])[:120] or None,
                        "production_status": "in_production",
                        "notes": "auto-imported from Wikipedia ({})".format(used_title),
                        "aliases": [],
                    }
                type_idx[r["name"].lower()] = tid
                unmatched += 1
            if r["active"]:
                key = (tid, "active")
                agg[key] = agg.get(key, 0) + r["active"]
            if r["on_order"]:
                key = (tid, "on_order")
                agg[key] = agg.get(key, 0) + r["on_order"]

        fleet_rows = [{
            "country_id": cid, "type_id": tid, "fleet_status": status,
            "quantity": qty, "as_of": today,
            "source_note": "[wiki] {}".format(used_title)[:500],
        } for (tid, status), qty in agg.items()]
        total_rows += len(fleet_rows)
        report.append((cid, used_title, len(fleet_rows), unmatched))

        if apply and fleet_rows:
            if new_types:
                db.upsert("ac_aircraft_types", list(new_types.values()), "type_id")
                new_types = {}
            # replace previous baseline/wiki rows for this country
            for tag in ("[baseline]", "[wiki]"):
                db._request("DELETE", "ac_fleets",  # noqa: SLF001
                            params={"country_id": "eq." + cid,
                                    "source_note": "like.{}%".format(tag)},
                            prefer="return=minimal")
            db.upsert("ac_fleets", fleet_rows, "country_id,type_id,fleet_status")
        time.sleep(1)  # politeness

    print("\n{:<6} {:<55} {:>5} {:>10}".format("ctry", "page", "rows", "new types"))
    for cid, title, n, unm in report:
        print("{:<6} {:<55} {:>5} {:>10}".format(cid, str(title)[:55], n, unm))
    print("\nTotal fleet rows: {}".format(total_rows))
    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to import.")


if __name__ == "__main__":
    main()
