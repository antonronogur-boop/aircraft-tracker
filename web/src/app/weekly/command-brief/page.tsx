import { loadReport } from "@/lib/reports";
import { CommandBriefPage } from "@/components/CommandBriefPage";

export const dynamic = "force-dynamic";

/* /weekly/command-brief — a legfrissebb heti Command Brief (4 oldal). */
export default async function LatestCommandBrief() {
  return <CommandBriefPage report={await loadReport("latest")} />;
}
