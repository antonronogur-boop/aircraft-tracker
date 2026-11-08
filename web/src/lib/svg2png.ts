// SVG -> nagy felbontasu PNG (resvg, beagyazott DejaVu Sans betukeszlettel,
// mert a serverless kornyezetben nincs rendszerfont). Csak szerveroldal.
import path from "path";

export async function svg2png(svg: string, width: number): Promise<Buffer> {
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
