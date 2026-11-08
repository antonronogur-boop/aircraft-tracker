# Date semantics audit — 2026-11-08 (PO blocker 1)

Five different dates exist in the pipeline. They answer different questions and **must never stand in for each other**.

| Field | Meaning | Where it comes from | Stored as |
|---|---|---|---|
| `source_publication_datetime` | When the article/statement was published | RSS/Atom entry `published` (`collect_rss.article_row`) → `ac_articles.publish_date`; for analyst-attached evidence: the verified page date (`config/evidence_supplements.json → published`) | `ac_articles.publish_date` (date) |
| `system_retrieval_datetime` | When our collector fetched it | `collect_rss.article_row` → `ac_articles.collected_date`; `ac_events.created_at` | `collected_date`, `created_at` |
| `event_date` | When the reported thing happened (delivery, loss, deployment) | Sonnet extraction (`process_articles.py`) | `ac_events.event_date` |
| `contract_date` | When a contract was signed | Programme layer: the event date of a contract-evidenced event (`ac_programmes.contract_date`) | `ac_programmes.contract_date` |
| `milestone_date` | First delivery / IOC / FOC / scale years | Extraction + `ac_intel._enforce_effect_timing` | `delivery_start_year`, `expected_ioc_year`, `foc_year`, `meaningful_scale_year` |

## Defect found and fixed

**Command Brief Source Register — `Published` column.** The v2 register displayed `publication_date ?? event_date`: when an article's publication date was not available to the brief (the W45 sample was rebuilt from the stored report's annex, which carries the event date but not the article date), the *event date* was shown as the publication date (e.g. 2025-04-01, 2023 contract year). Fixed:

- `Published` = article `publish_date` (feed) → else the date in the article URL (`/2026/10/31/`) → else **blank ("not recorded")**. Event, contract, milestone and retrieval dates are never used. The basis is shown (`url`, `analyst-verified`; feed is the default).
- `event_date` and `retrieved` are kept as separate fields and never rendered as "Published".
- Regression tests (`scripts/test_command_brief.py`, section G): feed date wins over URL and event date; no feed/URL date → blank even when an event date exists; retrieval date kept separately; URL-date extraction; no published value without a basis.

## Other substitutions found (not shown in the Command Brief; recorded for follow-up)

- `ac_programmes.first_reported_at` / `last_evidence_at` and `claim_history.as_of` fall back to `event_date` when `new_evidence_at` is missing (`ac_programmes.seen_or`, `apply_event`). These are programme bookkeeping fields, not publication dates; they are not displayed as publication dates anywhere. Recommended follow-up: feed them from the article `publish_date`.
- `ac_intel.effective_day` places an undated event by `announcement_date`, then `created_at`. This is window assignment, flagged in the report as "dated by collection time"; it is not presented as a publication date.
