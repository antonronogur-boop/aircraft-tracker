-- Weekly report archive + pipeline_runs constraint extension.
-- Run once in Supabase SQL Editor.

create table if not exists ac_reports (
  report_id     bigint generated always as identity primary key,
  week_label    text not null,               -- e.g. '2026-W29'
  period_start  date not null,
  period_end    date not null,
  generated_at  timestamptz default now(),
  payload       jsonb not null               -- full structured report
);

create unique index if not exists ac_reports_week_idx on ac_reports(week_label);

alter table ac_reports enable row level security;
drop policy if exists "anon read" on ac_reports;
create policy "anon read" on ac_reports for select using (true);

alter table public.pipeline_runs drop constraint if exists pipeline_runs_script_name_check;
alter table public.pipeline_runs add constraint pipeline_runs_script_name_check
  check (script_name in ('collect_rss','process_articles','generate_weekly_report',
                         'ac_collect_rss','ac_process_articles','ac_weekly_digest',
                         'ac_weekly_report'));
