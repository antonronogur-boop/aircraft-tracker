/* Browser + PDF + Word E2E for the Command Brief (authoring model).
 *   BASE=http://localhost:3311 OUT=./e2e-out WEEK=2026-W46 node e2e/command-brief.e2e.cjs
 * The server must run with AC_REPORT_FIXTURE=<rows.json> and a FRESH
 * AC_DRAFT_STORE=file:<dir> (see e2e/run_all.sh). Covers: generated view,
 * canonical 5-page PDF, structured editor (edit → save → submit → approve →
 * release), controlled-field protection, conflict detection, overflow
 * warning, release view / PDF / DOCX, Word template, existing routes.
 * Writes OUT/published_brief.json for e2e/check_parity.py.
 * Exit code 1 on any failure. */
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.BASE || "http://localhost:3311";
const OUT = process.env.OUT || path.join(__dirname, "..", "e2e-out");
const WEEK = process.env.WEEK || "2026-W46";
const LEGACY = process.env.LEGACY_WEEK || "2026-W45";
const NEW_TEXT = process.env.NEW_TEXT ||
  "Poland has shifted its first FA-50 tranche into operational air-defence alert duty, Hungary’s nearest Allied example.";
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

async function viewChecks(page, label) {
  const pages = await page.$$eval(".cb-page", (els) => els.map((e) => {
    const body = e.querySelector(".cb-body");
    let worst = 0;
    body.querySelectorAll("*").forEach((c) => {
      const r = c.getBoundingClientRect(), b = body.getBoundingClientRect();
      worst = Math.max(worst, r.bottom - b.bottom, r.right - b.right);
    });
    return { n: e.getAttribute("data-cb-page"), flow: e.classList.contains("cb-flow"),
             overflow: Math.round(worst), micro: !!e.querySelector(".cb-micro"),
             stamp: e.querySelector(".cb-stamp")?.textContent ?? "" };
  }));
  ok(`${label}: 4 executive pages + Sources & Legend`, pages.map((p) => p.n).join(",") === "1,2,3,4,5");
  for (const p of pages) ok(`${label}: page ${p.n} content inside the fixed A4 box`, p.overflow <= 1 && !p.flow, `overflow ${p.overflow}px${p.flow ? ", flowing" : ""}`);
  ok(`${label}: micro-legend on every page`, pages.every((p) => p.micro));
  return pages;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  const api = page.request;

  // ------------------------------------------------ 1. generated view --
  console.log(`Generated view /weekly/${WEEK}/command`);
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  const pg0 = await viewChecks(page, "generated");
  ok("every page stamped WORKING COPY — NOT APPROVED", pg0.every((p) => /WORKING COPY/.test(p.stamp) && /NOT APPROVED/.test(p.stamp)));
  const txt = await page.$eval(".cb", (e) => e.innerText);
  ok("no truncated executive text (no ellipsis)", !txt.includes("…") && !/\w\.\.\.\s/.test(txt));
  ok("Detailed-assessment cross-refs are gone", !txt.includes("Detailed assessment →"));
  ok("two deterministic SVG maps", (await page.$$eval(".cb-page svg[role=img]", (e) => e.length)) === 2);
  const ext = await page.$$eval("img, link[rel=stylesheet], script[src]", (e) =>
    e.map((x) => x.src || x.href).filter((u) => u && !u.startsWith(location.origin)));
  ok("no external tiles or remote assets", ext.length === 0, ext.join(","));
  const reg = await page.$$eval("[data-cb-page='5'] tbody tr", (rows) => rows.map((r) => ({
    id: r.id, href: r.querySelector("a")?.getAttribute("href"), role: r.getAttribute("data-evidence-role"),
    ev: r.querySelector("[data-col=evidence-for]")?.textContent, cx: r.querySelector("[data-col=context-for]")?.textContent,
    lineage: r.children[6]?.textContent })));
  const regUrls = new Set(reg.map((r) => r.href));
  const links = await page.$$eval(".cb a.cb-ref", (a) => a.map((x) => ({ href: x.getAttribute("href"), text: x.textContent })));
  ok("every executive page cites sources", (await page.$$eval("[data-cb-page]", (ps) =>
    ps.slice(0, 4).map((p) => p.querySelectorAll("a.cb-ref").length))).every((n) => n > 0));
  ok("all source links are absolute original-source URLs", links.every((l) => /^https?:\/\//.test(l.href)));
  ok("every S-xx link points to a register entry", links.filter((l) => /^S-\d+$/.test(l.text)).every((l) => regUrls.has(l.href)));
  ok("register rows have ids S-01..", reg.length > 0 && reg[0].id === "S-01", `${reg.length} sources`);
  ok("every register row has an evidence role", reg.every((r) => r.role === "EVIDENCE" || r.role === "CONTEXT_ONLY"));
  const ctxRows = reg.filter((r) => r.role === "CONTEXT_ONLY");
  ok("context source: 'Evidence for' empty, 'Context for' filled, no lineage",
     ctxRows.length > 0 && ctxRows.every((r) => r.ev === "—" && r.cx !== "—" && r.lineage === "—"), `${ctxRows.length} context row(s)`);
  ok("evidence sources: 'Evidence for' filled", reg.filter((r) => r.role === "EVIDENCE").every((r) => r.ev && r.ev !== "—"));
  const btns = await page.$$eval("button, a", (e) => e.map((x) => x.textContent.trim()));
  ok("not approved: print button is a WORKING COPY print", btns.includes("Print working copy (not approved)") && !btns.includes("Download PDF"));
  ok("Edit (analyst) link", btns.includes("Edit (analyst)"));
  ok("Download Word (.docx) button", btns.includes("Download Word (.docx)"));

  // ---------------------------------------- 2. working-copy PDF + DOCX --
  await page.emulateMedia({ media: "print" });
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  const wpdf = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  fs.writeFileSync(path.join(OUT, "working_copy.pdf"), wpdf);
  const w = pdfPages(wpdf);
  ok("working-copy PDF = exactly 5 A4 landscape pages", w.count === 5 && w.boxes.every(([a, b]) => a === 842 && b === 595), `${w.count}`);
  await page.emulateMedia({ media: "screen" });
  const wdoc = await api.get(`${BASE}/api/command-brief/${WEEK}/docx`);
  ok("Word working copy at any status (200)", wdoc.status() === 200);
  ok("Word working copy is named WORKING_COPY", (wdoc.headers()["content-disposition"] || "").includes(`Command_Brief_${WEEK}_WORKING_COPY.docx`));
  ok("DOCX for a week without v2 brief → 404, not a broken file", (await api.get(`${BASE}/api/command-brief/${LEGACY}/docx`)).status() === 404);

  // ----------------------------------------------- 3. structured editor --
  console.log("Structured editor");
  await page.goto(`${BASE}/weekly/${WEEK}/command/edit`, { waitUntil: "networkidle" });
  ok("editor opens with status GENERATED", (await page.getAttribute("[data-draft-status]", "data-draft-status")) === "GENERATED");
  const blocks = await page.$$eval("[data-editor-block]", (e) => e.map((x) => x.getAttribute("data-editor-block")));
  ok("page 1 blocks: bottom line, primary KJ, secondary watch, map caption",
     ["bottom_line", "primary", "secondary_watch", "map_cee"].every((b) => blocks.includes(b)), blocks.join(","));
  ok("controlled metadata shown read-only (sources, HU, SIG, CONF)",
     (await page.$$eval("[data-editor-block=primary] [data-controlled]", (e) => e.map((x) => x.getAttribute("data-controlled"))))
       .filter((k) => ["sources", "hu_relevance.level", "significance", "confidence"].includes(k)).length >= 4);
  const firstKJ = await page.$eval("[data-editor-block=primary] [data-editor-item]", (e) => e.getAttribute("data-editor-item"));
  const kjKey = firstKJ.split("/")[1];
  const fid = `primary/${kjKey}/assessment`;
  ok("no free-form editing of sources (no textarea for a controlled field)",
     (await page.$$(`textarea[data-field="primary/${kjKey}/sources"]`)).length === 0);
  // Tulcsordulas-figyelmeztetes: minden 1. oldali mezo a kemeny limit alatt,
  // de joval a cel-hossz felett -> az 1. oldal nem fer ki. Utana Discard.
  const schema = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "config", "command_brief_presentation.json"), "utf-8"));
  const lim = {};
  for (const pg of schema.pages) for (const bl of pg.blocks) for (const f of bl.fields ?? []) {
    if (f.edit === "copy" && f.max_chars) lim[`${bl.id}/${f.key}`] = Math.ceil(f.max_chars * schema.draft.hard_limit_factor) - 4;
  }
  const filler = (n) => ("Hungary should watch this capability change closely. ").repeat(20).slice(0, n).replace(/\s+\S*$/, "") + ".";
  for (const id of await page.$$eval("[data-tab-page] textarea, textarea[data-field]", (e) => e.map((x) => x.getAttribute("data-field")))) {
    const [bl, , f] = id.split("/");
    if (lim[`${bl}/${f}`]) await page.fill(`textarea[data-field="${id}"]`, filler(lim[`${bl}/${f}`]));
  }
  await page.waitForTimeout(500);
  ok("editor warns when a page no longer fits", (await page.$$("[data-overflow-page='1']")).length === 1);
  await page.click("text=Discard");
  await page.waitForTimeout(300);
  ok("overflow warning clears after discarding", (await page.$$("[data-overflow-page]")).length === 0);

  const before = await page.$eval(`textarea[data-field="${fid}"]`, (e) => e.value);
  await page.fill(`textarea[data-field="${fid}"]`, NEW_TEXT);
  await page.waitForTimeout(300);
  ok("live preview shows the edited text", (await page.$eval(".cb-preview", (e) => e.innerText)).includes(NEW_TEXT.slice(0, 60)));
  await page.fill("[data-actor]", "Analyst A");
  await page.click("[data-action=save]");
  await page.waitForSelector("[data-editor-msg=ok]");
  ok("save → EDITING", (await page.getAttribute("[data-draft-status]", "data-draft-status")) === "EDITING");
  await page.click("[data-tab=audit]");
  const audit = await page.$eval("[data-audit-log]", (e) => e.innerText);
  ok("audit log: actor, field, previous and new value", audit.includes("Analyst A") && audit.includes(fid) && audit.includes(NEW_TEXT.slice(0, 40)) && audit.includes(before.slice(0, 30)));

  // Vedett mezok az API-n keresztul sem.
  const st = await (await api.get(`${BASE}/api/command-brief/${WEEK}/draft`)).json();
  const bad = await api.post(`${BASE}/api/command-brief/${WEEK}/draft`, { data: {
    actor: "x", expected_revision: st.draft.revision,
    ops: [{ type: "set", block: "primary", key: kjKey, field: "confidence", value: "high" }] } });
  ok("API refuses a controlled field (confidence) — 400", bad.status() === 400);
  const bad2 = await api.post(`${BASE}/api/command-brief/${WEEK}/draft`, { data: {
    actor: "x", expected_revision: st.draft.revision,
    ops: [{ type: "set", block: "source_register", key: "S-01", field: "published", value: "2026-01-01" }] } });
  ok("API refuses a source-register change — 400", bad2.status() === 400);
  const stale = await api.post(`${BASE}/api/command-brief/${WEEK}/draft`, { data: {
    actor: "x", expected_revision: 0, ops: [{ type: "status", to: "READY_FOR_APPROVAL" }] } });
  ok("stale revision → 409 conflict (no silent overwrite)", stale.status() === 409);
  ok("generated (analytical) text unchanged in the base brief", st.brief.page1.primary.find((k) => k.id === kjKey).assessment === before);

  await page.click("[data-tab='1']");
  await page.click("[data-action=submit]");
  await page.waitForFunction(() => document.querySelector("[data-draft-status]")?.getAttribute("data-draft-status") === "READY_FOR_APPROVAL");
  ok("submit → READY_FOR_APPROVAL", true);
  await page.fill("[data-actor]", "Duty Officer");
  await page.click("[data-action=approve]");
  await page.waitForFunction(() => document.querySelector("[data-draft-status]")?.getAttribute("data-draft-status") === "APPROVED");
  ok("approve → APPROVED", true);
  await page.click("[data-action=release]");
  await page.waitForFunction(() => document.querySelector("[data-draft-status]")?.getAttribute("data-draft-status") === "RELEASED");
  ok("release → RELEASED", true);
  const st2 = await (await api.get(`${BASE}/api/command-brief/${WEEK}/draft`)).json();
  const rel = st2.draft.releases.at(-1);
  ok("release R-1 recorded with approver and hash", rel && rel.release_no === 1 && rel.approved_by === "Duty Officer" && /^[0-9a-f]{64}$/.test(rel.content_hash));
  ok("release records template / methodology / HU model version", !!(rel.template_version && rel.hu_model_version));
  fs.writeFileSync(path.join(OUT, "published_brief.json"), JSON.stringify(rel.brief));

  // ------------------------------------------------- 4. released view --
  console.log("Released product");
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  const pg1 = await viewChecks(page, "release");
  ok("every page stamped RELEASED R-1", pg1.every((p) => /RELEASED R-1/.test(p.stamp)));
  ok("released view shows the edited publication copy", (await page.$eval(".cb", (e) => e.innerText)).includes(NEW_TEXT.slice(0, 60)));
  const btns2 = await page.$$eval("button, a", (e) => e.map((x) => x.textContent.trim()));
  ok("canonical: Download PDF button", btns2.includes("Download PDF"));
  for (let i = 0; i < 5; i++) {
    const el = (await page.$$(".cb-page"))[i];
    await el.screenshot({ path: path.join(OUT, `brief_page${i + 1}.png`) });
  }
  await page.emulateMedia({ media: "print" });
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  const pdf = await page.pdf({ preferCSSPageSize: true, printBackground: true });
  fs.writeFileSync(path.join(OUT, "command_brief.pdf"), pdf);
  const a = pdfPages(pdf);
  ok("canonical PDF = exactly 5 pages (4 executive + Sources & Legend)", a.count === 5, `${a.count}`);
  ok("all PDF pages A4 landscape", a.boxes.every(([x, y]) => x === 842 && y === 595), JSON.stringify(a.boxes));
  await page.emulateMedia({ media: "screen" });
  const resp = await api.get(`${BASE}/api/command-brief/${WEEK}/docx`);
  ok("DOCX of the release 200", resp.status() === 200);
  ok("DOCX content type", (resp.headers()["content-type"] || "").includes("wordprocessingml"));
  ok("DOCX named after the release", (resp.headers()["content-disposition"] || "").includes(`Command_Brief_${WEEK}_R1.docx`));
  fs.writeFileSync(path.join(OUT, "command_brief.docx"), await resp.body());

  // Szerkesztes kiadas utan: a kiadas marad, a munkapeldany kulon latszik.
  const st3 = await (await api.get(`${BASE}/api/command-brief/${WEEK}/draft`)).json();
  const after = await api.post(`${BASE}/api/command-brief/${WEEK}/draft`, { data: {
    actor: "Analyst A", expected_revision: st3.draft.revision,
    ops: [{ type: "set", block: "bottom_line", key: "#0", field: "text", value: "A post-release working sentence." }] } });
  ok("edit after release → EDITING, release kept", after.status() === 200 && (await after.json()).draft.releases.length === 1);
  await page.goto(`${BASE}/weekly/${WEEK}/command`, { waitUntil: "networkidle" });
  ok("public view still shows R-1 and flags the newer draft",
     (await page.$eval("[data-brief-view]", (e) => e.getAttribute("data-brief-view"))) === "release" &&
     (await page.textContent("[data-brief-view]")).includes("newer draft"));

  // ------------------------------------------------- 5. Word template --
  console.log("Word template");
  const t = await api.get(`${BASE}/api/command-brief/template`);
  ok("Word template (.dotx) download 200", t.status() === 200);
  ok("template content type", (t.headers()["content-type"] || "").includes("wordprocessingml.template"));
  fs.writeFileSync(path.join(OUT, "Command_Air_Intelligence_Brief.dotx"), await t.body());

  // ---------------------------------------- 6. existing routes / products --
  console.log("Separate products and existing routes");
  await page.goto(`${BASE}/weekly/${WEEK}`, { waitUntil: "networkidle" });
  ok("detailed weekly report does not embed the brief", (await page.$$(".cb-page")).length === 0);
  ok("detailed report links to the Command Brief", (await page.textContent("body")).includes("Command brief"));
  ok("detailed report anchors intact (D-01)", !!(await page.$("#D-01")));
  for (const [url, needle] of [[`/weekly/${LEGACY}`, "Bottom line"], [`/weekly/${LEGACY}/command`, "no v2 Command Brief"],
                               [`/weekly/${WEEK}/brief`, "Briefing"], ["/weekly", "Weekly report"],
                               ["/weekly/command-brief", "Command Air Intelligence Brief"],
                               ["/weekly/command-brief/edit", "Edit Command Brief"]]) {
    const r = await page.goto(`${BASE}${url}`, { waitUntil: "networkidle" });
    const tx = await page.textContent("body");
    ok(`${url} renders (${r.status()})`, r.status() === 200 && tx.includes(needle));
  }
  await browser.close();
  console.log(fails.length ? `\n${fails.length} E2E check(s) FAILED` : "\nAll browser E2E checks passed.");
  process.exit(fails.length ? 1 : 0);
})();
