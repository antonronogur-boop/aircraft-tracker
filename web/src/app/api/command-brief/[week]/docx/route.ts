// GET /api/command-brief/<week|latest>/docx — szerkesztheto Word-export.
//
// Ugyanabbol a payload.command_brief-bol, mint a web nezet es a PDF; a
// tarolt jelentest nem modositja. A terkepeket a webes SVG-bol rendereli
// nagy felbontasu PNG-be (resvg, beagyazott DejaVu Sans betukeszlettel, mert
// a serverless kornyezetben nincs rendszerfont).
import path from "path";
import { loadReport } from "@/lib/reports";
import { buildCommandBriefDocx } from "@/lib/commandBriefDocx";
import type { CommandBriefV2 } from "@/lib/briefTypes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function svg2png(svg: string, width: number): Promise<Buffer> {
  const { Resvg } = await import("@resvg/resvg-js");
  const fonts = path.join(process.cwd(), "assets", "fonts");
  const r = new Resvg(svg, {
    fitTo: { mode: "width", value: width },
    font: {
      loadSystemFonts: false,
      fontFiles: [path.join(fonts, "DejaVuSans.ttf"), path.join(fonts, "DejaVuSans-Bold.ttf")],
      defaultFontFamily: "DejaVu Sans",
    },
    background: "#ffffff",
  });
  return r.render().asPng();
}

export async function GET(_req: Request, { params }: { params: { week: string } }) {
  const report = await loadReport(params.week);
  const brief = report?.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  if (!report || !brief || brief.schema !== "command_brief_v2") {
    return Response.json(
      { error: "No v2 Command Brief for this week. Rebuild it with scripts/backfill_command_brief.py." },
      { status: 404 });
  }
  const buf = await buildCommandBriefDocx(brief, svg2png);
  const name = `Command_Brief_${report.week_label}.docx`;
  return new Response(new Uint8Array(buf), {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition": `attachment; filename="${name}"`,
      "Cache-Control": "no-store",
    },
  });
}
