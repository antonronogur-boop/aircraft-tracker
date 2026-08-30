-- ============================================================
-- add_programme_layer.sql — Aircraft Tracker v3
--
-- EZ A MIGRACIO A RENDSZER LEGFONTOSABB SZERKEZETI JAVITASA.
-- Futtasd egyszer a Supabase SQL editorban (ujra futtathato).
--
-- ------------------------------------------------------------
-- A PROBLEMA
-- ------------------------------------------------------------
-- A W33/W34 jelentesek osszehasonlitasa harom olyan hibat mutatott, amelyek
-- MIND ugyanabbol az egy okbol szarmaznak: a rendszer nem valasztotta el a
-- HETI ESEMENYT, a TARTOS PROGRAMALLAPOTOT es a FORRAS ALLITASAT.
--
--   1. LENGYEL APACHE-DUPLIKACIO. W33: "on order 190" + "this period contract
--      signed x94" -> a KJ mar 284 gepes programme of recordrol beszelt.
--      W34: "on order 286" + "contract signed x96". Ugyanarrol az EGY
--      programrol (a 2024-es lengyel AH-64E beszerzes) szolo ujabb cikkek
--      ujabb es ujabb rendelesnek latszanak. Egy procurement-adatbazisnal ez
--      hosszu tavon vegzetes: a baseline evek alatt elmaszik a valosag alol.
--
--   2. UZBEGISZTAN: negotiation ES contract signed EGYSZERRE. Az elemzoi
--      reteg helyesen "negotiation / confidence low / nincs megerositett
--      szerzodes"-t irt, az ORBAT ugyanakkor "Contract signed x24"-et. Egy
--      allitas ket helyen ket allapotot kapott.
--
--   3. A-100LL -> A-10. A Beriev A-100LL AEW&C-tesztpad veszteset "A-10
--      Thunderbolt II — Loss x1"-kent mutatta a tabla (a matcher hibaja;
--      lasd scripts/ac_match.py). A megjeleniteskori nev-alapu visszakeresest
--      itt zarjuk le vegleg: a riport CSAK foreign key-rol dolgozhat.
--
-- ------------------------------------------------------------
-- A MEGOLDAS: HAROM KULON FOGALOM
-- ------------------------------------------------------------
--   EVIDENCE   — mit allit egy forras.  (ac_articles + ac_event_evidence)
--   EVENT      — mi tortent vagy mi jelent meg a heten.  (ac_events)
--   PROGRAMME  — a tartos valosag.  (ac_programmes)  <-- UJ
--
-- A heti jelentes ebben az iranyban epul:
--     EVIDENCE -> EVENT -> PROGRAMME STATE CHANGE
-- es NEM igy:
--     ARTICLE -> quantity -> ORBAT += quantity
--
-- Egy ujabb cikk ugyanarrol a programrol nem ad hozza darabszamot: FRISSITI
-- vagy MEGERSITI ugyanazt a programot. A darabszam a programon kanonikus,
-- es a felulirt ertekek megorzodnek (superseded_quantities), hogy a
-- programtortenet visszakovethetó legyen.
-- ============================================================


-- ------------------------------------------------------------
-- 1. PROGRAMMES — a tartos valosag
-- ------------------------------------------------------------
create table if not exists ac_programmes (
  programme_id      text primary key,     -- stabil, ember altal olvashato:
                                          -- 'pol-ah64e-2024', 'usa-vc25b-2018'
  country_id        text references ac_countries(country_id),
  type_id           text references ac_aircraft_types(type_id),
  -- A VARIANS ES A HADERONEM A PROGRAM RESZE. A "26 HH-60W az USAF-nak" es a
  -- "UH-60M az US Army-nak" nem ugyanaz a program, meg ha a katalogus
  -- csaladja azonos is. Enelkul all elo a "HH-60W esemeny / UH-60 Active
  -- 2000 baseline" tipusu ORBAT-hiba.
  variant           text,                 -- 'AH-64E', 'HH-60W', 'F-15EX'
  service           text,                 -- 'USAF', 'US Army', 'RAF', 'JASDF'
  title             text not null,        -- 'Poland AH-64E acquisition (2024)'
  programme_kind    text not null default 'acquisition',
  -- acquisition | upgrade | sustainment_mro | infrastructure | training
  -- | retirement | lease | development
  --
  -- MIERT KELL: egy MRO/depot-megallapodasnak NINCS "first aircraft
  -- delivery"-je. A W34 timeline "2028 Poland AH-64E MRO deal (first
  -- delivery)" sora ezert volt hibas: a 2028-as elso atadas a 2024-es
  -- BESZERZESI programhoz tartozik, nem az MRO-megallapodashoz.

  -- --- darabszam: KET KULON MERTEK, sosem osszegezve ---
  --
  -- A torok KAAN program 20 gepre kotott szerzodest, es 148 gepes sorozat-
  -- gyartast TERVEZ. Az ukran Gripen 16 gepre kotott szerzodest egy "up to
  -- 150" szandeknyilatkozat alatt. Ezek NEM ellentmondasok — ket kulonbozo
  -- allitas ugyanarrol a programrol. Egyetlen szamban tarolva vagy az egyik
  -- elveszik, vagy a ketto ellentmondasnak latszik.
  contracted_quantity int,                -- ami FIRM szerzodes alatt van
  contracted_basis  text,
  contracted_as_of  date,
  planned_quantity  int,                  -- a bejelentett/tervezett total
  planned_basis     text,
  planned_as_of     date,
  -- Szarmaztatott fejszam: contracted, ha van; kulonben planned.
  canonical_quantity int,
  canonical_source  text,                 -- contracted | planned
  quantity_basis    text,                 -- contract | announced | reported
                                          -- | estimate | unknown
  quantity_as_of    date,
  superseded_quantities jsonb default '[]'::jsonb,
  -- [{"quantity":190,"field":"planned","basis":"reported",
  --   "superseded_at":"2026-08-11","source":"<article_id>"}]
  -- Ket forras ELLENTMONDO programmeretet allit ugyanazon az evidencia-
  -- szinten. A rendszer NEM dont: megtartja a rogzitett erteket es jelez.
  quantity_conflicts jsonb default '[]'::jsonb,
  -- Nem programmeretu darabszamok (reszszallitas, prototipus, celzokonteneres
  -- vagy hajtomuves tetel), megfigyelesként megorizve.
  observed_quantities jsonb default '[]'::jsonb,

  -- --- allapot ---
  lifecycle_stage   text,                 -- a program ELERT legmagasabb
                                          -- evidencialt stadiuma
  contract_date     date,
  contract_evidence text,                 -- mi bizonyitja: article_id / doc
  -- --- kepesseg-idorend (kulon mezok, lasd 3. pont) ---
  first_delivery_year   int,
  delivery_start_year   int,
  delivery_end_year     int,
  ioc_year              int,
  foc_year              int,
  meaningful_scale_year int,

  -- --- ertek ---
  value_usd_m       numeric,
  value_type        text,
  value_currency_year int,

  -- --- evidencia ---
  confidence        text,                 -- high | moderate | low
  independent_lineages int not null default 1,
  first_reported_at date,
  last_evidence_at  date,
  evidence_count    int not null default 0,
  claim_history     jsonb default '[]'::jsonb,
  -- [{"as_of":"2026-08-11","stage":"contract_signed","quantity":96,
  --   "article_id":"rss-...","note":"MRO offset agreement"}]

  status_note       text,
  review_status     text default 'active',  -- active | merged | rejected
  merged_into       text,                   -- ha duplikatumnak bizonyult
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);

comment on table ac_programmes is
  'A tartos beszerzesi/fejlesztesi valosag. Egy ujabb cikk ugyanarrol a '
  'programrol NEM ad hozza darabszamot, hanem frissiti ezt a rekordot. A '
  'lengyel AH-64E 190 -> 284 -> 286 duplikacio ennek a tablanak a hianya '
  'miatt allt elo.';
comment on column ac_programmes.canonical_quantity is
  'A program teljes darabszama, NEM esemenyek osszege. Ha uj evidencia '
  'mas szamot ad, a regi ertek a superseded_quantities-be kerul.';
comment on column ac_programmes.programme_kind is
  'sustainment_mro / infrastructure programnak nincs "first aircraft '
  'delivery" milestoneja — a timeline ezt hasznalja.';
comment on column ac_programmes.variant is
  'A varians a program resze. HH-60W (USAF CSAR) es UH-60M (US Army) nem '
  'ugyanaz a program, meg ha a katalogus-csalad azonos is.';

-- Ha a tabla egy KORABBI futasbol mar letezik, a fenti create nem adja hozza
-- az uj oszlopokat. Ezert kulon is kikenyszeritjuk oket — igy a szkript
-- tovabbra is ujra futtathato, es a mar telepitett sema is frissul.
alter table ac_programmes
  add column if not exists contracted_quantity int,
  add column if not exists contracted_basis    text,
  add column if not exists contracted_as_of    date,
  add column if not exists planned_quantity    int,
  add column if not exists planned_basis       text,
  add column if not exists planned_as_of       date,
  add column if not exists canonical_source    text,
  add column if not exists quantity_conflicts  jsonb default '[]'::jsonb,
  add column if not exists observed_quantities jsonb default '[]'::jsonb;

comment on column ac_programmes.contracted_quantity is
  'Ami FIRM szerzodes alatt van. Az ORBAT on_order KIZAROLAG ebbol szarmazhat.';
comment on column ac_programmes.planned_quantity is
  'A bejelentett/tervezett teljes program. A torok KAAN eseteben 148, mikozben '
  'a szerzodott allomany 20 — a ketto nem ellentmondas es nem osszegezhetó.';
comment on column ac_programmes.quantity_conflicts is
  'Ket forras ellentmondo programmeretet allit ugyanazon evidencia-szinten. '
  'A rendszer megtartja a rogzitett erteket es elemzoi dontesre jelez.';
comment on column ac_programmes.observed_quantities is
  'Nem programmeretu darabszamok: reszszallitas, prototipus, illetve nem-gep '
  'tetel (celzokonteneres, hajtomuves). Megfigyelesként megorizve.';

create index if not exists ac_programmes_country_idx on ac_programmes(country_id);
create index if not exists ac_programmes_type_idx    on ac_programmes(type_id);
create index if not exists ac_programmes_stage_idx   on ac_programmes(lifecycle_stage);
create index if not exists ac_programmes_active_idx  on ac_programmes(review_status);


-- ------------------------------------------------------------
-- 2. EVENTS — kotes a programhoz, es a BASELINE-DELTA szetvalasztasa
-- ------------------------------------------------------------
alter table ac_events
  add column if not exists programme_id      text references ac_programmes(programme_id),

  -- Entitas-illesztes atlathatosaga. A type_id foreign key marad az EGYETLEN
  -- ut, ahogy a riport tipust azonosit; a variant_raw csak megjelenitesi es
  -- ORBAT-hatokor-dontesi celt szolgal.
  add column if not exists variant_raw       text,
  add column if not exists type_match_kind   text,

  -- ===== A HAROM DARABSZAM-FOGALOM SZETVALASZTASA =====
  -- Ez szunteti meg az uzbeg "negotiation ES contract signed" allapotot.
  add column if not exists quantity_claimed  int,
  add column if not exists on_order_delta    int not null default 0,

  -- ===== EVIDENCIA-IDOREND =====
  -- A W34-ben a 2025-ben elvesztett A-100LL a 2026-W34 "capability
  -- development" reszekent jelent meg, mert egyetlen datummezo volt. Negy
  -- kulonbozo dolgot kell kulon tartani.
  add column if not exists first_reported_at      date,
  add column if not exists new_evidence_at        date,
  add column if not exists assessment_updated_at  date,
  add column if not exists evidence_kind          text default 'new_event',
  add column if not exists originating_evidence_id text,

  -- ===== MILESTONE ES IDOHORIZONT =====
  add column if not exists milestone_kind        text,
  add column if not exists foc_year              int,
  add column if not exists meaningful_scale_year int,
  add column if not exists schedule_change       text;  -- delay | acceleration

comment on column ac_events.quantity_claimed is
  'AMIT A FORRAS ALLIT. Onmagaban nem mozgatja a baseline-t.';
comment on column ac_events.on_order_delta is
  'Amennyivel az ORBAT on_order valoban valtozik. ALAPERTELMEZESBEN 0. '
  'Csak elfogadott szerzodes-evidencia (lifecycle_stage=contract_signed ES '
  'contract_evidence) eseten kap nem nulla erteket. Az uzbeg 24 gepes eset '
  'quantity_claimed=24, on_order_delta=0.';
comment on column ac_events.evidence_kind is
  'new_event = a heten tortent; new_confirmation = korabbi esemeny UJ '
  'megerositese (pl. Oryx 2026-ban vizualisan igazolja a 2025-os A-100LL '
  'veszteseget); reassessment = valtozatlan tenyek uj ertekelese; '
  'correction = korabbi allitas javitasa.';
comment on column ac_events.originating_evidence_id is
  'A FORRASLANC gyokere: gyartoi kozlemeny, miniszteriumi nyilatkozat vagy '
  'primer dokumentum azonositoja. Ket lap ugyanarrol a kozlemenyrol = egy '
  'lineage. A lineage-et EBBOL kell szamolni, nem az event-rekordok szamabol '
  '— a W33 Iran MQ-9/MQ-1C "2 lineage" allitasa ket olyan eventre epult, '
  'amelyek UGYANAZ a cikk voltak.';
comment on column ac_events.milestone_kind is
  'first_delivery | final_delivery | ioc | foc | contract_award | '
  'mro_standup | certification | withdrawal_start | withdrawal_complete | '
  'loss | schedule_slip | none. EGY TIMELINE-SOR = EGY PROGRAMME + EGY '
  'MILESTONE. Egy kesés (schedule_slip) NEM kepesseg-erkezes.';
comment on column ac_events.type_match_kind is
  'exact | variant | family | none. Ha variant, az ORBAT NEM rendelhet '
  'csalad-szintu baseline-t az esemenyhez.';

create index if not exists ac_events_programme_idx on ac_events(programme_id);
create index if not exists ac_events_evidence_kind_idx on ac_events(evidence_kind);


-- ------------------------------------------------------------
-- 3. EVIDENCE — a forraslanc explicit tablaja
-- ------------------------------------------------------------
-- Enelkul a lineage becsles marad. Egy event tobb cikkbol is megerositest
-- kaphat; a FUGGETLEN lancok szama az, ami a confidence-t korlatozza.
create table if not exists ac_event_evidence (
  evidence_id   bigint generated always as identity primary key,
  event_id      bigint references ac_events(event_id) on delete cascade,
  programme_id  text   references ac_programmes(programme_id),
  article_id    text   references ac_articles(article_id),
  -- A LANC GYOKERE, nem a publikalo lap. Ket lap egy Boeing-kozlemenyrol
  -- ugyanezt az erteket kapja -> egy lineage.
  origin_kind   text,   -- manufacturer_release | government_statement |
                        -- contract_document | imagery | parliamentary_record
                        -- | trade_press | osint_visual | unknown
  origin_ref    text,   -- 'boeing-pr-2026-08-11', 'dsca-26-42', 'oryx-...'
  observed_at   date,
  claim         text,
  claim_stage   text,
  claim_quantity int,
  reliability   int,
  created_at    timestamptz default now()
);

create index if not exists ac_event_evidence_event_idx on ac_event_evidence(event_id);
create index if not exists ac_event_evidence_prog_idx  on ac_event_evidence(programme_id);
create index if not exists ac_event_evidence_origin_idx on ac_event_evidence(origin_ref);


-- ------------------------------------------------------------
-- 4. FLEETS — a baseline kulcsa varians- es haderonem-tudatos
-- ------------------------------------------------------------
-- A regi kulcs (country_id, type_id, fleet_status) osszevonta a service-t, a
-- variansot es a role-t. Emiatt jelent meg a "USAF 26 HH-60W" esemeny mellett
-- "UH-60 Black Hawk — Active 2000", es a "brit AH-64E flotta 50 gep" mellett
-- "UK AH-64 Apache — Active 100".
alter table ac_fleets
  add column if not exists service        text,
  add column if not exists baseline_scope text default 'national_family',
  -- national_family | national_variant | service_variant | unit
  add column if not exists programme_id   text references ac_programmes(programme_id);

comment on column ac_fleets.baseline_scope is
  'Mit MER ez a sor. A riport csak akkor mutathat szamot, ha a hatokor '
  'egyezik az esemeny hatokorevel: csalad-szintu baseline nem rendelhetó '
  'varians-szintu esemenyhez.';

-- A regi UNIQUE megszorítás lecsereleset ket lepesben vegezzuk, hogy a
-- meglevo adat ne serulhessen.
alter table ac_fleets drop constraint if exists ac_fleets_country_id_type_id_fleet_status_key;
create unique index if not exists ac_fleets_scope_key
  on ac_fleets(country_id, type_id, fleet_status,
               coalesce(variant, ''), coalesce(service, ''));


-- ------------------------------------------------------------
-- 5. REPORTS — a PUBLIKALT metrikak, hogy a WoW ne csuszhasson el
-- ------------------------------------------------------------
-- A W33 "18 in-period events"-et irt, a W34 "22 in-period events (+0 WoW)"-t.
-- Ket egymast koveto het ugyanazon metrikaja +4, nem +0. Az ok: a W34 az
-- ELOZO hetet ujraszamolta a sajat, kesobbi adatallapotabol — mikozben az
-- osszehasonlitasi alap a W33-ban PUBLIKALT szam.
--
-- Ezert a publikalt metrikat kulon, valtozatlanul tarolni kell.
create table if not exists ac_report_metrics (
  week_label        text primary key references ac_reports(week_label)
                      deferrable initially deferred,
  period_start      date,
  period_end        date,
  events_published  int,          -- amit a jelentes AKKOR kiirt
  developments_published int,
  firm_actions_published int,
  methodology_version text,       -- ha ez valtozik, a WoW nem hasonlithato
  metrics           jsonb default '{}'::jsonb,
  created_at        timestamptz default now()
);

comment on table ac_report_metrics is
  'A PUBLIKALT heti metrikak valtozatlan pillanatfelvetele. A WoW ebbol '
  'szamol, nem az elozo het ujraszamolt ertekebol. Ha a ket szam eltér, azt '
  'recomputation driftkent kell jelezni, nem elhallgatni.';


-- ------------------------------------------------------------
-- 6. Olvasasi jog a publikus frontendnek (anon key)
-- ------------------------------------------------------------
alter table ac_programmes      enable row level security;
alter table ac_event_evidence  enable row level security;
alter table ac_report_metrics  enable row level security;

do $$
declare t text;
begin
  foreach t in array array['ac_programmes','ac_event_evidence',
                           'ac_report_metrics'] loop
    execute format('drop policy if exists "anon read" on %I', t);
    execute format('create policy "anon read" on %I for select using (true)', t);
  end loop;
end $$;


-- ------------------------------------------------------------
-- 7. pipeline_runs: az uj scriptek engedelyezese — ONJAVITO MODON
-- ------------------------------------------------------------
--
-- A pipeline_runs tabla KOZOS a dron/UAV monitorral. Egy whitelist-jellegu
-- CHECK megszorítás egy megosztott naplotablan szerkezeti csapda: valahanyszor
-- barmelyik projekt uj scriptet kap, a MASIK projekt migracioja elbukik ezen:
--
--   ERROR: check constraint "pipeline_runs_script_name_check" of relation
--          "pipeline_runs" is violated by some row
--
-- Ez a hiba nem elmeleti: az add_reports.sql ugyanezt a mintat hasznalta, es
-- azota mindket projektben keletkeztek uj script-nevek.
--
-- Ezert a megszorítás mostantol a MAR MEGLEVO ertekekbol es az ismert uj
-- nevekbol EPUL FEL, futasidoben. Igy
--   * a meglevo adat sosem serti meg (nem kell kezzel felsorolni semmit),
--   * az uj scriptek engedelyt kapnak,
--   * es a migracio ujra futtathato marad.
do $$
declare
  -- HAROM projekt hasznalja ezt a tablat. A lista dokumentacio; a tenyleges
  -- engedely ettol fuggetlenul tartalmazza a tablaban MAR SZEREPLO neveket is.
  known    text[] := array[
    -- dron/UAV monitor
    'collect_rss','process_articles','generate_weekly_report',
    'backfill_links','export_to_json','validate_daily',
    'detect_corroboration','cap_confidence_backfill',
    -- balkan monitor
    'bm_collect_rss','bm_process_articles','bm_weekly_report',
    'bm_weekly_digest',
    -- aircraft tracker
    'ac_collect_rss','ac_process_articles','ac_weekly_digest',
    'ac_weekly_report','ac_backfill_programmes','ac_reconcile_fleets',
    'ac_import_fleets','ac_dedupe_events','ac_resolve_events',
    'ac_audit_event_dates','ac_check_health','ac_seed_database'];
  present  text[];
  allowed  text[];
  clause   text;
begin
  if to_regclass('public.pipeline_runs') is null then
    raise notice 'pipeline_runs does not exist — skipping';
    return;
  end if;

  -- Ami MAR benne van. Enelkul a megszorítás visszamenoleg bukik el.
  select coalesce(array_agg(distinct script_name), '{}')
    into present
  from public.pipeline_runs
  where script_name is not null;

  allowed := array(select distinct unnest(known || present) order by 1);

  select string_agg(quote_literal(v), ',')
    into clause
  from unnest(allowed) as v;

  execute 'alter table public.pipeline_runs '
          'drop constraint if exists pipeline_runs_script_name_check';

  if clause is null then
    raise notice 'pipeline_runs is empty and no known names — constraint left off';
    return;
  end if;

  execute format(
    'alter table public.pipeline_runs add constraint '
    'pipeline_runs_script_name_check check (script_name in (%s))', clause);

  raise notice 'pipeline_runs check rebuilt with % allowed script name(s); % '
               'were already present in the data',
               array_length(allowed, 1), array_length(present, 1);
end $$;
