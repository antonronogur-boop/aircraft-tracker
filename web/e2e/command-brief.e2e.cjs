/* Browser + PDF + Word E2E for the Command Brief v2.
 *   BASE=http://localhost:3311 OUT=./e2e-out WEEK=2026-W46 node e2e/command-brief.e2e.cjs
 * Then: python3 e2e/check_parity.py <rows.json> <WEEK> <OUT>/command_brief.pdf <OUT>/command_brief.docx
 * Exit code 1 on any failure. */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://localhost:3311";
const OUT = process.env.OUT || path.join(__dirname, "..", "e2e-out");
const WEEK = process.env.WEEK || "2026-W46";
const LEGACY = process.env.LEGACY_WEEK || "2026-W45";
fs.mkdirSync(OUT, { recursive: true });
const fails = [];
const ok = (label, cond, extra = "") => {
  console.log(`  ${cond ? "ok  " : "FAIL"} ${label}${extra ? "  — " + extra : ""}`);
  if (!cond) fails.push(label);
};
function pdfPages(buf) {
  const s = buf.toString("latin1");
  const boxes = [...s.matchAll(/\/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]/g)]
    .map((m) => [Math.round(+m[3] - +m[1]), Math.round(+m[4] - +m[2])]);
  return { count: (s.match(/\/Type\s*\/Page[^s]/g) || []).length, boxes };
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });

  console.log(`Standalone Command Brief /weekly/${WEEK}/command`);
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  const pages = await page.$$eval(".cb-page", (els) => els.map((e) => {
    const body = e.querySelector(".cb-body");
    let worst = 0;
    body.querySelectorAll("*").forEach((c) => {
      const r = c.getBoundingClientRect(), b = body.getBoundingClientRect();
      worst = Math.max(worst, r.bottom - b.bottom, r.right - b.right);
    });
    return { n: e.getAttribute("data-cb-page"), flow: e.classList.contains("cb-flow"),
             overflow: Math.round(worst), micro: !!e.querySelector(".cb-micro") };
  }));
  ok("4 executive pages + Sources & Legend", pages.map((p) => p.n).join(",") === "1,2,3,4,5");
  for (const p of pages.slice(0, 4)) ok(`page ${p.n}: content inside the fixed A4 box`, p.overflow <= 1, `overflow ${p.overflow}px`);
  ok("page 5 may flow (source register length varies)", pages[4] && pages[4].flow);
  ok("micro-legend on every page", pages.every((p) => p.micro));
  const txt = await page.$eval(".cb", (e) => e.innerText);
  ok("no truncated executive text (no ellipsis)", !txt.includes("…") && !/\w\.\.\.\s/.test(txt));
  ok("Detailed-assessment cross-refs are gone", !txt.includes("Detailed assessment →"));
  const svgs = await page.$$eval(".cb-page svg[role=img]", (e) => e.length);
  ok("two deterministic SVG maps", svgs === 2, `${svgs}`);
  const ext = await page.$$eval("img, link[rel=stylesheet], script[src]", (e) =>
    e.map((x) => x.src || x.href).filter((u) => u && !u.startsWith(location.origin)));
  ok("no external tiles or remote assets", ext.length === 0, ext.join(","));
  const reg = await page.$$eval("[data-cb-page='5'] tbody tr", (rows) =>
    rows.map((r) => ({ id: r.id, href: r.querySelector("a")?.getAttribute("href") })));
  const regUrls = new Set(reg.map((r) => r.href));
  const links = await page.$$eval(".cb a.cb-ref", (a) => a.map((x) => ({ href: x.getAttribute("href"), text: x.textContent })));
  ok("every executive page cites sources", (await page.$$eval("[data-cb-page]", (ps) =>
    ps.slice(0, 4).map((p) => p.querySelectorAll("a.cb-ref").length))).every((n) => n > 0));
  ok("all source links are absolute original-source URLs", links.every((l) => /^https?:\/\//.test(l.href)));
  ok("every S-xx link points to a register entry", links.filter((l) => /^S-\d+$/.test(l.text)).every((l) => regUrls.has(l.href)));
  ok("register rows have ids S-01..", reg.length > 0 && reg[0].id === "S-01", `${reg.length} sources`);
  const btns = await page.$$eval("button, a", (e) => e.map((x) => x.textContent.trim()));
  ok("Download PDF button", btns.includes("Download PDF"));
  ok("Download Word (.docx) button", btns.includes("Download Word (.docx)"));
  for (let i = 0; i < pages.length; i++) {
    const el = (await page.$$(".cb-page"))[i];
    await el.screenshot({ path: path.join(OUT, `brief_page${i + 1}.png`) });
  }

  console.log("Word export");
  const resp = await page.request.get(`${BASE}/api/command-brief/${WEEK}/docx`);
  ok("DOCX download 200", resp.status() === 200, `${resp.status()}`);
  ok("DOCX content type", (resp.headers()["content-type"] || "").includes("wordprocessingml"));
  ok("DOCX attachment filename", (resp.headers()["content-disposition"] || "").includes(`Command_Brief_${WEEK}.docx`));
  fs.writeFileSync(path.join(OUT, "command_brief.docx"), await resp.body());
  const legacyDocx = await page.request.get(`${BASE}/api/command-brief/${LEGACY}/docx`);
  ok("DOCX for a week without v2 brief → 404, not a broken file", legacyDocx.status() === 404);

  console.log("PDF export");
  await page.emulateMedia({ media: "print" });
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  fs.writeFileSync(path.join(OUT, "command_brief.pdf"), pdf);
  const a = pdfPages(pdf);
  ok("PDF = 4 executive pages + ≥1 Sources & Legend page", a.count >= 5, `${a.count}`);
  ok("all PDF pages A4 landscape", a.boxes.every(([w, h]) => w === 842 && h === 595), JSON.stringify(a.boxes));

  console.log("Separate products and existing routes");
  await page.emulateMedia({ media: "screen" });
  await page.goto(`${BASE}/weekly/${WEEK}`, { waitUntil: "networkidle" });
  ok("detailed weekly report no longer embeds the brief", (await page.$$(".cb-page")).length === 0);
  ok("detailed report links to the Command Brief", (await page.textContent("body")).includes("Command brief"));
  ok("detailed report anchors intact (D-01)", !!(await page.$("#D-01")));
  for (const [url, needle] of [[`/weekly/${LEGACY}`, "Bottom line"], [`/weekly/${LEGACY}/command`, "no v2 Command Brief"],
                               [`/weekly/${WEEK}/brief`, "Briefing"], ["/weekly", "Weekly report"],
                               ["/weekly/command-brief", "Command Air Intelligence Brief"]]) {
    const r = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    const t = await page.textContent("body");
    ok(`${url} renders (${r.status()})`, r.status() === 200 && t.includes(needle));
  }
  await browser.close();
  console.log(fails.length ? `\n${fails.length} E2E check(s) FAILED` : "\nAll browser E2E checks passed.");
  process.exit(fails.length ? 1 : 0);
})();
