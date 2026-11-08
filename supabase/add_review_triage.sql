-- add_review_triage.sql — advisory triage for the article review queue (2026-11).
--
-- Additive and idempotent: one nullable jsonb column on ac_events. No data is
-- changed, no column or table is dropped, no default is back-filled.
-- The approve / reject decision (review_status) and its semantics do not
-- change. The existing "anon read" policy on ac_events already covers the
-- new column.
--
-- Runtime does NOT depend on this migration: until it is applied,
-- scripts/triage_events.py skips the triage step and the review page simply
-- shows no triage chips.
--
-- Rollback: none needed (the code tolerates the column's absence). If ever
-- required, the inverse is `alter table ac_events drop column if exists
-- triage;` — destructive, therefore NOT part of the forward path.
alter table ac_events add column if not exists triage jsonb;

comment on column ac_events.triage is
  'Advisory review triage (scripts/triage_events.py). Never sets review_status.';
