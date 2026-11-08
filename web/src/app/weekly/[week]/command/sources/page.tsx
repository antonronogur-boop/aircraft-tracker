import Link from "next/link";
import { loadDraftRow } from "@/lib/draftStore";
import { PageHeader } from "@/components/ui";
import { SourceRegisterTable } from "@/components/CommandBrief";
import { publishedView } from "@/lib/briefDraft";
import type { CommandBriefV2 } from "@/lib/briefTypes";

export const dynamic = "force-dynamic";

/* /weekly/<het>/command/sources — a TELJES publikacio-szintu forrasjegyzek.
 * A kanonikus PDF 5. oldala lineage-szintu (egy sor = egy fuggetlen
 * bizonyitek-lanc); itt minden egyes publikacio lathato: eredeti nyelvu cim,
 * publikacios datum, szerep, lineage, mire bizonyitek / mire kontextus. */
export default async function SourceDetail({ params, searchParams }: {
  params: { week: string }; searchParams: { view?: string; release?: string };
}) {
  const s = await loadDraftRow(params.week);
  const base = s?.row.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  if (!s || !base || base.schema !== "command_brief_v2") {
    return <PageHeader title="Command brief not found" />;
  }
  const relNo = Number(searchParams.release ?? "") || null;
  const rel = relNo ? s.draft?.releases?.find((r) => r.release_no === relNo) : undefined;
  const b = rel ? publishedView(base, { ...s.draft!, releases: [rel] }, "release").brief
    : publishedView(base, s.draft, searchParams.view === "draft" ? "draft" : "auto").brief;
  const L = b.page5.lineages!;
  return (
    <div data-source-detail={b.week_label}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader title={`Source detail — ${b.week_label}`}
          description={`${L.publications} publications in ${L.independent_lineages} independent evidence lineages${L.context_only.length ? ` · ${L.context_only.length} context-only (not evidence)` : ""}. The canonical PDF (page 5) shows one row per lineage; this view lists every publication.`} />
        <Link href={`/weekly/${b.week_label}/command`} className="text-xs text-slate-400 hover:text-slate-200">← Command Brief</Link>
      </div>
      <SourceRegisterTable b={b} />
      <p className="mt-2 text-[11px] text-slate-500">{b.page5.source_note}</p>
    </div>
  );
}
