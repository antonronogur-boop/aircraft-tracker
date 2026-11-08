// WORD (.docx) EXPORT — ugyanabbol a kanonikus Command Brief adatmodellbol,
// mint a web nezet es a PDF. NEM a PDF-bol konvertal: minden cimsor,
// bekezdes, tablazat, forrasjegyzek es jelmagyarazat valodi, szerkesztheto
// Word-szoveg valodi stilusokkal. Csak a ket terkep kep (nagy felbontasu
// PNG ugyanabbol az SVG-bol, amit a web is rajzol).
//
// A Word-fajl szerkesztese NEM modositja a rendszerben tarolt jelentest: ez
// egy letoltott masolat ("EDITABLE EXPORT").
import {
  AlignmentType, BorderStyle, Document, ExternalHyperlink, Footer, Header, HeadingLevel,
  ImageRun, LevelFormat, PageNumber, PageOrientation, Packer, Paragraph, ShadingType,
  Table, TableCell, TableRow, TextRun, WidthType,
} from "docx";
import type { CommandBriefV2, SourceEntry, BriefItem } from "@/lib/briefTypes";
import { HORIZON_LABEL } from "@/lib/briefTypes";
import { ceeMapSvg, globalMapSvg } from "@/lib/briefMaps";
import { DOCX_STYLES } from "@/lib/docxStyles";

// A4 fekvo, 15 mm margo -> tartalomszelesseg DXA-ban.
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 850;
const CONTENT_W = PAGE_H - 2 * MARGIN; // fekvoben a szelesseg a 16838

type Svg2Png = (svg: string, width: number) => Promise<Buffer>;

const HU_COLOR: Record<string, string> = {
  HIGH: "B91C1C", MEDIUM: "C2410C", LOW: "A16207", MINIMAL: "64748B",
};

// ------------------------------------------------------------ primitives --
function p(text: string, opts: { bold?: boolean; italics?: boolean; style?: string; color?: string;
                                 size?: number; after?: number } = {}) {
  return new Paragraph({
    style: opts.style,
    spacing: opts.after != null ? { after: opts.after } : undefined,
    children: [new TextRun({ text, bold: opts.bold, italics: opts.italics, color: opts.color, size: opts.size })],
  });
}

function labelled(label: string, text: string, extra: (TextRun | ExternalHyperlink)[] = []) {
  return new Paragraph({
    spacing: { after: 40 },
    children: [new TextRun({ text: `${label}: `, bold: true }), new TextRun(text), ...extra],
  });
}

function srcRuns(ids: string[], idx: Map<string, SourceEntry>, prefix = "Sources: "): (TextRun | ExternalHyperlink)[] {
  if (!ids?.length) return [];
  const out: (TextRun | ExternalHyperlink)[] = [new TextRun({ text: prefix, color: "475569", size: 17 })];
  ids.forEach((id, i) => {
    if (i) out.push(new TextRun({ text: " · ", color: "475569", size: 17 }));
    const s = idx.get(id);
    out.push(s
      ? new ExternalHyperlink({ link: s.url, children: [new TextRun({ text: id, style: "Hyperlink", size: 17 })] })
      : new TextRun({ text: id, size: 17 }));
    if (s && s.tier_rank === 1) out.push(new TextRun({ text: " (official)", color: "64748B", size: 15 }));
  });
  return out;
}

function huRun(level?: string) {
  return new TextRun({ text: `HU ${level ?? "—"}`, bold: true, color: HU_COLOR[level ?? ""] ?? "334155" });
}

function metaLine(parts: (TextRun)[]) {
  return new Paragraph({ spacing: { after: 40 }, children: parts });
}

function bullet(children: (TextRun | ExternalHyperlink)[]) {
  return new Paragraph({ numbering: { reference: "bullets", level: 0 }, children });
}

function cell(children: (TextRun | ExternalHyperlink)[] | string, width: number, header = false) {
  const runs = typeof children === "string"
    ? [new TextRun({ text: children, bold: header, color: header ? "FFFFFF" : undefined })]
    : children;
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: header ? { type: ShadingType.CLEAR, color: "auto", fill: "1E293B" } : undefined,
    children: [new Paragraph({ children: runs })],
  });
}

function table(headers: string[], widthsPct: number[], rows: ((TextRun | ExternalHyperlink)[] | string)[][]) {
  const total = CONTENT_W;
  const widths = widthsPct.map((w) => Math.floor((total * w) / 100));
  widths[widths.length - 1] += total - widths.reduce((a, b) => a + b, 0);
  return new Table({
    style: "BriefTable",
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i])) })),
    ],
  });
}

async function image(svg: string, svgW: number, svgH: number, displayW: number, svg2png: Svg2Png) {
  const png = await svg2png(svg, 2400);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new ImageRun({
      type: "png", data: png,
      transformation: { width: displayW, height: Math.round((displayW * svgH) / svgW) },
      altText: { title: "Map", description: "Map", name: "map" },
    })],
  });
}

function noDirect(ctx: string[] | undefined, idx: Map<string, SourceEntry>): (TextRun | ExternalHyperlink)[] {
  if (!ctx?.length) return [];
  return [new TextRun({ text: "No direct source — claim appears only in the body of ", color: "92400E", size: 16 }),
    ...srcRuns(ctx, idx, ""), new TextRun({ text: " (context, not evidence)", color: "92400E", size: 16 })];
}

function itemParas(it: BriefItem, idx: Map<string, SourceEntry>) {
  return [
    new Paragraph({ spacing: { before: 80, after: 20 }, keepNext: true, children: [
      new TextRun({ text: `${it.country} — `, bold: true }), new TextRun({ text: it.what_changed, bold: true }),
      new TextRun({ text: `  (${it.domain ?? ""})`, color: "64748B", size: 17 })] }),
    ...(it.assessment ? [labelled("Assessment", it.assessment)] : []),
    metaLine([huRun(it.hu_relevance), new TextRun(` · SIG ${it.significance}/5 · CONF ${(it.confidence ?? "—").toUpperCase()} · ${HORIZON_LABEL(it.horizon)}   `),
              ...(it.sources.length ? srcRuns(it.sources, idx) : noDirect(it.context_sources, idx)) as TextRun[]]),
  ];
}

// ---------------------------------------------------------------- build --
export async function buildCommandBriefDocx(b: CommandBriefV2, svg2png: Svg2Png): Promise<Buffer> {
  const idx = new Map(b.page5.sources.map((s) => [s.id, s]));
  const m = b.meta;
  const body: (Paragraph | Table)[] = [];

  // --- cimlap-fejresz ---
  body.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(b.title)] }));
  body.push(p(`Hungary-focused air power intelligence · ${b.week_label} · ${b.classification}`, { style: "Subtitle" }));
  body.push(new Paragraph({
    border: { top: { style: BorderStyle.SINGLE, size: 8, color: "B45309", space: 2 },
              bottom: { style: BorderStyle.SINGLE, size: 8, color: "B45309", space: 2 } },
    shading: { type: ShadingType.CLEAR, color: "auto", fill: "FEF3C7" },
    spacing: { after: 60 },
    children: [new TextRun({ text: b.status_line, bold: true, color: "78350F" })],
  }));
  body.push(p("The canonical publication is the released PDF / web report. Editing this file does not change the report stored in Aircraft Tracker.", { style: "Caption" }));
  body.push(table(["Field", "Value"], [28, 72], [
    ["Report week", m.week_label],
    ["Reporting window", m.window_label ?? `${m.period_start} → ${m.period_end}`],
    ["Generated", m.generated_utc ?? "—"],
    ["Methodology version", m.methodology_version ?? "—"],
    ["HU relevance model version", m.hu_model_version ?? "—"],
    ["Brief version", m.brief_version ?? "v2"],
    ["Revision", m.revision ? `${m.revision.number}: ${m.revision.reason ?? ""} (${m.revision.restated_utc ?? ""})` : "none"],
    ["Report status", m.report_status ?? "—"],
    ["Source traceability", `${b.page5.sources.length} original sources (S-xx), hyperlinked in section 5`],
  ]));

  // --- 1. bottom line + primary KJ ---
  const p1 = b.page1;
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("1. Hungary Air Intelligence Bottom Line")] }));
  const blRuns: (TextRun | ExternalHyperlink)[] = [];
  p1.bottom_line.sentences.forEach((s, i) => {
    blRuns.push(new TextRun((i ? " " : "") + s.text));
    if (s.sources.length) blRuns.push(new TextRun(" "), ...srcRuns(s.sources, idx, "["), new TextRun({ text: "]", color: "475569", size: 17 }));
  });
  body.push(new Paragraph({ spacing: { after: 60 }, children: blRuns }));
  body.push(p(p1.bottom_line.origin === "executive_synthesis"
    ? "Executive synthesis — every sentence cites its sources; numbers and countries are checked against them."
    : "Built from the assessed judgements, developments and coverage audit.", { style: "Caption" }));

  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Primary key judgements")] }));
  body.push(p("Ranked by Hungary relevance → air-power significance → confidence → immediacy.", { style: "Caption" }));
  if (!p1.primary.length && p1.primary_empty) body.push(p(p1.primary_empty));
  for (const k of p1.primary) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(`${k.id} — ${k.statement}`)] }));
    body.push(metaLine([huRun(k.hu_relevance.level), new TextRun(` · SIG ${k.significance}/5 · CONF ${(k.confidence ?? "—").toUpperCase()} · ${HORIZON_LABEL(k.horizon)}`),
      ...(k.origin === "executive_synthesis" ? [new TextRun({ text: " · EXECUTIVE SYNTHESIS", bold: true, color: "6D28D9" })] : [])]));
    body.push(labelled("What changed", k.what_changed));
    body.push(labelled("Assessment", k.assessment));
    body.push(labelled("Why Hungary should care", k.why_hungary));
    body.push(labelled("Next observable", k.next_observable));
    body.push(labelled("What would make this wrong", k.alternative_explanation));
    body.push(new Paragraph({ spacing: { after: 100 }, children: srcRuns(k.sources, idx) }));
  }
  if (p1.secondary_watch.length) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Secondary air power watch")] }));
    body.push(p("Globally significant, but of low direct relevance to Hungary.", { style: "Caption" }));
    for (const s of p1.secondary_watch) {
      body.push(bullet([new TextRun(s.line), new TextRun({ text: `  SIG ${s.significance}/5 · HU ${s.hu_level ?? "—"}  `, color: "64748B", size: 17 }),
        ...srcRuns(s.sources, idx, "")]));
    }
  }
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Regional air picture")] }));
  body.push(await image(ceeMapSvg(p1.map_cee), 600, 470, 400, svg2png));
  body.push(p(`Figure 1 — ${p1.map_cee.caption ?? ""}`, { style: "Caption" }));

  // --- 2. regio ---
  const p2 = b.page2;
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("2. Immediate & Near-Regional Air Picture")] }));
  body.push(p("Non-NATO priority · Hungary's neighbours · extended regional NATO — material changes only.", { style: "Caption" }));
  if (p2.rows.length) {
    body.push(table(["Country", "What changed", "Capability / operational effect", "HU relevance", "SIG", "CONF", "Next observable", "Sources"],
      [10, 22, 20, 14, 5, 7, 14, 8],
      p2.rows.map((r) => [
        [new TextRun({ text: r.country, bold: true })],
        r.what_changed, r.effect,
        [huRun(r.hu_relevance), new TextRun({ text: ` ${r.hu_why ?? ""}`, size: 16 })],
        `${r.significance}/5`, `${r.confidence ?? "—"} · ${HORIZON_LABEL(r.horizon)}`,
        r.next_observable ?? "—", r.sources.length ? srcRuns(r.sources, idx, "") : noDirect(r.context_sources, idx),
      ])));
  } else {
    body.push(p("NO MATERIAL CHANGE IDENTIFIED in the immediate and near region.", { bold: true }));
  }
  body.push(labelled("No material change identified", p2.no_material_change.map((x) => `${x.name} (${x.coverage.toLowerCase()})`).join(" · ") || "—"));
  body.push(labelled("Collection gap", (p2.collection_gap.join(" · ") || "—") + (p2.collection_gap.length ? ". Absence of reporting is not evidence of inactivity." : "")));
  if (b.coverage_summary?.priority?.length) {
    body.push(labelled("Coverage (60 days)", b.coverage_summary.priority.map((c) => `${c.name} ${c.status}${c.official_source ? "" : "*"}`).join(" · ")));
    body.push(p("* no official air force / MoD source in collection.", { style: "Caption" }));
  }
  if (p2.collection_requirements.length) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Regional collection requirements")] }));
    body.push(p("Gap → intelligence question → desired observable.", { style: "Caption" }));
    body.push(table(["Country", "Status", "Gap", "Intelligence question", "Desired observable"], [12, 9, 19, 30, 30],
      p2.collection_requirements.map((q) => [[new TextRun({ text: q.country, bold: true })], q.status, q.gap, q.question, q.observable])));
  }
  if (p2.note) body.push(p(p2.note, { style: "Caption" }));

  // --- 3. tagabb kep ---
  const p3 = b.page3;
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("3. Extended Air Power Picture")] }));
  for (const s of p3.sections) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(`${s.title}${s.coverage ? ` (coverage ${s.coverage.toLowerCase()})` : ""}`)] }));
    if (!s.items.length) body.push(p(s.empty ?? "NO MATERIAL CHANGE IDENTIFIED", { bold: true, color: "475569" }));
    for (const it of s.items) body.push(...itemParas(it, idx));
  }
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Capability change / maturity matrix")] }));
  const cols = p3.maturity.columns;
  body.push(table(["Development", "HU", ...cols], [26, 10, ...cols.map(() => 64 / cols.length)],
    p3.maturity.rows.map((r) => {
      const at = r.column ? cols.indexOf(r.column) : -1;
      return [r.label + ` (${r.country})`, r.hu_relevance ?? "—",
        ...cols.map((c, i) => r.withdrawal ? (i === 0 ? `withdrawal — ${r.stage}` : "")
          : i === at ? [new TextRun({ text: r.stage, bold: true })] : i < at ? "✓" : "")];
    })));
  body.push(p(`${p3.maturity.caption ?? ""} ✓ = earlier stage implied, not observed.`, { style: "Caption" }));
  const ct = p3.change_table;
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(`Executive change table${ct.previous_week ? ` — against ${ct.previous_week} (published)` : ""}`)] }));
  if (ct.rows.length) {
    body.push(table(["Priority", "Country", "Capability", "Previous", "Current", "Delta", "HU relevance", "Confidence"],
      [7, 12, 18, 15, 15, 17, 8, 8],
      ct.rows.map((r) => [String(r.priority), r.country, r.capability, r.previous ?? "—", r.current ?? "—", r.delta ?? "—", r.hu_relevance ?? "—", r.confidence ?? "—"])));
  } else {
    body.push(p(ct.note || "No prior published report — the comparison begins next period."));
  }

  // --- 4. globalis ---
  const p4 = b.page4;
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("4. Global Strategic Air Power Watch")] }));
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Global strategic")] }));
  if (!p4.global.items.length) body.push(p(p4.global.empty ?? "NO MATERIAL CHANGE IDENTIFIED", { bold: true, color: "475569" }));
  for (const it of p4.global.items) body.push(...itemParas(it, idx));
  body.push(await image(globalMapSvg(p4.map_global), 800, 410, 560, svg2png));
  body.push(p(`Figure 2 — ${p4.map_global.caption ?? ""}`, { style: "Caption" }));
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Priority intelligence watch")] }));
  if (!p4.priority_watch.length) body.push(p("No priority watch item this week."));
  p4.priority_watch.forEach((w, i) => {
    body.push(new Paragraph({ keepNext: true, spacing: { before: 60, after: 20 }, children: [
      new TextRun({ text: `${i + 1}. ${w.question}`, bold: true }),
      ...(w.hu_relevance ? [new TextRun("  "), huRun(w.hu_relevance)] : [])] }));
    if (w.why) body.push(labelled("Why", w.why));
    body.push(labelled("Next observable", `${w.next_observable ?? "—"} (horizon ${w.horizon ?? "—"}, impact ${w.impact ?? "—"})`));
  });
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Intelligence gaps")] }));
  for (const g of p4.intelligence_gaps) {
    body.push(bullet([new TextRun(g.text), ...(g.origin === "coverage_audit" ? [new TextRun({ text: " (coverage audit)", color: "64748B", size: 17 })] : [])]));
  }
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Outlook & expected observables — next 7–30 days")] }));
  for (const o of p4.outlook) {
    body.push(bullet([new TextRun({ text: o.subject, bold: true }), new TextRun({ text: ` (${o.country}) — `, color: "64748B" }),
      new TextRun(o.expected_observable), new TextRun("  "), ...srcRuns(o.sources, idx, "")]));
  }
  if (p4.outlook_note) body.push(p(p4.outlook_note, { style: "Caption" }));

  // --- 5. forrasok + jelmagyarazat ---
  const p5 = b.page5;
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("5. Sources & Legend")] }));
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(p5.register_title ?? "Source register")] }));
  body.push(table(["ID", "Source · tier", "Title (original language)", "Published", "Role", "Country", "Lang", "Lineage", "Used by"],
    [5, 15, 31, 9, 12, 8, 5, 6, 9],
    p5.sources.map((s) => [
      [new TextRun({ text: s.id, bold: true })],
      [new TextRun(s.source_name), new TextRun({ text: ` (${s.tier} · ${s.source_type})`, color: "64748B", size: 15 })],
      [new ExternalHyperlink({ link: s.url, children: [new TextRun({ text: s.title, style: "Hyperlink" })] }),
       ...(s.note ? [new TextRun({ text: ` — ${s.note}`, color: "64748B", size: 15 })] : [])],
      (s.published ?? "not recorded") + (s.published_basis && s.published_basis !== "feed" ? ` (${s.published_basis})` : ""),
      s.role, s.country, s.language, s.lineage,
      s.used_by.join(", ") || "—",
    ])));
  if (p5.source_note) body.push(p(p5.source_note, { style: "Caption" }));
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Legend")] }));
  for (const sec of p5.legend) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(sec.title)] }));
    for (const [term, text] of sec.items) {
      body.push(new Paragraph({ spacing: { after: 30 }, children: [new TextRun({ text: `${term} — `, bold: true }), new TextRun(text)] }));
    }
  }
  body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Analytical discipline")] }));
  for (const x of p5.principles) body.push(bullet([new TextRun(x)]));
  body.push(p(b.micro_legend, { style: "Caption" }));

  const doc = new Document({
    creator: "Aircraft Tracker", title: `${b.title} ${b.week_label}`,
    description: `${b.status_line}. Generated ${m.generated_utc ?? ""}; methodology ${m.methodology_version ?? ""}; HU model ${m.hu_model_version ?? ""}.`,
    externalStyles: DOCX_STYLES,
    numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 240 } } } }] }] },
    sections: [{
      properties: { page: { size: { width: PAGE_W, height: PAGE_H, orientation: PageOrientation.LANDSCAPE },
                            margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN, header: 400, footer: 400 } } },
      headers: { default: new Header({ children: [new Paragraph({ style: "Header", children: [
        new TextRun(`Command Air Intelligence Brief · ${b.week_label} · ${b.classification} · ${b.status_line}`)] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ style: "Footer", children: [
        new TextRun(`${b.micro_legend}   ·   Page `), new TextRun({ children: [PageNumber.CURRENT] }),
        new TextRun(" of "), new TextRun({ children: [PageNumber.TOTAL_PAGES] })] })] }) },
      children: body,
    }],
  });
  return stripFolderEntries(await Packer.toBuffer(doc));
}

// A ZIP mappa-bejegyzesei (word/, word/_rels/ ...) miatt a felhos
// tarsszerkeszto szolgaltatasok egy resze megtagadja a fajlt. Csak a
// fajl-bejegyzeseket irjuk ujra, valtozatlan tartalommal.
async function stripFolderEntries(buf: Buffer): Promise<Buffer> {
  const JSZip = (await import("jszip")).default;
  const src = await JSZip.loadAsync(buf);
  const out = new JSZip();
  const names = Object.keys(src.files).filter((n) => !src.files[n].dir);
  // [Content_Types].xml elol — a Word igy varja.
  names.sort((a, b) => (a === "[Content_Types].xml" ? -1 : b === "[Content_Types].xml" ? 1 : 0));
  for (const n of names) {
    out.file(n, await src.files[n].async("uint8array"), { createFolders: false });
  }
  return out.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}
