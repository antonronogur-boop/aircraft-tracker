import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { PrintButton } from "@/components/PrintButton";
import { CommandBrief } from "@/components/CommandBrief";
import type { ReportRow } from "@/lib/reports";

/* Az onallo Command Brief oldal (es a 4 oldalas PDF forrasa). Ugyanaz a
 * CommandBrief komponens, mint a teljes jelentes elejen — a nyomtatas itt
 * pontosan a 4 oldalt adja. A hivatkozasok a reszletes jelentesre mutatnak. */
export function CommandBriefPage({ report }: { report: ReportRow | undefined }) {
  if (!report) {
    return (
      <div>
        <PageHeader title="Command brief not found" />
        <Link href="/weekly" className="text-sm text-cyan-400 hover:text-cyan-300">← Back to latest report</Link>
      </div>
    );
  }
  const brief = report.payload?.command_brief;
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 print:hidden">
        <PageHeader
          title={`Command Air Intelligence Brief — ${report.week_label}`}
          description="Four pages for a Hungarian commander, built from the same assessed data as the weekly report. Print / Save as PDF gives exactly these 4 pages (A4 landscape)."
        />
        <div className="flex items-center gap-2">
          <Link href={`/weekly/${report.week_label}`} className="text-xs text-slate-400 hover:text-slate-200">
            Full report (brief + detailed assessment) →
          </Link>
          <PrintButton />
        </div>
      </div>
      {!brief ? (
        <p className="text-sm text-slate-500">
          This report predates the Command Brief (added in methodology v3.1). The next Wednesday report
          will include it — or rebuild it for this week with{" "}
          <code className="text-slate-300">python scripts/backfill_command_brief.py --week {report.week_label}</code>.
        </p>
      ) : (
        <CommandBrief brief={brief} detailBase={`/weekly/${report.week_label}`} />
      )}
    </div>
  );
}
