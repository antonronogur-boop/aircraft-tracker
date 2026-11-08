import { loadDraftRow } from "@/lib/draftStore";
import { CommandBriefPage, type BriefView } from "@/components/CommandBriefPage";

export const dynamic = "force-dynamic";

/* /weekly/2026-W46/command — egy adott het Command Briefje ("latest" is jo).
 * ?view=draft  -> munkapeldany · ?release=N -> adott kiadas */
export default async function WeekCommandBrief({ params, searchParams }: {
  params: { week: string }; searchParams: BriefView;
}) {
  const s = await loadDraftRow(params.week);
  return <CommandBriefPage report={s?.row} draft={s?.draft} q={searchParams} />;
}
