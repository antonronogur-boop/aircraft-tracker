import { fetchTable } from "@/lib/db";
import { PageHeader } from "@/components/ui";
import { WeeklyReportView } from "@/components/WeeklyReportView";
import { PrintButton } from "@/components/PrintButton";
import Link from "next/link";
import type { ReportRow } from "../page";

export const dynamic = "force-dynamic";

export default async function ArchivedReportPage({ params }: { params: { week: string } }) {
  const rows = await fetchTable<ReportRow>(
    "ac_reports", `select=*&week_label=eq.${encodeURIComponent(params.week)}&limit=1`);
  const report = rows[0];
  if (!report) {
    return (
      <div>
        <PageHeader title="Report not found" />
        <Link href="/weekly" className="text-sm text-cyan-400 hover:text-cyan-300">← Back to latest report</Link>
      </div>
    );
  }
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title={`Weekly report — ${report.week_label}`}
          description={`Archived report · generated ${report.generated_at?.slice(0, 16).replace("T", " ")} UTC`}
        />
        <div className="flex items-center gap-2 print:hidden">
          <Link href="/weekly" className="text-xs text-slate-400 hover:text-slate-200">← Latest</Link>
          <PrintButton />
        </div>
      </div>
      <WeeklyReportView
        payload={report.payload}
        weekLabel={report.week_label}
        periodStart={report.period_start}
        periodEnd={report.period_end}
      />
    </div>
  );
}
