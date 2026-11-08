import { loadDraftRow } from "@/lib/draftStore";
import { CommandBriefPage, type BriefView } from "@/components/CommandBriefPage";

export const dynamic = "force-dynamic";

/* /weekly/command-brief — a legfrissebb heti Command Brief. */
export default async function LatestCommandBrief({ searchParams }: { searchParams: BriefView }) {
  const s = await loadDraftRow("latest");
  return <CommandBriefPage report={s?.row} draft={s?.draft} q={searchParams} />;
}
