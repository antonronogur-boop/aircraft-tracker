/* Builds the official Word fallback template from the presentation schema:
 *   cd web && node scripts/build_dotx.cjs
 * -> templates/Command_Air_Intelligence_Brief.dotx            (current)
 *    templates/Command_Air_Intelligence_Brief_v<version>.dotx (archived)
 *    templates/command_brief_presentation_v<version>.json     (archived schema)
 * Same renderer as the weekly Word export (src/lib/commandBriefDocx.ts). */
const path = require("path");
const fs = require("fs");
const jiti = require("jiti")(__filename, { alias: { "@": path.join(__dirname, "..", "src") }, interopDefault: true });
const { buildCommandBriefDocx } = jiti("../src/lib/commandBriefDocx.ts");
const { templateBrief } = jiti("../src/lib/templateBrief.ts");
const { svg2png } = jiti("../src/lib/svg2png.ts");
const { TEMPLATE_VERSION } = jiti("../src/lib/presentation.ts");

(async () => {
  process.chdir(path.join(__dirname, ".."));
  // A web tukorpeldanyt a kanonikus config-fajlhoz igazitjuk.
  fs.copyFileSync(path.join(__dirname, "..", "..", "config", "command_brief_presentation.json"),
                  path.join(__dirname, "..", "src", "lib", "command_brief_presentation.json"));
  const out = path.join(__dirname, "..", "..", "templates");
  fs.mkdirSync(out, { recursive: true });
  const buf = await buildCommandBriefDocx(templateBrief(), svg2png, { template: true });
  fs.writeFileSync(path.join(out, "Command_Air_Intelligence_Brief.dotx"), buf);
  fs.writeFileSync(path.join(out, `Command_Air_Intelligence_Brief_v${TEMPLATE_VERSION}.dotx`), buf);
  fs.copyFileSync(path.join(__dirname, "..", "..", "config", "command_brief_presentation.json"),
                  path.join(out, `command_brief_presentation_v${TEMPLATE_VERSION}.json`));
  console.log(`template v${TEMPLATE_VERSION}: ${buf.length} bytes -> ${out}`);
})().catch((e) => { console.error(e); process.exit(1); });
