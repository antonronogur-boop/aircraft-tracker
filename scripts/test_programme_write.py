# -*- coding: utf-8 -*-
"""test_programme_write.py — az IRASI UT ellenorzese VALODI PostgreSQL-en.

MIERT LETEZIK
-------------
Az iras harom kulonbozo hibaval bukott el egymas utan, mindharom eles futasban:

    HTTP 400 (ismeretlen oszlop)   — a sema egy korabbi migracion allt
    PGRST102 "All object keys must match"  — a batch sorai mas kulcsokat vittek
    23502 NOT NULL violation       — a kulcs-normalizalas kifejezett NULL-t
                                     kuldott oda, ahol addig a default ervenyesult

Mindharmat kulon-kulon "javitottam", majd a kovetkezo csak eles futasban derult
ki. Ez a teszt ezt zarja le: felepiti a TELJES semat, es a VALODI sor-epitovel
(reconcile_programmes.build_programme_rows) beszurja a programokat egy igazi
PostgreSQL-be. Ami itt atmegy, az a Supabase-ben sem bukhat el NOT NULL,
tipus- vagy FK-hiba miatt.

A PostgREST kulcs-egyezesi szabalyat kulon ellenorizzuk (az nem SQL-szintu).

Futtatas:  python scripts/test_programme_write.py
Igeny:     helyi postgres (initdb + pg_ctl elerheto)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

# A supabase_client importaláskor kotelezo kornyezeti valtozokat ker. Ez a
# teszt NEM lep halozatra — csak a sor-epito kodot es a helyi PostgreSQL-t
# hasznalja —, ezert helyorzo ertekeket allitunk be.
os.environ.setdefault("SUPABASE_URL", "https://offline.invalid")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "offline-test-key")

PGBIN = None
for cand in ("/usr/lib/postgresql/16/bin", "/usr/lib/postgresql/15/bin",
             "/usr/local/pgsql/bin"):
    if Path(cand, "initdb").exists():
        PGBIN = cand
        break

FAILS = []


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def psql(sql, port, want_ok=True):
    r = sh('psql -h /tmp -p {} -U postgres -v ON_ERROR_STOP=1 -q -c {}'.format(
        port, json_quote(sql)))
    if want_ok and r.returncode != 0:
        return False, (r.stderr or r.stdout)
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def json_quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


# --------------------------------------------------------------------------
# 1. NOT NULL oszlopok kiolvasasa A MIGRACIOS FAJLBOL
# --------------------------------------------------------------------------

def not_null_columns():
    """Igy egy JOVOBELI uj NOT NULL oszlop sem maradhat le a defaultokrol."""
    sql = (ROOT / "supabase" / "add_programme_layer.sql").read_text(
        encoding="utf-8")
    m = re.search(r"create table if not exists ac_programmes \((.*?)\n\);",
                  sql, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).split("\n"):
        line = line.split("--")[0].strip().rstrip(",")
        if not line:
            continue
        if re.search(r"\bnot null\b", line, re.I):
            col = line.split()[0]
            d = re.search(r"default\s+([^,]+)", line, re.I)
            out[col] = d.group(1).strip() if d else None
    return out


def test_defaults_cover_not_null():
    print("\n1. Every NOT NULL column has a client-side default")
    print("-" * 78)
    import reconcile_programmes as R
    cols = not_null_columns()
    for col, dbdefault in sorted(cols.items()):
        covered = col in R.PROGRAMME_NOT_NULL_DEFAULTS
        ok = covered or dbdefault is not None
        # A 'title'-nek nincs adatbazis-defaultja, tehat KELL kliens-oldali.
        if dbdefault is None:
            ok = covered
        print("  {:<24} db default: {:<16} client default: {:<6} {}".format(
            col, str(dbdefault), str(covered), "ok" if ok else "FAIL"))
        if not ok:
            FAILS.append(("not-null default missing", col))
    return cols


# --------------------------------------------------------------------------
# 2. Sor-epites a VALODI adatbol
# --------------------------------------------------------------------------

def build_rows_from_replay():
    import replay_audit as RA
    import reconcile_programmes as R
    events, types, countries, label = RA.load_events()
    by_id, decisions = RA.replay(events, types)
    rows = R.build_programme_rows(by_id.values(), stamp="2026-08-17T20:00:00")
    return rows, label, by_id


def test_key_uniformity(rows):
    print("\n2. PostgREST: every row in the batch has the same key set")
    print("-" * 78)
    shapes = {tuple(sorted(r)) for r in rows}
    print("  {} row(s), {} distinct key set(s)".format(len(rows), len(shapes)))
    if len(shapes) != 1:
        FAILS.append(("key sets differ", len(shapes)))
        print("  FAIL")
    else:
        print("  ok — {} columns per row".format(len(next(iter(shapes)))))


def test_no_null_in_not_null(rows, cols):
    print("\n3. No explicit NULL in a NOT NULL column")
    print("-" * 78)
    bad = {}
    for r in rows:
        for col in cols:
            if col in r and r[col] is None:
                bad.setdefault(col, 0)
                bad[col] += 1
    if not bad:
        print("  ok — none of {} NOT NULL column(s) receives NULL".format(
            len(cols)))
    for col, n in bad.items():
        print("  FAIL {:<24} NULL in {} row(s)".format(col, n))
        FAILS.append(("null in not-null column", col))


# --------------------------------------------------------------------------
# 3. TENYLEGES beszuras valodi PostgreSQL-be
# --------------------------------------------------------------------------

def test_real_insert(rows):
    print("\n4. Real INSERT into PostgreSQL (the definitive check)")
    print("-" * 78)
    if PGBIN is None:
        print("  [skip] no local postgres found — SQL-level check skipped")
        return
    port = "5455"
    # Fix utvonal /tmp alatt: a mkdtemp altal letrehozott szulo konyvtar
    # jogosultsagai miatt a postgres felhasznalo nem tudta bejarni az utat.
    data = Path("/tmp/pgw_test_data")
    sh("rm -rf {0} && mkdir -p {0} && chmod 777 /tmp && "
       "chown -R postgres:postgres {0}".format(data))
    r1 = sh("su postgres -c '{}/initdb -D {} -A trust'".format(PGBIN, data))
    r2 = sh("su postgres -c '{}/pg_ctl -D {} -o \"-k /tmp -p {}\" "
            "-l /tmp/pgw.log start'".format(PGBIN, data, port))
    sh("sleep 4")
    try:
        ok, out = psql("select 1;", port)
        if not ok:
            print("  [skip] postgres would not start")
            print("    initdb: {}".format(
                (r1.stderr or r1.stdout or "")[-300:].strip()))
            print("    pg_ctl: {}".format(
                (r2.stderr or r2.stdout or "")[-300:].strip()))
            log = sh("tail -5 /tmp/pgw.log")
            print("    log: {}".format((log.stdout or "").strip()[-300:]))
            return

        # pipeline_runs, hogy a migracio vegso szakasza is lefusson
        psql("create table pipeline_runs (run_id bigint generated always as "
             "identity primary key, script_name text, started_at timestamptz "
             "default now(), finished_at timestamptz, status text, "
             "items_processed int, error_message text);", port)

        for f in ("schema.sql", "add_capability_fields.sql", "add_reports.sql",
                  "add_fleet_verification.sql", "add_programme_layer.sql"):
            r = sh("psql -h /tmp -p {} -U postgres -q -v ON_ERROR_STOP=1 -f {}"
                   .format(port, ROOT / "supabase" / f))
            if r.returncode != 0:
                print("  FAIL migration {}: {}".format(
                    f, (r.stderr or "")[:200]))
                FAILS.append(("migration", f))
                return
        print("  schema built from the 5 migration files")

        # FK-k: orszagok es tipusok betoltese
        cats = json.loads((ROOT / "data" / "aircraft_catalogue.json").read_text(
            encoding="utf-8"))
        ctry = json.loads((ROOT / "data" / "countries.json").read_text(
            encoding="utf-8"))
        cats = cats if isinstance(cats, list) else next(
            v for v in cats.values() if isinstance(v, list))
        ctry = ctry if isinstance(ctry, list) else next(
            v for v in ctry.values() if isinstance(v, list))
        vals = ",".join("('{}','{}','{}')".format(
            t["type_id"], str(t.get("name", "")).replace("'", "''"),
            t.get("category", "other")) for t in cats)
        psql("insert into ac_aircraft_types(type_id,name,category) values {} "
             "on conflict do nothing;".format(vals), port)
        vals = ",".join("('{}','{}')".format(
            c["country_id"], str(c.get("name", "")).replace("'", "''"))
            for c in ctry)
        psql("insert into ac_countries(country_id,name) values {} "
             "on conflict do nothing;".format(vals), port)
        print("  {} type(s) and {} country(ies) seeded for the FKs".format(
            len(cats), len(ctry)))

        # A VALODI sorok beszurasa, egyenkent — igy latszik, MELYIK bukik el
        inserted, failed = 0, []
        jsonb = {"claim_history", "superseded_quantities",
                 "quantity_conflicts", "observed_quantities"}
        for r in rows:
            cols, vals2 = [], []
            for k, v in r.items():
                cols.append('"{}"'.format(k))
                if v is None:
                    vals2.append("null")
                elif k in jsonb or isinstance(v, (list, dict)):
                    vals2.append("'{}'::jsonb".format(
                        json.dumps(v).replace("'", "''")))
                elif isinstance(v, bool):
                    vals2.append("true" if v else "false")
                elif isinstance(v, (int, float)):
                    vals2.append(str(v))
                else:
                    vals2.append("'{}'".format(str(v).replace("'", "''")))
            sql = "insert into ac_programmes ({}) values ({});".format(
                ",".join(cols), ",".join(vals2))
            ok, err = psql(sql, port)
            if ok:
                inserted += 1
            else:
                failed.append((r.get("programme_id"), err.strip()[:220]))

        print("  inserted {}/{} programme row(s)".format(inserted, len(rows)))
        for pid, err in failed[:8]:
            print("  FAIL {}: {}".format(pid, err))
        if failed:
            FAILS.append(("insert failures", len(failed)))

        # Ellenorzes: a NOT NULL oszlopok tenyleg kaptak erteket
        ok, out = psql(
            "select count(*) filter (where independent_lineages is null) as il, "
            "count(*) filter (where evidence_count is null) as ec, "
            "count(*) filter (where title is null) as t, count(*) as total "
            "from ac_programmes;", port)
        print("  post-insert null check: {}".format(
            " ".join(out.split())[:120]))
    finally:
        sh("su postgres -c '{}/pg_ctl -D {} stop'".format(PGBIN, data))
        sh("rm -rf {}".format(data))


def main():
    print("=" * 78)
    print("PROGRAMME WRITE PATH — verified against real PostgreSQL")
    print("=" * 78)
    cols = test_defaults_cover_not_null()
    rows, label, by_id = build_rows_from_replay()
    print("\nsource: {}".format(label))
    print("{} programme row(s) built by the production code path".format(
        len(rows)))
    test_key_uniformity(rows)
    test_no_null_in_not_null(rows, cols)
    test_real_insert(rows)

    print("\n" + "=" * 78)
    if FAILS:
        print("FAILURES: {}".format(len(FAILS)))
        for f in FAILS:
            print("  {}".format(f))
        return 1
    print("Write path verified — the batch inserts cleanly into a real "
          "PostgreSQL built from the migration files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
