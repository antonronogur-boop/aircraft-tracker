# -*- coding: utf-8 -*-
"""reconcile_programmes.py — a meglevo esemenyallomany programme-retegbe kotese.

MIT TESZ
--------
1. Ujraillesztes: minden esemeny type_id-jat ujraszamolja az uj, hatar-tudatos
   matcherrel, es JELZI, ahol a korabbi ertek hibas volt. (Itt derul ki az
   A-100LL -> A-10 tipusu hiba a mar felhalmozott adatban.)
2. Programme-kotes: minden esemenyt hozzarendel egy tartos programhoz, vagy
   ujat javasol.
3. Allapotfelepites: a programok kanonikus darabszamat, eletciklusat es
   idorendjet az esemenyekbol epiti fel — IDORENDBEN, felulirasos logikaval,
   NEM osszegzessel.
4. Baseline-delta: minden esemenyre kiszamolja, hogy szabad-e egyaltalan
   mozgatnia az on_order allomanyt (alapertelmezesben nem).
5. Duplikatum-jelzes: a gyanus programparokat kiirja EMBERI dontesre.

ALAPERTELMEZESBEN DRY RUN. Semmit nem ir, csak jelentest keszit.

    python scripts/reconcile_programmes.py              # dry run (default)
    python scripts/reconcile_programmes.py --report      # + JSON riport fajlba
    python scripts/reconcile_programmes.py --write       # tenyleges iras
    python scripts/reconcile_programmes.py --write --only-programmes
                                                        # csak a programtabla

A --write MODOT CSAK A DRY RUN ATNEZESE UTAN hasznald. A tipus-ujraillesztes
kulon kapcsolo ala esik (--fix-types), mert az a MEGLEVO adatot valtoztatja:

    python scripts/reconcile_programmes.py --write --fix-types

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import supabase_client as db  # noqa: E402
import ac_match  # noqa: E402
import ac_programmes as acprog  # noqa: E402
import ac_intel  # noqa: E402


def load_all():
    types = db.select("ac_aircraft_types",
                      {"select": "type_id,name,designation,aliases,category"})
    countries = db.select("ac_countries", {"select": "country_id,name,aliases"})
    events = db.select("ac_events", {
        "select": "*", "review_status": "neq.rejected",
        "order": "event_date.asc"})
    try:
        programmes = db.select("ac_programmes", {"select": "*"})
    except Exception as exc:  # noqa: BLE001
        print("[fatal] ac_programmes not found — run "
              "supabase/add_programme_layer.sql first.\n  {}".format(
                  str(exc)[:200]))
        raise SystemExit(2)
    return types, countries, events, programmes


def rematch_types(events, types):
    """A tipus-illesztes ujraszamolasa. Csak JELEZ, nem ir."""
    idx = ac_match.build_index(types, "type_id",
                              name_keys=("name", "designation"))
    family_idx = {}
    for t in types:
        fam = ac_match.designation_family(t["type_id"])
        if fam and fam not in family_idx:
            family_idx[fam] = t["type_id"]
    names = {t["type_id"]: t.get("name") for t in types}

    changes, variants, unresolved = [], [], []
    for e in events:
        raw = (e.get("unresolved_type_name")
               or e.get("variant_raw")
               or names.get(e.get("type_id") or ""))
        if not raw:
            continue
        new_id, variant, kind = ac_match.match_type(raw, idx, family_idx)
        old_id = e.get("type_id")
        if new_id != old_id:
            changes.append({
                "event_id": e.get("event_id"),
                "source_text": raw,
                "old_type_id": old_id, "old_name": names.get(old_id or ""),
                "new_type_id": new_id, "new_name": names.get(new_id or ""),
                "match_kind": kind,
                "summary": str(e.get("summary") or "")[:110],
                # Ez a mezo mondja meg, hogy a KORABBI ertek volt-e hibas.
                "verdict": ("previous mapping was a digit-prefix collision"
                            if old_id and new_id is None
                            and ac_match.designation_family(raw)
                            != ac_match.designation_family(old_id)
                            else "mapping differs — review"),
            })
        if variant and not e.get("variant_raw"):
            variants.append({"event_id": e.get("event_id"),
                             "variant_raw": variant, "type_id": new_id,
                             "match_kind": kind})
        if new_id is None:
            unresolved.append({"event_id": e.get("event_id"),
                               "source_text": raw})
    return changes, variants, unresolved


def build_programme_state(events, programmes):
    """A programok allapotanak felepitese az esemenyekbol, IDORENDBEN.

    A sorrend kritikus: a kanonikus darabszam felulirasos logikaval all ossze,
    tehat a kesobbi, erosebb evidencia nyer. Ha visszafele mennenk, a legregibb
    sajtobecsles maradna a vegen.
    """
    by_id = {p.get("programme_id"): dict(p) for p in programmes}
    proposed = {}
    links, deltas, changelog = [], [], defaultdict(list)

    def sort_key(e):
        d = ac_intel.effective_day(e)
        return (d or datetime(1900, 1, 1), e.get("event_id") or 0)

    for e in sorted(events, key=sort_key):
        probe = dict(e)
        prog, why = acprog.find_programme(probe, list(by_id.values()),
                                         e.get("summary"))
        if prog is None:
            if not (e.get("country_id") and e.get("type_id")):
                continue
            kind = acprog.kind_from_event(probe, e.get("summary"))
            d = ac_intel.effective_day(e)
            key = acprog.programme_key(
                e.get("country_id"), e.get("type_id"),
                e.get("variant_raw"), e.get("service"), kind,
                d.year if d else None)
            prog = {
                "programme_id": key, "country_id": e.get("country_id"),
                "type_id": e.get("type_id"), "variant": e.get("variant_raw"),
                "service": e.get("service"), "programme_kind": kind,
                "title": "{} {}{}".format(
                    (e.get("country_id") or "?").upper(),
                    e.get("variant_raw") or e.get("type_id") or "?",
                    "" if kind == "acquisition" else " ({})".format(
                        acprog.PROGRAMME_KINDS.get(kind, kind))),
                "review_status": "active", "evidence_count": 0,
                "canonical_quantity": None, "lifecycle_stage": None,
                "claim_history": [], "superseded_quantities": [],
            }
            by_id[key] = prog
            proposed[key] = prog

        pid = prog["programme_id"]
        links.append({"event_id": e.get("event_id"), "programme_id": pid,
                      "basis": why})

        # A baseline-delta a program AKKORI allapota alapjan.
        delta, dwhy = acprog.on_order_delta(probe, prog, e.get("summary"))
        deltas.append({"event_id": e.get("event_id"), "programme_id": pid,
                       "on_order_delta": delta, "reason": dwhy})

        patch, changes = acprog.apply_event(
            prog, probe, e.get("summary"), e.get("article_id"))
        prog.update(patch)
        for c in changes:
            if not c.startswith("no state change"):
                changelog[pid].append({"event_id": e.get("event_id"),
                                       "change": c})
    return by_id, proposed, links, deltas, changelog


def main(argv):
    write = "--write" in argv
    fix_types = "--fix-types" in argv
    only_programmes = "--only-programmes" in argv
    want_report = "--report" in argv or not write

    print("=" * 74)
    print("PROGRAMME RECONCILIATION — {}".format(
        "WRITE MODE" if write else "DRY RUN (nothing will be written)"))
    print("=" * 74)

    types, countries, events, programmes = load_all()
    print("\nLoaded: {} types, {} countries, {} events, {} programmes".format(
        len(types), len(countries), len(events), len(programmes)))

    # ---------------- 1. tipus-ujraillesztes ----------------
    print("\n" + "-" * 74)
    print("1. ENTITY RE-MATCHING (the A-100LL -> A-10 class of defect)")
    print("-" * 74)
    changes, variants, unresolved = rematch_types(events, types)
    if not changes:
        print("  No type mapping would change.")
    else:
        print("  {} event(s) map differently under the boundary-aware "
              "matcher:".format(len(changes)))
        for c in changes[:25]:
            print("    event {:>6}  {!r}".format(
                c["event_id"], c["source_text"][:38]))
            print("               was: {!s:<12} ({})".format(
                c["old_type_id"], c["old_name"]))
            print("               now: {!s:<12} ({})  [{}]".format(
                c["new_type_id"], c["new_name"], c["match_kind"]))
        if len(changes) > 25:
            print("    ... and {} more (see the JSON report)".format(
                len(changes) - 25))
    print("  {} event(s) would gain a variant designation.".format(
        len(variants)))
    print("  {} event(s) resolve to no catalogue type (go to review rather "
          "than a wrong FK).".format(len(unresolved)))

    # ---------------- 2. programme-allapot ----------------
    print("\n" + "-" * 74)
    print("2. PROGRAMME STATE (built in date order, superseding not summing)")
    print("-" * 74)
    by_id, proposed, links, deltas, changelog = build_programme_state(
        events, programmes)
    print("  {} programme(s) in the register ({} newly proposed).".format(
        len(by_id), len(proposed)))
    print("  {} event(s) linked to a programme.".format(len(links)))

    moving = [d for d in deltas if d["on_order_delta"]]
    print("\n  Baseline movement: {} of {} events may move on-order.".format(
        len(moving), len(deltas)))
    print("  The remaining {} are restatements, unconfirmed claims or "
          "non-contracted stages.".format(len(deltas) - len(moving)))
    for d in moving[:12]:
        print("    event {:>6} / {:<28} {:+d}".format(
            d["event_id"], d["programme_id"][:27], d["on_order_delta"]))

    # A legtobb evidenciat vonzo programok — itt lattszik a duplikacio.
    busiest = sorted(by_id.values(),
                     key=lambda p: -(p.get("evidence_count") or 0))[:10]
    print("\n  Programmes with the most evidence attached:")
    for p in busiest:
        if not p.get("evidence_count"):
            continue
        print("    {:<34} qty={!s:<6} basis={!s:<9} stage={!s:<16} n={}".format(
            (p.get("programme_id") or "")[:33],
            p.get("canonical_quantity"), p.get("quantity_basis"),
            p.get("lifecycle_stage"), p.get("evidence_count")))
        for h in (p.get("superseded_quantities") or [])[:3]:
            print("        superseded: {} ({}) on {}".format(
                h.get("quantity"), h.get("basis"), h.get("superseded_at")))

    # ---------------- 3. duplikatum-jelzes ----------------
    print("\n" + "-" * 74)
    print("3. DUPLICATE PROGRAMMES (flagged for the analyst, never auto-merged)")
    print("-" * 74)
    dups = acprog.merge_candidates(
        [p for p in by_id.values()
         if p.get("review_status") in (None, "active")])
    if not dups:
        print("  None detected.")
    for d in dups[:20]:
        print("    {:<30} <-> {:<30}".format(d["a"][:29], d["b"][:29]))
        print("        {} vs {} aircraft; {} / {}".format(
            d["a_quantity"], d["b_quantity"], d["a_stage"], d["b_stage"]))

    report = {
        "generated_utc": datetime.utcnow().isoformat(),
        "mode": "write" if write else "dry_run",
        "counts": {
            "events": len(events), "programmes_existing": len(programmes),
            "programmes_after": len(by_id), "programmes_proposed": len(proposed),
            "type_mapping_changes": len(changes),
            "variants_detected": len(variants),
            "unresolved_types": len(unresolved),
            "events_moving_baseline": len(moving),
            "duplicate_pairs": len(dups),
        },
        "type_mapping_changes": changes,
        "variants_detected": variants,
        "unresolved_types": unresolved,
        "programmes": [{k: v for k, v in p.items() if not k.startswith("_")}
                       for p in by_id.values()],
        "event_links": links,
        "baseline_deltas": deltas,
        "duplicate_pairs": dups,
        "changelog": {k: v for k, v in changelog.items()},
    }
    if want_report:
        out = HERE.parent / "data" / "reconcile_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 default=str), encoding="utf-8")
        print("\nFull JSON report: {}".format(out))

    if not write:
        print("\n" + "=" * 74)
        print("DRY RUN COMPLETE — nothing was written.")
        print("Review the report, then re-run with --write (add --fix-types to")
        print("also correct the type_id mappings listed in section 1).")
        print("=" * 74)
        return 0

    # ================= WRITE =================
    print("\n" + "=" * 74)
    print("WRITING")
    print("=" * 74)
    run = db.start_run("ac_reconcile_fleets")
    try:
        rows = []
        for p in by_id.values():
            row = {k: v for k, v in p.items()
                   if not k.startswith("_") and k not in ("created_at",)}
            row["updated_at"] = datetime.utcnow().isoformat()
            rows.append(row)
        for i in range(0, len(rows), 100):
            db.upsert("ac_programmes", rows[i:i + 100], "programme_id")
        print("  {} programme(s) upserted.".format(len(rows)))

        if not only_programmes:
            link_by_event = {l["event_id"]: l["programme_id"] for l in links}
            delta_by_event = {d["event_id"]: d for d in deltas}
            var_by_event = {v["event_id"]: v for v in variants}
            type_by_event = {c["event_id"]: c for c in changes} if fix_types \
                else {}
            n = 0
            for e in events:
                eid = e.get("event_id")
                patch = {}
                if eid in link_by_event:
                    patch["programme_id"] = link_by_event[eid]
                if eid in delta_by_event:
                    patch["on_order_delta"] = delta_by_event[eid][
                        "on_order_delta"]
                if e.get("quantity_claimed") in (None, "") \
                        and e.get("quantity") is not None:
                    patch["quantity_claimed"] = e.get("quantity")
                if eid in var_by_event:
                    patch["variant_raw"] = var_by_event[eid]["variant_raw"]
                    patch["type_match_kind"] = var_by_event[eid]["match_kind"]
                if eid in type_by_event:
                    patch["type_id"] = type_by_event[eid]["new_type_id"]
                    patch["type_match_kind"] = type_by_event[eid]["match_kind"]
                    if type_by_event[eid]["new_type_id"] is None:
                        patch["unresolved_type_name"] = \
                            type_by_event[eid]["source_text"]
                if not patch:
                    continue
                db.update("ac_events", {"event_id": "eq.{}".format(eid)}, patch)
                n += 1
            print("  {} event(s) updated{}.".format(
                n, " (including type_id corrections)" if fix_types else ""))
        db.finish_run(run, "success", items_processed=len(rows))
        print("\nDone. Regenerate the weekly report to see the corrected "
              "baseline.")
    except Exception as exc:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(exc))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
