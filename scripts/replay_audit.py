# -*- coding: utf-8 -*-
"""replay_audit.py — a programme-reteg TELJES ujrajatszasa offline adaton.

Ez a fejlesztoi eszkoz. Nem resze a heti pipeline-nak.

Ket bemenetet fogad, ebben a sorrendben:
  1. data/events_export.json      (scripts/export_for_review.py kimenete) — hu
  2. data/reconcile_report.json   (rekonstrualt, ha az export nincs meg)

Kiirja MINDEN program vegallapotat es a dontesek indoklasat, hogy a logika
korlatlanul iteralhato legyen eles futtatas nelkul.

    python scripts/replay_audit.py                 # osszefoglalo
    python scripts/replay_audit.py --full          # minden program
    python scripts/replay_audit.py --suspect       # csak a gyanus esetek
    python scripts/replay_audit.py <programme_id>  # egy program reszletei
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ac_match  # noqa: E402
import ac_programmes as acprog  # noqa: E402

DATA = HERE.parent / "data"


# --------------------------------------------------------------------------
# Bemenet
# --------------------------------------------------------------------------

def load_events():
    """(events, types, countries, source_label)"""
    exp = DATA / "events_export.json"
    if exp.exists():
        raw = json.loads(exp.read_text(encoding="utf-8"))
        return (raw.get("ac_events") or [],
                raw.get("ac_aircraft_types") or [],
                raw.get("ac_countries") or [],
                "events_export.json (faithful)")

    # Rekonstrukcio a reconcile riportbol. Az event_type nincs benne, ezert a
    # stadiumot a claim_history 'stage' mezoje adja, es ahol az ures, a
    # szovegbol becsuljuk. A rekonstrukcio JELZETT.
    rep = DATA / "reconcile_report.json"
    if not rep.exists():
        raise SystemExit(
            "Neither data/events_export.json nor data/reconcile_report.json "
            "is present. Run scripts/export_for_review.py first.")
    raw = json.loads(rep.read_text(encoding="utf-8"))
    events = []
    for pr in raw.get("programmes") or []:
        for h in (pr.get("claim_history") or []):
            events.append({
                "event_id": None,
                "article_id": h.get("article_id"),
                "country_id": pr.get("country_id"),
                "type_id": pr.get("type_id"),
                "variant_raw": pr.get("variant"),
                "service": pr.get("service"),
                "lifecycle_stage": h.get("stage"),
                "event_type": _guess_event_type(h.get("note") or "",
                                                h.get("stage")),
                "quantity": h.get("quantity"),
                "event_date": h.get("as_of"),
                "evidence_kind": h.get("evidence_kind"),
                "summary": h.get("note") or "",
                "_reconstructed": True,
            })
    return (events, [], [], "reconcile_report.json (reconstructed — "
            "event_type inferred, summaries truncated to 180 chars)")


_TYPE_HINTS = (
    ("incident", ("crash", "destroyed", "was lost", "were lost", "shot down",
                  "written off", "total loss", "mishap")),
    ("retirement", ("retire", "withdraw", "out of service", "boneyard",
                    "final flight", "divest")),
    ("delivery", ("received", "delivered", "handed over", "took delivery",
                  "arrived", "first flight", "entered service")),
    ("upgrade", ("upgrade", "modernis", "moderniz", "retrofit", "convert",
                 "slep", "service life extension")),
    ("order", ("signed a", "signed the", "contract", "awarded", "ordered",
               "order for", "procure", "purchase")),
    ("selection", ("selected", "shortlist", "downselect", "chose", "picked")),
    ("negotiation", ("negotiat", "talks", "letter of intent", "memorandum",
                     "interest", "request for information", "rfi", "plans to",
                     "considering", "cleared", "approved", "authoris",
                     "authoriz")),
)


def _guess_event_type(text, stage):
    if stage:
        rev = {"contract_signed": "order", "production": "order",
               "delivery": "delivery", "ioc": "delivery", "foc": "delivery",
               "upgrade_programme": "upgrade", "retirement": "retirement",
               "loss": "incident", "selection": "selection"}
        if stage in rev:
            return rev[stage]
        return "negotiation"
    low = (text or "").lower()
    for etype, needles in _TYPE_HINTS:
        if any(n in low for n in needles):
            return etype
    return "other"


# --------------------------------------------------------------------------
# Ujrajatszas
# --------------------------------------------------------------------------

def _day(e):
    import re
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(e.get("event_date") or ""))
    if not m:
        return datetime(1900, 1, 1)
    try:
        return datetime(*map(int, m.groups()))
    except ValueError:
        return datetime(1900, 1, 1)


def replay(events, types):
    idx = ac_match.build_index(types, "type_id",
                              name_keys=("name", "designation")) if types else {}
    fam = {}
    for t in (types or []):
        f = ac_match.designation_family(t["type_id"])
        if f and f not in fam:
            fam[f] = t["type_id"]

    by_id, decisions = {}, defaultdict(list)
    for e in sorted(events, key=lambda x: (_day(x), x.get("event_id") or 0)):
        # Varians felderitese, ha van katalogus.
        if idx and not e.get("variant_raw"):
            src = e.get("unresolved_type_name") or ""
            if src:
                tid, var, kind = ac_match.match_type(src, idx, fam)
                if var:
                    e["variant_raw"] = var
                    e["type_match_kind"] = kind

        prog, why = acprog.find_programme(e, list(by_id.values()),
                                         e.get("summary"))
        if prog is None:
            if not (e.get("country_id") and e.get("type_id")):
                continue
            kind = acprog.kind_from_event(e, e.get("summary"))
            d = _day(e)
            key = acprog.programme_key(
                e["country_id"], e["type_id"], e.get("variant_raw"),
                e.get("service"), kind, d.year if d.year > 1900 else None)
            prog = {"programme_id": key, "country_id": e["country_id"],
                    "type_id": e["type_id"], "variant": e.get("variant_raw"),
                    "service": e.get("service"), "programme_kind": kind,
                    "review_status": "active", "evidence_count": 0,
                    "claim_history": [], "superseded_quantities": [],
                    "title": key}
            by_id[key] = prog
        pid = prog["programme_id"]

        scope, scope_why = acprog.quantity_scope(e, e.get("summary"))
        delta, dwhy = acprog.on_order_delta(e, prog, e.get("summary"))
        patch, changes = acprog.apply_event(prog, e, e.get("summary"),
                                           e.get("article_id"))
        prog.update(patch)
        decisions[pid].append({
            "event_id": e.get("event_id"), "qty": e.get("quantity"),
            "stage_raw": e.get("lifecycle_stage"),
            "stage_resolved": acprog.resolved_stage(e),
            "scope": scope, "scope_why": scope_why,
            "delta": delta, "delta_why": dwhy,
            "changes": changes, "summary": (e.get("summary") or "")[:150],
        })
    return by_id, decisions


# --------------------------------------------------------------------------
# Gyanujelek — amit EMBERNEK kell megneznie
# --------------------------------------------------------------------------

def suspects(by_id, decisions):
    out = []
    for pid, p in by_id.items():
        kind = p.get("programme_kind") or "acquisition"
        c, pl = p.get("contracted_quantity"), p.get("planned_quantity")
        flags = []
        # Egy MEG NEM SZERZODOTT program (RFI / RFP / requirement) jogosan nem
        # ismer darabszamot — ez nem gyanujel. A KC-135 console-refresh RFI es
        # a GCAP fejlesztesi szakasza igy adott hamis riasztast.
        pre_contract = (p.get("lifecycle_stage") or "") in (
            "", "requirement", "rfi_sources_sought", "rfp", "bid",
            "selection", "other")
        if kind == "acquisition" and c is None and pl is None \
                and not pre_contract and (p.get("evidence_count") or 0) >= 3:
            flags.append("contracted or later stage but no quantity anywhere")
        if c not in (None, "") and pl not in (None, "") and int(pl) < int(c):
            flags.append("planned total ({}) is BELOW the contracted quantity "
                         "({}) — reporting disagreement".format(pl, c))
        if p.get("quantity_conflicts"):
            flags.append("{} unresolved quantity conflict(s)".format(
                len(p["quantity_conflicts"])))
        if kind in acprog.NO_CANONICAL_QUANTITY \
                and p.get("canonical_quantity") is not None:
            flags.append("a {} programme carries a canonical size".format(kind))
        if kind == "acquisition" and p.get("lifecycle_stage") in (
                "loss", "retirement"):
            flags.append("acquisition programme sitting at stage '{}'".format(
                p.get("lifecycle_stage")))
        # Egy EGY gepes "beszerzesi program" gyakran felreolvasas — de a ketto
        # nem: a cseh ket S-70 Firehawk es a kolumbiai ket KC-390 valodi
        # szerzodes. Ezert csak az 1-et jelezzuk.
        if kind == "acquisition" and c == 1:
            flags.append("contracted quantity of 1 — verify this is not a "
                         "single-airframe event")
        big = [d for d in decisions[pid]
               if d["scope"] == "programme" and (d["qty"] or 0) > 0]
        if len(big) >= 2:
            qs = sorted({d["qty"] for d in big})
            if len(qs) >= 3:
                flags.append("{} different programme-scope figures reported: "
                             "{}".format(len(qs), qs))
        if flags:
            out.append((pid, p, flags))
    return out


def show(pid, p, decisions, indent="  "):
    print("{}{:<34} [{:<15}] contracted={!s:<6} planned={!s:<6} "
          "stage={!s:<18} n={}".format(
              indent, pid[:33], (p.get("programme_kind") or "")[:15],
              p.get("contracted_quantity"), p.get("planned_quantity"),
              p.get("lifecycle_stage"), p.get("evidence_count")))
    print("{}  reading: {}".format(indent, acprog._quantity_reading(p)))
    for d in decisions.get(pid, []):
        print("{}  qty={!s:<6} stage={:<18} scope={:<13} delta={:+d}".format(
            indent, d["qty"], d["stage_resolved"][:17], d["scope"], d["delta"]))
        print("{}    \"{}\"".format(indent, d["summary"][:118]))
        for c in d["changes"]:
            if "no state change" in c:
                continue
            print("{}    -> {}".format(indent, c[:118]))


def main(argv):
    events, types, countries, label = load_events()
    print("=" * 100)
    print("REPLAY AUDIT — source: {}".format(label))
    print("=" * 100)
    print("{} event(s)".format(len(events)))
    if not types:
        print("[note] no catalogue in the source — variant detection is "
              "skipped in this replay")

    by_id, decisions = replay(events, types)
    kinds = defaultdict(int)
    for p in by_id.values():
        kinds[p.get("programme_kind") or "acquisition"] += 1
    print("\n{} programme(s):  {}".format(
        len(by_id), "  ".join("{}={}".format(k, v)
                              for k, v in sorted(kinds.items(),
                                                 key=lambda x: -x[1]))))

    acq = [p for p in by_id.values()
           if (p.get("programme_kind") or "acquisition") == "acquisition"]
    sized = [p for p in acq if p.get("canonical_quantity") is not None]
    print("acquisitions with an established size: {}/{}".format(
        len(sized), len(acq)))
    conflicts = sum(len(p.get("quantity_conflicts") or [])
                    for p in by_id.values())
    print("unresolved quantity conflicts: {}".format(conflicts))
    moved = sum(1 for ds in decisions.values() for d in ds if d["delta"])
    print("events moving the on-order baseline: {}".format(moved))

    sus = suspects(by_id, decisions)
    print("\nSUSPECT PROGRAMMES: {}".format(len(sus)))
    for pid, p, flags in sus:
        print("  {:<34} {}".format(pid[:33], "; ".join(flags)[:100]))

    args = [a for a in argv if not a.startswith("--")]
    if args:
        for pid in args:
            print("\n" + "=" * 100)
            if pid in by_id:
                show(pid, by_id[pid], decisions)
            else:
                near = [k for k in by_id if pid in k]
                print("no exact match; near: {}".format(near[:10]))
    elif "--suspect" in argv:
        print()
        for pid, p, flags in sus:
            print("=" * 100)
            show(pid, p, decisions)
    elif "--full" in argv:
        print()
        for pid in sorted(by_id):
            show(pid, by_id[pid], decisions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
