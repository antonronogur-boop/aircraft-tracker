import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { CommandBrief } from "@/components/CommandBrief";
import { DownloadButtons } from "@/components/DownloadButtons";
import type { ReportRow } from "@/lib/reports";
import type { CommandBriefV2 } from "@/lib/briefTypes";

/* Az onallo Command Brief oldal — KULON TERMEK a reszletes heti jelentestol.
 * Web nezet + PDF (nyomtatas) + Word (.docx), mind ugyanabbol az adatbol. */
export function CommandBriefPage({ report }: { report: ReportRow | undefined }) {
  if (!report) {
    return (
      <div>
        <PageHeader title="Command brief not found" />
        <Link href="/weekly" className="text-sm text-cyan-400 hover:text-cyan-300">← Weekly reports</Link>
      </div>
    );
  }
  const brief = report.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  const v2 = brief?.schema === "command_brief_v2";
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 print:hidden">
        <PageHeader
          title={`Command Air Intelligence Brief — ${report.week_label}`}
          description="A standalone 4-page brief for a Hungarian commander, plus Sources & Legend. Every item links to its original source."
        />
        <div className="flex flex-wrap items-center gap-2">
          <Link href={`/weekly/${report.week_label}`} className="text-xs text-slate-400 hover:text-slate-200">
            Detailed weekly report (analyst product) →
          </Link>
          {v2 && <DownloadButtons week={report.week_label} />}
        </div>
      </div>
      {!v2 ? (
        <p className="text-sm text-slate-500">
          This week has no v2 Command Brief yet. The next Wednesday report includes it — or rebuild it for this
          week with <code className="text-slate-300">python scripts/backfill_command_brief.py --week {report.week_label}</code>.
        </p>
      ) : (
        <CommandBrief brief={brief!} />
      )}
    </div>
  );
}
