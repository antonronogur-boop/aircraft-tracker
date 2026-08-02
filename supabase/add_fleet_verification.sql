-- add_fleet_verification.sql — KULSO HITELESITES NYOMA A FLOTTA-SOROKON.
--
-- MIERT: a flotta-adatok egy resze kezi feltoltesu volt, hitelesites nelkul.
-- Egy kulso ellenorzes utan a legrosszabb, amit tehetunk, hogy egyszeruen
-- feluliruk a szamokat — mert akkor egy ho mulva mar nem tudjuk megmondani,
-- MELYIK sor ment at ellenorzesen es melyik nem, es MIRE hivatkozva.
--
-- Ezert az ellenorzes nem az adatot valtoztatja meg csendben, hanem NYOMOT
-- HAGY: mikor, mi alapjan, milyen bizonyossaggal, es mi volt az itelet.
--
-- A KULCS-MEZO a verification_verdict. Negy ertek van, es mindegyik MAST
-- jelent a kesobbi felhasznalas szempontjabol:
--
--   confirmed      — a szam ellenorizve, egyezik            -> hasznalhato
--   corrected      — a szam javitva lett                    -> hasznalhato
--   unverifiable   — nyilt forrasbol nem allapithato meg    -> NEM hasznalhato
--                    pontos szamkent; a range_note orzi, amit tudunk
--   needs_split    — a sor tobb kulonbozo dolgot kever      -> szerkezeti hiba
--                    (pl. MQ-9A Reaper es MQ-9B Protector egy sorban)
--
-- Az "unverifiable" NEM hiba es NEM torlendo. Egy bizonytalan sor, ami annak
-- van jelolve, hasznalhato; egy magabiztos teves szam kart okoz. A jelentesek
-- ezt a mezot olvasva tudjak eldonteni, mit szabad allitani.
--
-- PROGRAMKERET: kulon mezo, es SOSEM keverheto a darabszammal. A 29 gepes
-- Apache-program nem 29 uzemelo helikopter — ez pontosan az a hiba, amit az
-- ellenorzes a legtobb sorban talalt.

begin;

alter table ac_fleets add column if not exists verification_verdict    text;
alter table ac_fleets add column if not exists verified_quantity       int;
alter table ac_fleets add column if not exists verified_as_of          date;
alter table ac_fleets add column if not exists verification_confidence text;
alter table ac_fleets add column if not exists verification_source     text;
alter table ac_fleets add column if not exists verification_source_url text;
alter table ac_fleets add column if not exists verification_note       text;
-- Amikor a valos ertek tartomany ("kb. 160-165", "legalabb 11"), a szamot NEM
-- irjuk be, mert az hamis pontossagot adna. A szoveges alak ide kerul.
alter table ac_fleets add column if not exists quantity_range_note     text;
-- A teljes beszerzesi program merete. NEM aktiv allomany, NEM osszeadhato.
alter table ac_fleets add column if not exists program_total           int;
alter table ac_fleets add column if not exists verified_at             timestamptz;

do $$ begin
  alter table ac_fleets add constraint ac_fleets_verdict_chk
    check (verification_verdict is null or verification_verdict in (
      'confirmed', 'corrected', 'unverifiable', 'needs_split'));
exception when duplicate_object then null; end $$;

do $$ begin
  alter table ac_fleets add constraint ac_fleets_vconf_chk
    check (verification_confidence is null or verification_confidence in (
      'high', 'medium', 'low'));
exception when duplicate_object then null; end $$;

create index if not exists ac_fleets_verdict_idx on ac_fleets (verification_verdict);

comment on column ac_fleets.verification_verdict is
  'confirmed | corrected | unverifiable | needs_split. Az unverifiable NEM hiba: azt jelenti, hogy nyilt forrasbol nem allapithato meg pontos szam. Ilyen sorbol nem szabad konkret darabszamot allitani — a quantity_range_note orzi, amit tudunk.';
comment on column ac_fleets.program_total is
  'A teljes beszerzesi program merete. NEM az uzemelo allomany, es SOHA nem adhato hozza ahhoz. A 29 gepes Apache-program nem 29 uzemelo helikopter.';
comment on column ac_fleets.quantity_range_note is
  'Ha a valos ertek tartomany vagy also becsles ("kb. 160-165", "legalabb 11"), akkor a quantity mezobe NEM irunk szamot — a hamis pontossag rosszabb, mint a bevallott bizonytalansag.';

commit;
