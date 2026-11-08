// GET /api/command-brief/template — a hivatalos Word FALLBACK template
// (.dotx), ugyanabbol a presentation schemabol es rendererbol, mint a heti
// export. A repo templates/ mappajaban verziozott peldany is van.
import { buildCommandBriefDocx } from "@/lib/commandBriefDocx";
import { templateBrief } from "@/lib/templateBrief";
import { svg2png } from "@/lib/svg2png";
import { TEMPLATE_VERSION } from "@/lib/presentation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const buf = await buildCommandBriefDocx(templateBrief(), svg2png, { template: true });
  return new Response(new Uint8Array(buf), {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
      "Content-Disposition": `attachment; filename="Command_Air_Intelligence_Brief_v${TEMPLATE_VERSION}.dotx"`,
      "Cache-Control": "no-store",
    },
  });
}
