// Heti jelentesek betoltese — Supabase-bol, vagy (CSAK teszthez) fixture-bol.
//
// AC_REPORT_FIXTURE=/path/rows.json  -> a rows.json egy ReportRow tomb. Ez
// teszi lehetove, hogy a Command Brief bongeszos / PDF E2E tesztje adatbazis
// nelkul fusson. Elesben az env nincs beallitva, es minden a regi uton megy.
import { fetchTable } from "@/lib/db";
import type { ReportPayload } from "@/components/WeeklyReportView";

export interface ReportRow {
  report_id: number;
  week_label: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  payload: ReportPayload;
}

async function fixtureRows(): Promise<ReportRow[] | null> {
  const path = process.env.AC_REPORT_FIXTURE;
  if (!path) return null;
  const { readFile } = await import("fs/promises");
  const rows = JSON.parse(await readFile(path, "utf-8")) as ReportRow[];
  return [...rows].sort((a, b) => (b.period_end ?? "").localeCompare(a.period_end ?? ""));
}

export async function loadReports(limit = 30): Promise<ReportRow[]> {
  const fx = await fixtureRows();
  if (fx) return fx.slice(0, limit);
  return fetchTable<ReportRow>("ac_reports", `select=*&order=period_end.desc&limit=${limit}`);
}

/** week = "2026-W46" vagy "latest" */
export async function loadReport(week: string): Promise<ReportRow | undefined> {
  const fx = await fixtureRows();
  if (fx) return week === "latest" ? fx[0] : fx.find((r) => r.week_label === week);
  const query = week === "latest"
    ? "select=*&order=period_end.desc&limit=1"
    : `select=*&week_label=eq.${encodeURIComponent(week)}&limit=1`;
  const rows = await fetchTable<ReportRow>("ac_reports", query);
  return rows[0];
}
