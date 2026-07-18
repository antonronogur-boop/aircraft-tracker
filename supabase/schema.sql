-- ============================================================
--  Aircraft Procurement Tracker — database schema
--  All tables prefixed ac_ so they coexist with the drone/UAV
--  monitor tables in the same Supabase project.
--  Run once in Supabase SQL Editor.
-- ============================================================

-- 1. Aircraft type catalogue (the encyclopedia — seeded from
--    data/aircraft_catalogue.json, then maintained by hand)
create table if not exists ac_aircraft_types (
  type_id            text primary key,          -- slug, e.g. 'f-16'
  name               text not null,             -- 'F-16 Fighting Falcon'
  designation        text,                      -- current main variant family, e.g. 'F-16C/D Block 70/72'
  category           text not null,             -- fighter | bomber | attack | trainer | transport | tanker | helicopter | special_mission | maritime_patrol | uav
  manufacturer       text,
  origin_country     text,
  role               text,                      -- one-line role description
  first_flight_year  int,
  production_status  text default 'in_production',  -- in_production | out_of_production | in_development
  notes              text,
  aliases            jsonb default '[]'::jsonb  -- alternative names for matching
);

-- 2. Countries (operators)
create table if not exists ac_countries (
  country_id  text primary key,                 -- ISO 3166-1 alpha-3, lowercase, e.g. 'srb'
  name        text not null,
  region      text,                             -- e.g. 'Balkans', 'Middle East'
  aliases     jsonb default '[]'::jsonb
);

-- 3. Fleet baseline — the heart of the tracker.
--    One row = one country's holding of one type in one status.
create table if not exists ac_fleets (
  fleet_id     bigint generated always as identity primary key,
  country_id   text not null references ac_countries(country_id),
  type_id      text not null references ac_aircraft_types(type_id),
  fleet_status text not null default 'active',  -- active | on_order | option | selected | retiring | retired
  quantity     int,
  variant      text,
  as_of        date,
  source_note  text,
  unique (country_id, type_id, fleet_status)
);

-- 4. Sources (RSS + manual)
create table if not exists ac_sources (
  source_id         text primary key,
  source_name       text not null,
  rss_url           text,                       -- null = manual source
  homepage          text,
  reliability_score int default 70,             -- 0-100
  language          text default 'en',
  enabled           boolean default true
);

-- 5. Collected articles
create table if not exists ac_articles (
  article_id      text primary key,             -- 'rss-' + sha16(url)
  source_id       text references ac_sources(source_id),
  title           text,
  url             text,
  publish_date    date,
  collected_date  date,
  short_summary   text,
  status          text default 'raw',           -- raw | processed | irrelevant | failed
  failure_reason  text,
  dedupe_hash     text unique
);

-- 6. Events — what the AI extracts from articles. Everything the
--    frontend shows revolves around these.
create table if not exists ac_events (
  event_id                 bigint generated always as identity primary key,
  article_id               text references ac_articles(article_id),
  event_type               text not null,       -- order | delivery | upgrade | export_sale | selection | negotiation | retirement | incident | other
  country_id               text references ac_countries(country_id),
  type_id                  text references ac_aircraft_types(type_id),
  counterparty_country_id  text references ac_countries(country_id),  -- seller/buyer other side, if any
  quantity                 int,
  value_usd_m              numeric,             -- deal value in millions USD, if stated
  event_date               date,
  summary                  text not null,       -- one/two-sentence plain-English event summary
  confidence               numeric,             -- 0..1 extraction confidence
  review_status            text default 'pending',   -- pending | approved | rejected
  unresolved_type_name     text,                -- raw name when no catalogue match
  unresolved_country_name  text,
  created_at               timestamptz default now()
);

create index if not exists ac_events_country_idx on ac_events(country_id);
create index if not exists ac_events_type_idx    on ac_events(type_id);
create index if not exists ac_events_review_idx  on ac_events(review_status);
create index if not exists ac_articles_status_idx on ac_articles(status);

-- 7. Read-only access for the public frontend (anon key), writes only
--    with the service_role key — same pattern as the drone monitor.
alter table ac_aircraft_types enable row level security;
alter table ac_countries      enable row level security;
alter table ac_fleets         enable row level security;
alter table ac_sources        enable row level security;
alter table ac_articles       enable row level security;
alter table ac_events         enable row level security;

do $$
declare t text;
begin
  foreach t in array array['ac_aircraft_types','ac_countries','ac_fleets',
                           'ac_sources','ac_articles','ac_events'] loop
    execute format('drop policy if exists "anon read" on %I', t);
    execute format('create policy "anon read" on %I for select using (true)', t);
  end loop;
end $$;
