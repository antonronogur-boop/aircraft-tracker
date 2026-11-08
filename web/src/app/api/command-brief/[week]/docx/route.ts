// GET /api/command-brief/<week|latest>/docx — szerkesztheto Word MUNKAPELDANY.
//
// Ugyanaz a nezet, mint a web/PDF oldalon: alapertelmezes a legutobbi kiadas
// (ha van), kulonben a draft; ?view=draft -> munkapeldany, ?release=N -> adott
// kiadas. A tarolt jelentest nem modositja. Bármely statuszbol keszulhet
// (working copy) — a kanonikus termek a kiadott PDF.
import { loadDraftRow } from "@/lib/draftStore";
import { buildCommandBriefDocx } from "@/lib/commandBriefDocx";
import { publishedView } from "@/lib/briefDraft";
import { svg2png } from "@/lib/svg2png";
import type { CommandBriefV2 } from "@/lib/briefTypes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: { week: string } }) {
  const s = await loadDraftRow(params.week);
  const base = s?.row.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  if (!s || !base || base.schema !== "command_brief_v2") {
    return Response.json(
      { error: "No v2 Command Brief for this week. Rebuild it with scripts/backfill_command_brief.py." },
      { status: 404 });
  }
  const u = new URL(req.url);
  const relNo = Number(u.searchParams.get("release") ?? "") || null;
  const rel = relNo ? s.draft?.releases?.find((r) => r.release_no === relNo) : undefined;
  const brief = rel
    ? publishedView(base, { ...s.draft!, releases: [rel] }, "release").brief
    : publishedView(base, s.draft, u.searchParams.get("view") === "draft" ? "draft" : "auto").brief;
  const buf = await buildCommandBriefDocx(brief, svg2png);
  const d = brief.meta.draft;
  const tag = d?.release_no ? `_R${d.release_no}` : d && !d.canonical ? "_WORKING_COPY" : "";
  const name = `Command_Brief_${s.row.week_label}${tag}.docx`;
  return new Response(new Uint8Array(buf), {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition": `attachment; filename="${name}"`,
      "Cache-Control": "no-store",
    },
  });
}
