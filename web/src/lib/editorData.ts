// A szerkeszto kezdo allapota (szerveroldal) — ugyanaz, mint a draft API GET.
import { loadDraftRow, sha256 } from "@/lib/draftStore";
import { draftState, normalizeBrief } from "@/lib/briefDraft";
import { TEMPLATE_VERSION } from "@/lib/presentation";
import type { CommandBriefV2 } from "@/lib/briefTypes";
import type { EditorPayload } from "@/components/BriefEditor";

export async function editorPayload(week: string): Promise<EditorPayload | null> {
  const stored = await loadDraftRow(week);
  const brief = stored?.row.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  if (!stored || !brief || brief.schema !== "command_brief_v2") return null;
  const st = draftState(stored.draft, brief, sha256, new Date().toISOString());
  return { week_label: stored.row.week_label, generated_at: stored.row.generated_at,
           template_version: TEMPLATE_VERSION, brief: normalizeBrief(brief), ...st };
}
