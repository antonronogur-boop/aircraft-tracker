/* Browser + PDF E2E for the Command Brief.
 *   BASE=http://localhost:3000 OUT=./e2e-out node e2e/command-brief.e2e.cjs
 * Checks: 4 brief pages, none overflowing its fixed A4 box; every brief
 * cross-reference resolves to an anchor in the full report; standalone PDF is
 * exactly 4 A4-landscape pages; the full report PDF starts with the same 4
 * landscape pages and continues with the detailed report; an older report
 * without a brief still renders. Exit code 1 on any failure. */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://localhost:3311";
const OUT = process.env.OUT || path.join(__dirname, "..", "e2e-out");
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
  const count = (s.match(/\/Type\s*\/Page[^s]/g) || []).length;
  return { count, boxes };
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });

  console.log("Standalone brief /weekly/command-brief");
  await page.goto(`${BASE}/weekly/command-brief`, { waitUntil: "networkidle" });
  const pages = await page.$$eval(".cb-page", (els) => els.map((e) => {
    const body = e.querySelector(".cb-body");
    // Tulcsordulas: a tartalom kilog-e a fix oldalmeretbol (a sorkorlatos
    // mezok sajat magukon belul vagnak, ez a doboz szintjet nezi).
    let worst = 0;
    body.querySelectorAll("*").forEach((c) => {
      const r = c.getBoundingClientRect(), b = body.getBoundingClientRect();
      worst = Math.max(worst, r.bottom - b.bottom, r.right - b.right);
    });
    return { n: e.getAttribute("data-cb-page"), w: e.getBoundingClientRect().width,
             h: e.getBoundingClientRect().height, overflow: Math.round(worst) };
  }));
  ok("exactly 4 brief pages", pages.length === 4, JSON.stringify(pages.map((p) => p.n)));
  for (const p of pages) ok(`page ${p.n}: content inside the A4 box`, p.overflow <= 1, `overflow ${p.overflow}px`);
  const svgs = await page.$$eval(".cb-page svg[role=img]", (e) => e.length);
  ok("two deterministic SVG maps (CEE + global)", svgs === 2, `${svgs}`);
  const ext = await page.$$eval("img, link[rel=stylesheet]", (e) => e.map((x) => x.src || x.href).filter((u) => u && !u.startsWith(location.origin)));
  ok("no external tiles or remote assets", ext.length === 0, ext.join(","));
  for (let i = 0; i < 4; i++) {
    const el = (await page.$$(".cb-page"))[i];
    await el.screenshot({ path: path.join(OUT, `brief_page${i + 1}.png`) });
  }
  const links = await page.$$eval(".cb a.cb-ref", (a) => a.map((x) => x.getAttribute("href")));
  ok("brief carries cross-references", links.length > 5, `${links.length}`);

  console.log("Cross-references resolve in the full report");
  await page.goto(`${BASE}/weekly/2026-W46`, { waitUntil: "networkidle" });
  const anchors = new Set(await page.$$eval("[id]", (e) => e.map((x) => x.id)));
  const missing = [...new Set(links.map((h) => h.split("#")[1]))].filter((id) => !anchors.has(id));
  ok("every brief ref has an anchor in the detailed report", missing.length === 0, missing.join(","));
  const embedded = await page.$$eval(".cb-page", (e) => e.length);
  ok("full report starts with the same 4 brief pages", embedded === 4);
  const order = await page.evaluate(() => {
    const cb = document.querySelector(".cb"); const rb = document.querySelector(".report-body");
    return cb && rb && (cb.compareDocumentPosition(rb) & Node.DOCUMENT_POSITION_FOLLOWING) ? "brief-first" : "wrong";
  });
  ok("brief precedes the detailed report", order === "brief-first");

  console.log("PDF export");
  await page.emulateMedia({ media: "print" });
  await page.goto(`${BASE}/weekly/command-brief`, { waitUntil: "networkidle" });
  const pdf1 = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  fs.writeFileSync(path.join(OUT, "command_brief_2026-W46.pdf"), pdf1);
  const a = pdfPages(pdf1);
  ok("standalone PDF = 4 pages", a.count === 4, `${a.count}`);
  ok("all 4 pages A4 landscape (842x595 pt)", a.boxes.slice(0, 4).every(([w, h]) => w === 842 && h === 595), JSON.stringify(a.boxes.slice(0, 4)));

  await page.goto(`${BASE}/weekly/2026-W46`, { waitUntil: "networkidle" });
  const pdf2 = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  fs.writeFileSync(path.join(OUT, "weekly_report_2026-W46_full.pdf"), pdf2);
  const b = pdfPages(pdf2);
  ok("full report PDF longer than the brief", b.count > 4, `${b.count}`);
  ok("full report: first 4 pages landscape brief", b.boxes.slice(0, 4).every(([w, h]) => w === 842 && h === 595), JSON.stringify(b.boxes.slice(0, 5)));
  ok("full report: detailed part continues portrait", b.boxes.slice(4).every(([w, h]) => h > w), JSON.stringify(b.boxes.slice(4, 6)));

  console.log("Backward compatibility and existing routes");
  await page.emulateMedia({ media: "screen" });
  for (const [url, needle] of [["/weekly/2026-W45", "Bottom line"], ["/weekly/2026-W45/command", "predates the Command Brief"],
                               ["/weekly/2026-W46/brief", "Briefing"], ["/weekly", "Weekly report"]]) {
    const r = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    const txt = await page.textContent("body");
    ok(`${url} renders (${r.status()})`, r.status() === 200 && txt.includes(needle));
  }
  await page.goto(`${BASE}/weekly/2026-W46`, { waitUntil: "networkidle" });
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.screenshot({ path: path.join(OUT, "full_report_top.png") });
  await browser.close();
  console.log(fails.length ? `\n${fails.length} E2E check(s) FAILED` : "\nAll E2E checks passed.");
  process.exit(fails.length ? 1 : 0);
})();
