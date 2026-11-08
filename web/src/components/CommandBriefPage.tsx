import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { CommandBrief } from "@/components/CommandBrief";
import { DownloadButtons } from "@/components/DownloadButtons";
import type { ReportRow } from "@/lib/reports";
import type { CommandBriefV2 } from "@/lib/briefTypes";
import { publishedView, statusLabel, type BriefDraft } from "@/lib/briefDraft";

export type BriefView = { view?: string; release?: string };

/* Az onallo Command Brief oldal — KULON TERMEK a reszletes heti jelentestol.
 * Alapertelmezes: a legutobbi KIADOTT (released) valtozat; ha meg nincs, a
 * munkapeldany, minden oldalon lathato "WORKING COPY — NOT APPROVED"
 * jelolessel. Kanonikus PDF csak APPROVED / RELEASED allapotbol keszul. */
export function CommandBriefPage({ report, draft, q = {} }: {
  report: ReportRow | undefined; draft?: BriefDraft | null; q?: BriefView;
}) {
  if (!report) {
    return (
      <div>
        <PageHeader title="Command brief not found" />
        <Link href="/weekly" className="text-sm text-cyan-400 hover:text-cyan-300">← Weekly reports</Link>
      </div>
    );
  }
  const base = report.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  const v2 = base?.schema === "command_brief_v2";
  let shown: CommandBriefV2 | null = null;
  let kind: "release" | "draft" = "draft";
  let newer = false;
  let relNo: number | null = null;
  if (v2) {
    const want = q.release ? Number(q.release) : null;
    const rel = want ? draft?.releases?.find((r) => r.release_no === want) : undefined;
    if (rel) {
      shown = publishedView(base!, { ...draft!, releases: [rel] }, "release").brief;
      kind = "release"; relNo = rel.release_no;
    } else {
      const pv = publishedView(base!, draft, q.view === "draft" ? "draft" : "auto");
      shown = pv.brief; kind = pv.kind; newer = pv.newerDraft; relNo = pv.release?.release_no ?? null;
    }
  }
  const d = shown?.meta.draft;
  const qs = kind === "release" && relNo ? `?release=${relNo}` : "?view=draft";
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
          {v2 && (
            <Link href={`/weekly/${report.week_label}/command/edit`}
                  className="rounded border border-slate-600 px-3 py-1.5 text-xs text-slate-100 hover:border-slate-400">
              Edit (analyst)
            </Link>
          )}
          {v2 && <DownloadButtons week={report.week_label} canonical={!!d?.canonical} query={qs} />}
        </div>
      </div>
      {v2 && d && (
        <p className="mb-2 text-xs text-slate-400 print:hidden" data-brief-view={kind}>
          Showing: <b className="text-slate-200">{kind === "release" ? `Release R-${relNo}` : `${statusLabel(d.status)} · draft rev ${d.revision}`}</b>
          {d.approved_by && <> · approved by {d.approved_by}</>}
          {newer && <> · a newer draft is in editing (<Link className="text-sky-300 hover:underline" href={`/weekly/${report.week_label}/command?view=draft`}>view working copy</Link>)</>}
          {kind === "draft" && draft?.releases?.length ? <> · <Link className="text-sky-300 hover:underline" href={`/weekly/${report.week_label}/command`}>view latest release</Link></> : null}
          {!d.canonical && <> · <span className="text-amber-300">working copy — the canonical PDF is produced only from an approved draft</span></>}
        </p>
      )}
      {!v2 ? (
        <p className="text-sm text-slate-500">
          This week has no v2 Command Brief yet. The next Wednesday report includes it — or rebuild it for this
          week with <code className="text-slate-300">python scripts/backfill_command_brief.py --week {report.week_label}</code>.
        </p>
      ) : (
        <CommandBrief brief={shown!} />
      )}
    </div>
  );
}
