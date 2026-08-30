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
import re
import sys
import urllib.error
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import supabase_client as db  # noqa: E402
import ac_match  # noqa: E402
import ac_programmes as acprog  # noqa: E402
import ac_intel  # noqa: E402


# --------------------------------------------------------------------------
# SEMA-TOLERANS IRAS
# --------------------------------------------------------------------------
#
# Az elso eles --write futas nyers tracebackkel allt le:
#
#     urllib.error.HTTPError: HTTP Error 400: Bad Request
#
# Az ok: a sema egy KORABBI migracio-verzion allt, es nem ismerte a
# contracted_quantity / planned_quantity / quantity_conflicts oszlopokat.
# Ez ket kulon hiba volt: (1) a szkript nem mondta meg, mi a baj;
# (2) az egesz muvelet elbukott egy hianyzo oszlop miatt.
#
# Ezert az iras mostantol TOLERANS: a PostgREST megnevezi a nem talalt
# oszlopot, azt kivesszuk, es ujraprobaljuk. Amit ki kellett hagyni, azt
# kiirjuk — igy az iras akkor is atmegy, ha a migracio meg nem futott le,
# es latszik, mit nyerne a felhasznalo a futtatasaval.

# Az ac_programmes irasi alakja. Minden sor EZEKET a kulcsokat kapja, ebben a
# sorrendben — igy a PostgREST bulk-insert kulcs-egyezesi elvarasa mindig
# teljesul, fuggetlenul attol, mely program milyen mezoket allitott be.
PROGRAMME_COLUMNS = [
    "programme_id", "country_id", "type_id", "variant", "service",
    "programme_kind", "title", "review_status", "merged_into",
    # darabszam — ket kulon mertek + a szarmaztatott fejszam
    "contracted_quantity", "contracted_basis", "contracted_as_of",
    "planned_quantity", "planned_basis", "planned_as_of",
    "canonical_quantity", "canonical_source", "quantity_basis",
    "quantity_as_of",
    # allapot
    "lifecycle_stage", "contract_date", "contract_evidence",
    # kepesseg-idorend
    "first_delivery_year", "delivery_start_year", "delivery_end_year",
    "ioc_year", "foc_year", "meaningful_scale_year",
    # ertek
    "value_usd_m", "value_type", "value_currency_year",
    # evidencia
    "confidence", "independent_lineages", "first_reported_at",
    "last_evidence_at", "evidence_count",
    # tortenet (jsonb)
    "claim_history", "superseded_quantities", "quantity_conflicts",
    "observed_quantities", "status_note",
]

# A NOT NULL oszlopok ertelmes alapertekei.
#
# A kulcs-normalizalas bevezetese utan MINDEN sor minden kulcsot megkapta —
# a hianyzokat None-nal. Ez viszont ELRONTOTTA a NOT NULL oszlopokat: korabban
# a kulcs egyszeruen nem volt jelen, es az adatbazis-default ervenyesult; a
# kifejezett NULL felulirja a defaultot:
#
#     23502  Failing row contains (pol-f35-2020, ..., null, ...)
#
# A NOT NULL oszlopokat a supabase/add_programme_layer.sql definialja:
#   title (default NINCS), programme_kind, independent_lineages, evidence_count
# A test_programme_write.py ezt a listat a MIGRACIOS FAJLBOL olvassa vissza,
# hogy egy uj NOT NULL oszlop se maradhasson le rola.
PROGRAMME_NOT_NULL_DEFAULTS = {
    "programme_kind": "acquisition",
    "independent_lineages": 1,
    "evidence_count": 0,
    "review_status": "active",
    # A title-nek NINCS adatbazis-defaultja, tehat mindig kell ertek.
    "title": None,          # kulon kezelve: programme_id a vegso fallback
    # jsonb oszlopok: ures lista, nem NULL — igy a kesobbi olvasas egyszerubb
    "claim_history": [],
    "superseded_quantities": [],
    "quantity_conflicts": [],
    "observed_quantities": [],
}


def apply_not_null_defaults(row):
    """A NOT NULL oszlopok kitoltese, hogy a kifejezett NULL ne bukjon el."""
    for col, default in PROGRAMME_NOT_NULL_DEFAULTS.items():
        if col not in row:
            continue
        if row[col] in (None, ""):
            row[col] = ([] if isinstance(default, list) else default)
    if not row.get("title"):
        row["title"] = row.get("programme_id") or "unnamed programme"
    return row


_UNKNOWN_COL_RX = re.compile(
    r"'([A-Za-z_][A-Za-z0-9_]*)'\s+column|column\s+\"?([A-Za-z_][A-Za-z0-9_]*)\"?"
    r"\s+of\s+relation|Could not find the '([A-Za-z_][A-Za-z0-9_]*)'")


def _error_body(exc):
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _unknown_column(body):
    m = _UNKNOWN_COL_RX.search(body or "")
    if not m:
        return None
    return next((g for g in m.groups() if g), None)


def build_programme_rows(programmes, stamp=None):
    """A programme-rekordok ATALAKITASA irasra kesz sorokka.

    Kulon fuggveny, hogy a teszt (scripts/test_programme_write.py) PONTOSAN ezt
    a kodot futtassa valodi PostgreSQL ellen, ne egy kozelitest.

    Harom kenyszer teljesul egyszerre:
      1. minden sor UGYANAZT a kulcskeszletet kapja  (PostgREST PGRST102)
      2. a NOT NULL oszlopok sosem kapnak NULL-t     (Postgres 23502)
      3. a listan kivuli mezok is atmennek           (tolerans upsert szuri)
    """
    stamp = stamp or datetime.utcnow().isoformat()
    rows = []
    for p in programmes:
        row = {c: p.get(c) for c in PROGRAMME_COLUMNS}
        row["programme_id"] = p.get("programme_id")
        row["updated_at"] = stamp
        for k, v in p.items():
            if not k.startswith("_") and k not in row and k != "created_at":
                row[k] = v
        apply_not_null_defaults(row)
        rows.append(row)
    rows, _keys = normalise_keys(rows)
    # A normalizalas UTAN ujra: az unio uj kulcsokat vihetett be None-nal.
    for r in rows:
        apply_not_null_defaults(r)
    return rows


def normalise_keys(rows):
    """MINDEN sor UGYANAZT a kulcskeszletet kapja.

    A PostgREST bulk-insert kotelezo elvarasa:

        PGRST102: "All object keys must match"

    A programme-rekordok kulcsai termeszetesen elternek — az egyiknek van
    contracted_quantity, a masiknak csak planned_quantity, a harmadiknak
    superseded_quantities. Igy epitve a batch elbukik.

    A megoldas a kulcsok UNIOJA, a hianyzokat None-nal kitoltve. Ez nem
    veszit adatot: a rekordokat a teljes szamolt allapotbol epitjuk, tehat a
    None valoban azt jelenti, hogy az ertek nem ismert.
    """
    rows = [dict(r) for r in rows]
    keys = set()
    for r in rows:
        keys.update(r.keys())
    for r in rows:
        for k in keys:
            r.setdefault(k, None)
    return rows, sorted(keys)


def tolerant_upsert(table, rows, conflict_column, label=""):
    """Upsert, amely a sema hianyzo oszlopait kihagyja ahelyett, hogy elbukna.

    Visszaad: (siker, kihagyott_oszlopok)
    """
    dropped = []
    # A kulcs-egyseges alak MEG A KULDES ELOTT — kulonben a PostgREST a
    # hianyzo oszlop helyett kulcs-eltéresre panaszkodik, es a tolerans
    # oszlop-elhagyas nem tud mit kezdeni vele.
    work, _keys = normalise_keys(rows)
    for _ in range(24):
        try:
            db.upsert(table, work, conflict_column)
            return True, dropped
        except urllib.error.HTTPError as exc:
            body = _error_body(exc)
            # Kulcs-eltéres: ujranormalizalunk es ujraprobalunk egyszer.
            if "PGRST102" in (body or "") or "object keys must match" in (
                    body or ""):
                fixed, _k = normalise_keys(work)
                if [sorted(r) for r in fixed] != [sorted(r) for r in work]:
                    work = fixed
                    print("  [schema] key sets differed across rows — "
                          "normalised and retrying")
                    continue
                print("  [ERROR] {} upsert failed ({}): {}".format(
                    table, exc.code, (body or str(exc))[:300]))
                return False, dropped
            col = _unknown_column(body)
            if col is None or all(col not in r for r in work):
                print("  [ERROR] {} upsert failed ({}): {}".format(
                    table, exc.code, (body or str(exc))[:400]))
                return False, dropped
            dropped.append(col)
            for r in work:
                r.pop(col, None)
            print("  [schema] '{}' not present on {} — retrying without it"
                  .format(col, table))
    print("  [ERROR] {} upsert still failing after dropping {}".format(
        table, dropped))
    return False, dropped


def tolerant_update(table, filters, patch):
    """Ugyanaz PATCH-re. Visszaad: (siker, kihagyott_oszlopok)"""
    dropped, work = [], dict(patch)
    for _ in range(12):
        if not work:
            return True, dropped
        try:
            db.update(table, filters, work)
            return True, dropped
        except urllib.error.HTTPError as exc:
            body = _error_body(exc)
            col = _unknown_column(body)
            if col is None or col not in work:
                return False, dropped
            dropped.append(col)
            work.pop(col, None)
    return False, dropped


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


def apply_detected_variants(events, variants):
    """A section 1-ben FELDERITETT variansokat mar a dry run alatt alkalmazzuk.

    Enelkul a dry run nem elorejelzo: a programme-felbontas variansok NELKUL
    keszul, es minden F-35A/B/C esemeny egy 'usa-f35' programba esik — pedig
    az iras utan (amikor a variant_raw bekerul) mar szetvalna. A dry runnak azt
    kell megmutatnia, ami a --write UTAN tenylegesen lesz.
    """
    by_id = {v["event_id"]: v for v in variants}
    n = 0
    for e in events:
        v = by_id.get(e.get("event_id"))
        if v and not e.get("variant_raw"):
            e["variant_raw"] = v["variant_raw"]
            e["type_match_kind"] = v.get("match_kind")
            n += 1
    return n


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

    # A felderitett variansokat MAR ITT alkalmazzuk, hogy a programme-felbontas
    # azt tukrozze, ami az iras utan tenylegesen lesz (F-35A / F-35B / F-35C
    # kulon program, nem egy kozos 'usa-f35').
    applied_v = apply_detected_variants(events, variants)
    if applied_v:
        print("  -> {} variant(s) applied in-memory so the programme split "
              "below reflects the post-write state.".format(applied_v))

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
    # A programfajtak megoszlasa. Az 'attrition' sorok NEM beszerzesek: azok
    # vesztesegek, amelyek korabban beszerzesi programot hoztak letre es
    # allitottak be a "kanonikus darabszamot" egy lezuhant gepbol.
    kinds = defaultdict(int)
    for p in by_id.values():
        kinds[p.get("programme_kind") or "acquisition"] += 1
    print("\n  By programme kind:")
    for k, n in sorted(kinds.items(), key=lambda x: -x[1]):
        print("    {:<18} {}".format(k, n))

    busiest = sorted(by_id.values(),
                     key=lambda p: -(p.get("evidence_count") or 0))[:12]
    print("\n  Programmes with the most evidence attached:")
    for p in busiest:
        if not p.get("evidence_count"):
            continue
        print("    {:<32} [{:<15}] qty={!s:<6} basis={!s:<9} stage={!s:<18} "
              "n={}".format(
                  (p.get("programme_id") or "")[:31],
                  (p.get("programme_kind") or "")[:15],
                  p.get("canonical_quantity"), p.get("quantity_basis"),
                  p.get("lifecycle_stage"), p.get("evidence_count")))
        for h in (p.get("superseded_quantities") or [])[:3]:
            print("        superseded: {} ({})".format(
                h.get("quantity"), h.get("basis")))
        for c in (p.get("quantity_conflicts") or [])[:3]:
            print("        CONFLICT: {} ({}) vs recorded {} — kept the "
                  "recorded value".format(
                      c.get("quantity"), c.get("basis"), c.get("against")))

    # A darabszam-konfliktusok kulon listaja: EZ az, amit elemzoi szemmel
    # at kell nezni, mert itt ket forras mast allit a program mereterol.
    conflicts = [(p.get("programme_id"), c)
                 for p in by_id.values()
                 for c in (p.get("quantity_conflicts") or [])]
    print("\n  Quantity conflicts needing an analyst decision: {}".format(
        len(conflicts)))
    for pid, c in conflicts[:15]:
        print("    {:<30} claims {!s:<6} against recorded {!s:<6} ({})".format
              (str(pid)[:29], c.get("quantity"), c.get("against"),
               c.get("basis")))

    no_qty = [p for p in by_id.values()
              if (p.get("programme_kind") or "acquisition") == "acquisition"
              and p.get("canonical_quantity") is None
              and (p.get("evidence_count") or 0) >= 2]
    if no_qty:
        print("\n  Acquisition programmes with no established size ({}) — the "
              "reporting never stated a programme total:".format(len(no_qty)))
        for p in no_qty[:10]:
            print("    {:<32} n={}".format(
                (p.get("programme_id") or "")[:31], p.get("evidence_count")))

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
        "programme_kinds": dict(kinds),
        "quantity_conflicts": [{"programme_id": pid, **c}
                               for pid, c in conflicts],
        "acquisitions_without_size": [p.get("programme_id") for p in no_qty],
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
        rows = build_programme_rows(by_id.values())
        all_dropped, ok_all = set(), True
        for i in range(0, len(rows), 100):
            ok, dropped = tolerant_upsert(
                "ac_programmes", rows[i:i + 100], "programme_id")
            all_dropped.update(dropped)
            ok_all = ok_all and ok
        if not ok_all:
            raise SystemExit(
                "\n  Programme write failed. See the error above.\n"
                "  If it names a missing column, re-run\n"
                "  supabase/add_programme_layer.sql in the Supabase SQL editor.")
        print("  {} programme(s) upserted.".format(len(rows)))
        if all_dropped:
            print("\n  [schema notice] These columns are not yet in your "
                  "ac_programmes table, so their values were NOT stored:")
            for c in sorted(all_dropped):
                print("     - {}".format(c))
            print("  Re-run supabase/add_programme_layer.sql to add them, then\n"
                  "  re-run this script to store the full programme state.")

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
                ok, dropped = tolerant_update(
                    "ac_events", {"event_id": "eq.{}".format(eid)}, patch)
                if dropped:
                    all_dropped.update(dropped)
                if ok:
                    n += 1
            print("  {} event(s) updated{}.".format(
                n, " (including type_id corrections)" if fix_types else ""))
            if all_dropped:
                print("  [schema notice] columns skipped: {}".format(
                    ", ".join(sorted(all_dropped))))
        db.finish_run(run, "success", items_processed=len(rows))
        print("\nDone. Regenerate the weekly report to see the corrected "
              "baseline.")
    except Exception as exc:  # noqa: BLE001
        db.finish_run(run, "error", error_message=str(exc))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
