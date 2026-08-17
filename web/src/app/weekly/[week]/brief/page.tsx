import { fetchTable } from "@/lib/db";
import { PageHeader } from "@/components/ui";
import { BriefingView } from "@/components/BriefingView";
import { PrintButton } from "@/components/PrintButton";
import Link from "next/link";
import type { ReportRow } from "../../page";

export const dynamic = "force-dynamic";

/* A 4 slide-os briefing nezet egy adott hetre.
 *
 * A teljes jelentes marad a reference product; ez az, amibol elo lehet adni.
 * A "latest" kulcsszo a legfrissebb jelentest hozza, hogy a nezet linkelhetó
 * legyen anelkul, hogy a hetcimket tudni kellene:  /weekly/latest/brief
 */
export default async function BriefingPage({
  params,
}: {
  params: { week: string };
}) {
  const query = params.week === "latest"
    ? "select=*&order=period_end.desc&limit=1"
    : `select=*&week_label=eq.${encodeURIComponent(params.week)}&limit=1`;
  const rows = await fetchTable<ReportRow>("ac_reports", query);
  const report = rows[0];

  if (!report) {
    return (
      <div>
        <PageHeader title="Briefing not found" />
        <Link href="/weekly" className="text-sm text-cyan-400 hover:text-cyan-300">
          ← Back to latest report
        </Link>
      </div>
    );
  }

  const briefing = report.payload?.briefing;

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title={`Briefing — ${report.week_label}`}
          description="Four slides for a 5–8 minute spoken brief. The full weekly report remains the reference product."
        />
        <div className="flex items-center gap-2 print:hidden">
          <Link href={`/weekly/${report.week_label}`}
                className="text-xs text-slate-400 hover:text-slate-200">
            Full report →
          </Link>
          <PrintButton />
        </div>
      </div>

      {!briefing ? (
        <p className="text-sm text-slate-500">
          This report predates the briefing view (added in v3.0). The next generated report will
          include it — see the{" "}
          <Link href={`/weekly/${report.week_label}`} className="text-cyan-400 hover:text-cyan-300">
            full report
          </Link>{" "}
          for this period.
        </p>
      ) : (
        <BriefingView
          briefing={briefing}
          weekLabel={report.week_label}
          periodStart={report.period_start}
          periodEnd={report.period_end}
        />
      )}
    </div>
  );
}
