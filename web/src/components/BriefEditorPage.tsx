import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { BriefEditor, type EditorPayload } from "@/components/BriefEditor";

/* Weekly -> Command Brief -> Edit. Az elsodleges szerkesztesi felulet. */
export function BriefEditorPage({ data, week }: { data: EditorPayload | null; week: string }) {
  if (!data) {
    return (
      <div>
        <PageHeader title="Command brief not found" />
        <p className="text-sm text-slate-500">No v2 Command Brief for {week}.</p>
        <Link href="/weekly" className="text-sm text-cyan-400 hover:text-cyan-300">← Weekly reports</Link>
      </div>
    );
  }
  return (
    <div className="print:hidden">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title={`Edit Command Brief — ${data.week_label}`}
          description="Publication copy only. Sources, lineage, dates, HU relevance, significance and confidence are controlled analytical metadata and cannot be changed here — an assessment error goes through the analytical workflow."
        />
        <Link href={`/weekly/${data.week_label}/command`} className="text-xs text-slate-400 hover:text-slate-200">
          ← Command Brief
        </Link>
      </div>
      <BriefEditor initial={data} />
    </div>
  );
}
