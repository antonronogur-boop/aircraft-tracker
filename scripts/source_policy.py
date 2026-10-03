# -*- coding: utf-8 -*-
"""
source_policy.py — FORRAS-SZINTU KAPU A DRAGA KINYERES ELE

MIERT: a 2026-10-03-i meres szerint a 8599 cikkbol 1971 (23%) irrelevans
lett — mindegyikert egy TELJES Sonnet-hivas aran, akar 12 000 karakter
cikkszoveggel. A pazarlas 65%-a nyolc forrasbol jott. Kulcsszavas szures
ebbol legfeljebb 5%-ot fog meg, es minden egyes mintaval no az eselye, hogy
relevans anyagot dob el. A forras viszont stabil, merheto es visszavonhato
dontes.

HAROM ALLAPOT:
    pass        — a szokasos (draga) kinyeres. EZ AZ ALAPERTELMEZES.
    haiku_gate  — eloszor egy olcso modell dont a cim+osszefoglalo alapjan.
    drop        — nincs modellhivas, a cikk status='irrelevant' lesz.

A 'drop' NEM TORLES. A cikk ugyanabba az allapotba kerul, amit a modell
adott volna neki, tehat auditalhato marad, es a policy valtoztatasaval
barmikor ujra feldolgozhato. Egyetlen sor sem vesz el.

ISMERETLEN FORRAS -> 'pass'. Egy ujonnan felvett forras sosem eshet ki
csendben: a hallgatas nem jelenthet kizarast.
"""
import json
import os
from pathlib import Path

PASS = "pass"
HAIKU_GATE = "haiku_gate"
DROP = "drop"
VALID = (PASS, HAIKU_GATE, DROP)

_CACHE = {"loaded": False, "default": PASS, "policies": {}, "path": None}


def _config_path():
    env = os.environ.get("UAV_SOURCE_POLICY")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents)[:4]:
        candidate = parent / "config" / "source_policy.json"
        if candidate.is_file():
            return candidate
    return None


def load(force=False):
    """A policy betoltese. Hianyzo vagy hibas fajl eseten MINDEN 'pass'.

    Ez a biztonsagos irany: ha a konfiguracio nem olvashato, a rendszer a
    draga, de TELJES feldolgozast valasztja. A forditottja — hallgatasbol
    kizarast kovetkeztetni — adatot veszitene.
    """
    if _CACHE["loaded"] and not force:
        return _CACHE

    _CACHE.update({"loaded": True, "default": PASS, "policies": {}, "path": None})
    path = _config_path()
    if not path:
        return _CACHE

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        print("  [warn] source_policy.json nem olvashato ({}), minden forras 'pass'".format(e))
        return _CACHE

    default = data.get("default")
    if default in VALID:
        _CACHE["default"] = default

    for sid, entry in (data.get("policies") or {}).items():
        value = entry.get("policy") if isinstance(entry, dict) else entry
        if value in VALID:
            _CACHE["policies"][sid] = {
                "policy": value,
                "name": (entry.get("name") if isinstance(entry, dict) else "") or sid,
            }
        else:
            # Az ervenytelen ertek NEM csendes 'pass': kiirjuk, kulonben egy
            # elgepeles ("hakiu_gate") eszrevetlenul kikapcsolna a kaput.
            print("  [warn] source_policy: ervenytelen ertek '{}' ({}) — 'pass' lesz".format(
                value, sid))

    _CACHE["path"] = str(path)
    return _CACHE


def policy_for(source_id):
    """A forrashoz tartozo allapot. Ismeretlen forras -> alapertelmezes."""
    cfg = load()
    entry = cfg["policies"].get(source_id)
    return entry["policy"] if entry else cfg["default"]


def name_for(source_id):
    cfg = load()
    entry = cfg["policies"].get(source_id)
    return entry["name"] if entry else source_id


def describe():
    """Egysoros osszegzes a futas elejere — lassek, mi van ervenyben."""
    cfg = load()
    if not cfg["path"]:
        return "forras-policy: nincs config fajl, minden forras 'pass'"
    counts = {}
    for entry in cfg["policies"].values():
        counts[entry["policy"]] = counts.get(entry["policy"], 0) + 1
    parts = ", ".join("{}={}".format(k, counts[k]) for k in sorted(counts))
    return "forras-policy: {} ({}; alapertelmezes: {})".format(
        cfg["path"], parts or "nincs bejegyzes", cfg["default"])


# ---------------------------------------------------------------------------

def self_test():
    ok = [True]

    def check(label, cond):
        print("  {} {}".format("OK  " if cond else "BUKO", label))
        if not cond:
            ok[0] = False

    import tempfile

    cfg = {
        "default": "pass",
        "policies": {
            "SRC-DROP": {"policy": "drop", "name": "Dobando"},
            "SRC-GATE": {"policy": "haiku_gate", "name": "Kapuzott"},
            "SRC-BAD": {"policy": "hakiu_gate", "name": "Elgepelt"},
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(cfg, fh)
        tmp = fh.name

    os.environ["UAV_SOURCE_POLICY"] = tmp
    load(force=True)

    check("a drop ervenyesul", policy_for("SRC-DROP") == DROP)
    check("a haiku_gate ervenyesul", policy_for("SRC-GATE") == HAIKU_GATE)
    check("az ISMERETLEN forras alapertelmezetten atmegy",
          policy_for("SRC-SOHA-NEM-LATOTT") == PASS)
    check("az ELGEPELT ertek nem kapcsol ki kaput csendben",
          policy_for("SRC-BAD") == PASS)
    check("a nev visszakereshato", name_for("SRC-DROP") == "Dobando")
    check("a leiras emliti a fajlt", tmp in describe())

    # Hianyzo fajl -> minden pass.
    os.environ["UAV_SOURCE_POLICY"] = tmp + ".nincs"
    load(force=True)
    check("hianyzo config eseten minden forras atmegy",
          policy_for("SRC-DROP") == PASS)

    os.environ.pop("UAV_SOURCE_POLICY", None)
    os.unlink(tmp)

    print("\nSELF-TEST: {}".format("MINDEN RENDBEN" if ok[0] else "VAN BUKOTT ELLENORZES"))
    return 0 if ok[0] else 1


if __name__ == "__main__":
    import sys
    sys.exit(self_test())
