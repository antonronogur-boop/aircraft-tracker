-- export_fleet_review.sql — FLOTTA-KIVONAT KULSO ELLENORZESHEZ.
--
-- CEL: egy olyan tablazat, amit valaki (elemzo vagy masik AI) at tud nezni
-- anelkul, hogy hozzaferne az adatbazishoz. Ezert minden sor ONMAGABAN
-- ertelmezheto: orszagnev, tipusnev, valtozat, statusz, darabszam, es hogy
-- MIKORRA vonatkozik.
--
-- A LEGFONTOSABB MEGKULONBOZTETES: a "van neki" es a "rendelt belole" nem
-- ugyanaz, es a ketto osszeadasa a leggyakoribb hiba a nyilt forrasu
-- flotta-adatokban. A tracker ezt a fleet_status mezoben tartja:
--
--   active    — repul, uzemel                    -> BIRTOKOLT
--   retiring  — kivonas alatt, de meg uzemel     -> BIRTOKOLT
--   retired   — mar nem uzemel                   -> KORABBAN HASZNALT
--   on_order  — megrendelve, meg nem szallitottak-> NEM birtokolt
--   option    — opcio, nem lehivott              -> NEM birtokolt
--   selected  — kivalasztva, szerzodes elott     -> NEM birtokolt
--
-- Az 1. lekerdezes csak a BIRTOKOLT es a KORABBAN HASZNALT allomanyt adja —
-- pontosan azt, amit ellenorizni akarunk. A 2. kulon mutatja a folyamatban
-- levo beszerzest, hogy lathato legyen, de ne keveredjen bele.
--
-- Futtatas: Supabase SQL Editor. Minden lekerdezes eredmenyet kulon CSV-be
-- mentsd (jobb felso sarok -> Download CSV).

-- ===========================================================================
-- 1. BIRTOKOLT ES KORABBAN HASZNALT ALLOMANY  (ezt add at ellenorzesre)
-- ===========================================================================
select
  c.name                                   as orszag,
  c.country_id                             as orszag_kod,
  c.region                                 as regio,
  t.name                                   as tipus,
  t.type_id                                as tipus_kod,
  t.category                               as kategoria,
  t.manufacturer                           as gyarto,
  t.origin_country                         as szarmazas,
  f.variant                                as valtozat,
  case f.fleet_status
    when 'active'   then 'uzemel'
    when 'retiring' then 'kivonas alatt'
    when 'retired'  then 'korabban hasznalt'
  end                                      as allapot,
  f.quantity                               as darab,
  f.as_of                                  as adat_datuma,
  f.source_note                            as forras_megjegyzes,
  -- Ellenorzoi fogodzo: mi az, ami eleve gyanus a sorban.
  concat_ws('; ',
    case when f.quantity is null then 'DARABSZAM HIANYZIK' end,
    case when f.as_of is null then 'NINCS DATUM' end,
    case when f.as_of < current_date - interval '2 years'
         then 'AZ ADAT 2 EVNEL REGEBBI' end,
    case when f.source_note is null or f.source_note = ''
         then 'NINCS FORRASMEGJEGYZES' end
  )                                        as jelzesek
from ac_fleets f
join ac_countries c      on c.country_id = f.country_id
join ac_aircraft_types t on t.type_id    = f.type_id
where f.fleet_status in ('active', 'retiring', 'retired')
order by c.name, t.category, t.name, f.fleet_status;

-- ===========================================================================
-- 2. FOLYAMATBAN LEVO BESZERZES  (kulon, NEM adhato hozza az elozohoz)
-- ===========================================================================
-- Egy megrendelt gep nem kepesseg. A ketto osszeadasa azt sugallja, hogy egy
-- orszagnak mar most megvan az, ami 5 ev mulva erkezik — ez a leggyakoribb
-- torzitas a nyilt forrasu flotta-osszesitesekben.
select
  c.name as orszag, t.name as tipus, f.variant as valtozat,
  case f.fleet_status
    when 'on_order' then 'megrendelve'
    when 'option'   then 'opcio'
    when 'selected' then 'kivalasztva'
  end   as beszerzesi_allapot,
  f.quantity as darab, f.as_of as adat_datuma, f.source_note as forras
from ac_fleets f
join ac_countries c      on c.country_id = f.country_id
join ac_aircraft_types t on t.type_id    = f.type_id
where f.fleet_status in ('on_order', 'option', 'selected')
order by c.name, t.name;

-- ===========================================================================
-- 3. ORSZAG-SZINTU OSSZEGZES  (gyors attekintes)
-- ===========================================================================
select
  c.name as orszag,
  count(*) filter (where f.fleet_status in ('active','retiring'))    as tipus_uzemben,
  sum(f.quantity) filter (where f.fleet_status in ('active','retiring')) as gep_uzemben,
  count(*) filter (where f.fleet_status = 'retired')                 as tipus_kivonva,
  sum(f.quantity) filter (where f.fleet_status = 'retired')          as gep_kivonva,
  sum(f.quantity) filter (where f.fleet_status = 'on_order')         as gep_rendelesben,
  max(f.as_of)                                                      as legfrissebb_adat
from ac_fleets f
join ac_countries c on c.country_id = f.country_id
group by c.name
order by gep_uzemben desc nulls last;

-- ===========================================================================
-- 4. ADATMINOSEG — mit NEM tudunk
-- ===========================================================================
-- Ez a lekerdezes szandekosan a hianyokat mutatja. Egy flotta-adatbazis
-- ertekét nem az donti el, mennyi sor van benne, hanem hogy tudjuk-e, MELYIK
-- sorban nem bizhatunk meg.
select 'darabszam nelkuli sor' as hiba, count(*) as db
  from ac_fleets where quantity is null
union all
select 'datum nelkuli sor', count(*)
  from ac_fleets where as_of is null
union all
select '2 evnel regebbi adat', count(*)
  from ac_fleets where as_of < current_date - interval '2 years'
union all
select 'forrasmegjegyzes nelkuli sor', count(*)
  from ac_fleets where source_note is null or source_note = ''
union all
select 'orszag flotta-sor nelkul', count(*)
  from ac_countries c
 where not exists (select 1 from ac_fleets f where f.country_id = c.country_id)
union all
select 'tipus, amit senki nem uzemeltet', count(*)
  from ac_aircraft_types t
 where not exists (select 1 from ac_fleets f where f.type_id = t.type_id);

-- ===========================================================================
-- 5. GYANUS DUPLIKATUM  (ugyanaz a tipus egy orszagnal tobb sorban)
-- ===========================================================================
-- A unique(country_id, type_id, fleet_status) megengedi, hogy ugyanaz a tipus
-- 'active' ES 'retired' allapotban is szerepeljen — ez legitim (reszben
-- kivontak). De ha a ket sor darabszama egyutt tobb, mint a valos allomany,
-- akkor valamelyik nem lett frissitve a kivonaskor.
select c.name as orszag, t.name as tipus,
       string_agg(f.fleet_status || '=' || coalesce(f.quantity::text, '?'),
                  ', ' order by f.fleet_status) as allapotok,
       sum(f.quantity) as osszesen
from ac_fleets f
join ac_countries c      on c.country_id = f.country_id
join ac_aircraft_types t on t.type_id    = f.type_id
group by c.name, t.name
having count(*) > 1
order by c.name, t.name;
