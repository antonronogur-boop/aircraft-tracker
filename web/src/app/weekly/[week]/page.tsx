import { loadReport } from "@/lib/reports";
import { BriefEmbed } from "@/components/BriefEmbed";
import { PageHeader } from "@/components/ui";
import { WeeklyReportView } from "@/components/WeeklyReportView";
import { PrintButton } from "@/components/PrintButton";
import Link from "next/link";
import type { ReportRow } from "../page";

export const dynamic = "force-dynamic";

export default async function ArchivedReportPage({ params }: { params: { week: string } }) {
  const report: ReportRow | undefined = await loadReport(params.week);
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
      {/* Nyomtataskor a jelentes ELSO 4 oldala a Command Brief. */}
      <div className={`flex flex-wrap items-start justify-between gap-3 ${report.payload?.command_brief ? "cb-print-hide" : ""}`}>
        <PageHeader
          title={`Weekly report — ${report.week_label}`}
          description={`Archived report · generated ${report.generated_at?.slice(0, 16).replace("T", " ")} UTC`}
        />
        <div className="flex items-center gap-2 print:hidden">
          <Link href="/weekly" className="text-xs text-slate-400 hover:text-slate-200">← Latest</Link>
          {report.payload?.command_brief && (
            <Link href={`/weekly/${report.week_label}/command`}
                  className="rounded border border-amber-600/60 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200 hover:border-amber-400">
              Command brief (4 pages) →
            </Link>
          )}
          <Link href={`/weekly/${report.week_label}/brief`}
                className="rounded border border-cyan-700/60 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-200 hover:border-cyan-500">
            4-slide briefing →
          </Link>
          <PrintButton />
        </div>
      </div>
      <BriefEmbed payload={report.payload} />
      <WeeklyReportView
        payload={report.payload}
        weekLabel={report.week_label}
        periodStart={report.period_start}
        periodEnd={report.period_end}
      />
    </div>
  );
}
