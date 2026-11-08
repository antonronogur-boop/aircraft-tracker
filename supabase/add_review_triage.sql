-- add_review_triage.sql — AI/rule triage for the article review queue (2026-11).
--
-- One jsonb column on ac_events. It is ADVISORY ONLY: the human approve /
-- reject decision (review_status) and its semantics do not change. The
-- existing "anon read" policy on ac_events already covers the new column.
-- Safe to run more than once.
alter table ac_events add column if not exists triage jsonb;
