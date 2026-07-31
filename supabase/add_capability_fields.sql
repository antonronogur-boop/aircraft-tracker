-- add_capability_fields.sql — Aircraft Tracker v2: air power development
-- intelligence brief.
--
-- A jelentes eddig azt mondta meg, MI KERULT AZ ADATBAZISBA. A felderitoi
-- kerdes viszont az, hogy MILYEN LEGI KEPESSEG VALTOZOTT, MIKORRA VALIK
-- HASZNALHATOVA, MENNYIRE BIZTOS, ES MIT JELENT. Ehhez negy uj dimenzio kell:
--
-- 1. BESZERZESI ELETCIKLUS. Az "order" cimke alatt eddig egyutt volt a nemet
--    parlamenti koltsegvetesi jovahagyas, egy 2020-ban alairt szerzodes es egy
--    amerikai gyartasi megrendeles. Katonailag ezek nem egyenertekuek:
--    "szandekozik beszerezni 60 helikoptert" es "a 60. helikopter hadrendbe
--    all" ket kulonbozo vilag. A DSCA/FMS-notifikacio kulon stadium: az csak
--    EXPORTENGEDELY egy felso ertekhatarral, nem alairt uzlet.
--
-- 2. ERTEKTIPUS ES ARFOLYAM-EV. A "disclosed value" eddig osszeadta a firm
--    szerzodest, az IDIQ-plafont ("up to $90M"), az FMS-notifikacios maximumot
--    es a 2020-as aron alairt osszeget. Ezek nem osszeadhatok.
--
-- 3. KEPESSEGI DOMAIN. A "476 aircraft" egy kalapban kezelt egy F-35-ot, egy
--    Chinookot, egy CCA-t es egy hatizsakos motoros siklóernyot.
--
-- 4. KEPESSEG-HATALYBALEPES. Egy 7,7 mrd USD-s szerzodes near-term fenyegetesi
--    hatasa NULLA, ha az elso szazad 2030-ban all fel. Ezert a dontesi datum
--    mellett kell a szallitasi ablak es a varhato IOC.
--
-- Futtasd egyszer a Supabase SQL editorban (ujra futtathato).

alter table ac_events
  add column if not exists lifecycle_stage      text,
  add column if not exists value_type           text,
  add column if not exists value_currency_year  int,
  add column if not exists capability_domain    text,
  add column if not exists delivery_start_year  int,
  add column if not exists delivery_end_year    int,
  add column if not exists expected_ioc_year    int,
  add column if not exists announcement_date    date,
  add column if not exists reports_count        int  not null default 1,
  add column if not exists independent_lineages int  not null default 1,
  add column if not exists updated_at           timestamptz default now();

comment on column ac_events.lifecycle_stage is
  'requirement | rfi_sources_sought | rfp | bid | selection | national_approval | export_approval | contract_signed | production | delivery | ioc | foc | upgrade_programme | retirement | loss | other. Az export_approval (DSCA/FMS/State Dept) NEM alairt uzlet: engedelyezesi felso hatar.';
comment on column ac_events.value_type is
  'firm (alairt szerzodesertek) | ceiling (IDIQ/"up to") | notified_max (DSCA-notifikacio felso hatara) | estimate (sajtobecsles) | unknown. Csak azonos tipusu ertekek adhatok ossze.';
comment on column ac_events.value_currency_year is
  'Az ertek arfolyam-eve. 2020-as es 2026-os dollar nem ugyanaz; osszegzeskor jelezni kell.';
comment on column ac_events.capability_domain is
  'fighter_strike | air_mobility_rotary | air_mobility_fixed | uncrewed_cca | counter_uas | isr_aew_sigint | tanker | training | attack_helicopter | maritime_patrol | other';
comment on column ac_events.expected_ioc_year is
  'Varhato kezdeti muveleti keszenlet eve. Ez dont a near-term hatasrol, nem a szerzodes datuma.';
comment on column ac_events.announcement_date is
  'A BEJELENTES napja. Az event_date az esemeny megtortentenek napja — egy 2020-as szerzodesrol szolo 2026-os cikk nem tesz egy 2020-as esemenyt e hetive.';
comment on column ac_events.independent_lineages is
  'Fuggetlen forras-szalak szama. Ket lap ugyanarrol a gyartoi kozlemenyrol = 1 szal.';

create index if not exists ac_events_event_date_idx on ac_events(event_date);
create index if not exists ac_events_domain_idx     on ac_events(capability_domain);
create index if not exists ac_events_stage_idx      on ac_events(lifecycle_stage);
