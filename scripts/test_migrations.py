# -*- coding: utf-8 -*-
"""Migracios ut ellenorzese valodi PostgreSQL-en — friss ES meglevo adatbazis.

  A. FRISS adatbazis: a supabase/migrations.txt teljes sorrendje lefut.
  B. IDEMPOTENCIA: a teljes sorrend masodszor is hiba nelkul lefut.
  C. MEGLEVO adatbazis: az uj migracio ELOTTI allapot + valos jellegu adat,
     majd az uj migracio (ketszer) — minden meglevo sor valtozatlan.
  D. NEM DESTRUKTIV: az uj migracioban nincs drop / delete / truncate /
     rename / tipusvaltas (a megjegyzeseken kivul).
  E. FUTASIDO: a triage script a migracio NELKUL is biztonsagosan kilep.

Futtatas: python scripts/test_migrations.py   (helyi postgres kell; ha
nincs, a SQL-szintu reszt kihagyja es ezt kiirja)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("SUPABASE_URL", "https://offline.invalid")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "offline-test-key")

NEW = "add_review_triage.sql"
FAILS = []
PGBIN = next((c for c in ("/usr/lib/postgresql/16/bin",
                          "/usr/lib/postgresql/15/bin", "/usr/local/pgsql/bin")
              if Path(c, "initdb").exists()), None)


def check(label, ok, extra=""):
    print("  {} {}{}".format("ok  " if ok else "FAIL", label,
                            "  — " + extra if extra else ""))
    if not ok:
        FAILS.append(label)


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def manifest():
    return [l.strip() for l in (ROOT / "supabase" / "migrations.txt")
            .read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]


def strip_comments(sql):
    return re.sub(r"--[^\n]*", "", sql)


def start_pg(port, data):
    sh("rm -rf {0} && mkdir -p {0} && chmod 777 /tmp && "
       "chown -R postgres:postgres {0}".format(data))
    sh("su postgres -c '{}/initdb -D {} -A trust'".format(PGBIN, data))
    sh("su postgres -c '{}/pg_ctl -D {} -o \"-k /tmp -p {}\" -l {}.log "
       "start'".format(PGBIN, data, port, data))
    sh("sleep 3")


def stop_pg(data):
    sh("su postgres -c '{}/pg_ctl -D {} stop -m fast'".format(PGBIN, data))


def psql(port, sql=None, f=None):
    cmd = "psql -h /tmp -p {} -U postgres -q -v ON_ERROR_STOP=1 -At ".format(
        port)
    if f:
        cmd += "-f {}".format(f)
    else:
        cmd += "-c \"{}\"".format(sql.replace('"', '\\"'))
    r = sh(cmd)
    return r.returncode == 0, (r.stdout or "").strip(), (r.stderr or "")


def apply(port, files):
    for name in files:
        ok, _, err = psql(port, f=ROOT / "supabase" / name)
        if not ok:
            return False, "{}: {}".format(name, err.strip()[:200])
    return True, ""


def base_tables(port):
    psql(port, "create table if not exists pipeline_runs (run_id bigint "
               "generated always as identity primary key, script_name text, "
               "started_at timestamptz default now(), finished_at "
               "timestamptz, status text, items_processed int, "
               "error_message text);")


def test_static():
    print("\nD. The new migration is additive and idempotent (static)")
    sql = strip_comments((ROOT / "supabase" / NEW).read_text(
        encoding="utf-8")).lower()
    bad = re.findall(r"\b(drop|delete|truncate|rename|alter\s+column|"
                     r"update\s+\w+\s+set)\b", sql)
    check("no drop / delete / truncate / rename / type change", not bad,
          ", ".join(bad))
    adds = re.findall(r"add column (\w+ )?", sql)
    check("every add column is 'if not exists'",
          all(a.strip() == "if" for a in adds) and bool(adds))
    check("listed in supabase/migrations.txt (apply order)",
          NEW in manifest())


def test_runtime_without_column():
    print("\nE. Runtime is safe before the migration is applied")
    import supabase_client as db
    import triage_events as T
    calls = {"update": 0}
    orig = (db.select, db.update)
    try:
        db.select = lambda table, params=None: (
            [{"event_id": 1, "review_status": "pending",
              "summary": "x"}] if table == "ac_events" else [])
        db.update = lambda *a, **k: calls.__setitem__("update",
                                                      calls["update"] + 1)
        T.main()
    finally:
        db.select, db.update = orig
    check("triage step skips (no write) when the column is missing",
          calls["update"] == 0)


def test_sql():
    if not PGBIN:
        print("\n[skip] no local PostgreSQL — SQL-level checks skipped")
        return
    files = manifest()
    print("\nA/B. Fresh database: full migration order, twice")
    port, data = "5466", "/tmp/pg_mig_fresh"
    start_pg(port, data)
    try:
        base_tables(port)
        ok, err = apply(port, files)
        check("fresh: all {} migrations apply".format(len(files)), ok, err)
        ok2, err2 = apply(port, files)
        check("idempotent: second full run succeeds", ok2, err2)
        _, typ, _ = psql(port, "select data_type from information_schema."
                               "columns where table_name='ac_events' and "
                               "column_name='triage';")
        check("ac_events.triage exists as jsonb", typ == "jsonb", typ)
        _, nul, _ = psql(port, "select is_nullable from information_schema."
                               "columns where table_name='ac_events' and "
                               "column_name='triage';")
        check("triage is nullable (no forced back-fill)", nul == "YES", nul)
    finally:
        stop_pg(data)

    print("\nC. Existing database: data in place, then the new migration")
    port, data = "5467", "/tmp/pg_mig_existing"
    start_pg(port, data)
    try:
        base_tables(port)
        ok, err = apply(port, [f for f in files if f != NEW])
        check("existing: previous migrations apply", ok, err)
        seed = [
            "insert into ac_countries(country_id,name,region) values "
            "('pol','Poland','Eastern Europe'),('srb','Serbia','Balkans');",
            "insert into ac_aircraft_types(type_id,name,category) values "
            "('fa-50','KAI FA-50','fighter'),('rafale','Dassault Rafale',"
            "'fighter');",
            "insert into ac_sources(source_id,source_name) values "
            "('ACS-0001','Defense News');",
            "insert into ac_articles(article_id,source_id,title,url,"
            "publish_date,dedupe_hash) values ('a1','ACS-0001','FA-50 duty',"
            "'https://x/1','2026-10-03','h1');",
            "insert into ac_events(article_id,event_type,country_id,type_id,"
            "quantity,event_date,summary,review_status) values "
            "('a1','delivery','pol','fa-50',12,'2026-10-02','FA-50 duty',"
            "'approved'),('a1','delivery','srb','rafale',2,'2026-11-05',"
            "'Rafale','pending');",
        ]
        for q in seed:
            ok, _, err = psql(port, q)
            if not ok:
                check("seed existing data", False, err[:200])
                return
        snap = ("select md5(string_agg(event_id::text||event_type||"
                "coalesce(country_id,'')||coalesce(quantity::text,'')||"
                "summary||review_status, ',' order by event_id)) from "
                "ac_events;")
        _, before, _ = psql(port, snap)
        _, n_before, _ = psql(port, "select count(*) from ac_events;")
        ok, err = apply(port, [NEW])
        check("new migration applies on an existing database", ok, err)
        ok, err = apply(port, [NEW])
        check("… and again (idempotent)", ok, err)
        _, after, _ = psql(port, snap)
        _, n_after, _ = psql(port, "select count(*) from ac_events;")
        check("existing rows unchanged (count)", n_before == n_after,
              "{} -> {}".format(n_before, n_after))
        check("existing rows unchanged (content checksum)",
              before == after and bool(before))
        _, nulls, _ = psql(port, "select count(*) from ac_events where "
                                 "triage is null;")
        check("no back-fill: triage is NULL on existing rows",
              nulls == n_after, nulls)
        ok, _, err = psql(port, "update ac_events set triage = "
                                "jsonb_build_object('triage_class', "
                                "'routine') where review_status='pending';")
        _, st, _ = psql(port, "select review_status from ac_events where "
                              "triage is not null;")
        check("writing triage leaves review_status untouched",
              ok and st == "pending", st or err[:120])
    finally:
        stop_pg(data)


if __name__ == "__main__":
    test_static()
    test_runtime_without_column()
    test_sql()
    print("\n" + ("{} migration check(s) FAILED".format(len(FAILS)) if FAILS
                  else "All migration checks passed."))
    sys.exit(1 if FAILS else 0)
