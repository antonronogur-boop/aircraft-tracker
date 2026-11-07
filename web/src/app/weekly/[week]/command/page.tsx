import { loadReport } from "@/lib/reports";
import { CommandBriefPage } from "@/components/CommandBriefPage";

export const dynamic = "force-dynamic";

/* /weekly/2026-W46/command — egy adott het Command Briefje ("latest" is jo). */
export default async function WeekCommandBrief({ params }: { params: { week: string } }) {
  return <CommandBriefPage report={await loadReport(params.week)} />;
}
