// WORD (.docx) EXPORT + WORD TEMPLATE (.dotx) — ugyanabbol a kanonikus
// Command Brief adatmodellbol es ugyanabbol a presentation schemabol, mint a
// web nezet es a PDF. NEM a PDF-bol konvertal: minden cimsor, bekezdes,
// tablazat, forrasjegyzek es jelmagyarazat valodi, szerkesztheto Word-szoveg
// valodi stilusokkal. A ket terkep kep (nagy felbontasu PNG ugyanabbol az
// SVG-bol, amit a web rajzol), kep-tartalomvezerloben.
//
// TARTALOMVEZERLOK (content controls): minden schema-mezo egy stabil
// cimkeju (w:tag) Word content control — CB_BOTTOM_LINE_1, CB_KJ1_TITLE,
// CB_KJ1_ASSESSMENT, CB_KJ1_SOURCES ... Igy UGYANAZ a szerkezet:
//   * kezzel kitoltheto (a .dotx template-ben helyorzo szoveggel),
//   * programbol feltoltheto (ez az export),
//   * kesobb ujrageneralhato / kiolvashato (a cimkek alapjan).
// A fix design-elemek (cimsorok, mezo-cimkek, jelmagyarazat, statuszsor)
// tartalom-zarolt vezerlokben vannak, hogy veletlenul ne modosuljanak.
//
// A Word-fajl MUNKAPELDANY: szerkesztese nem modositja a rendszerben tarolt
// jelentest; a kanonikus termek a kiadott PDF.
import {
  AlignmentType, Bookmark, BorderStyle, Document, ExternalHyperlink, Footer, Header, HeadingLevel,
  ImageRun, LevelFormat, PageNumber, PageOrientation, Packer, Paragraph, SectionType, ShadingType,
  Table, TableCell, TableRow, TextRun, WidthType, type ParagraphChild,
} from "docx";
import type { CommandBriefV2, SourceEntry, BriefItem } from "@/lib/briefTypes";
import { HORIZON_LABEL } from "@/lib/briefTypes";
import { ceeMapSvg, globalMapSvg } from "@/lib/briefMaps";
import { DOCX_STYLES } from "@/lib/docxStyles";
import { PRESENTATION, TEMPLATE_VERSION, block as schemaBlock, page as schemaPage, slotTag } from "@/lib/presentation";
import { lineageRegister } from "@/lib/briefDraft";

const MM = 56.6929; // DXA / mm
const PAGE_W = 11906, PAGE_H = 16838;
const MARGIN = Math.round(PRESENTATION.document.word_page.margin_mm.left * MM);
const CONTENT_W = PAGE_H - 2 * MARGIN; // fekvoben a szelesseg a 16838

export type Svg2Png = (svg: string, width: number) => Promise<Buffer>;
type Run = ParagraphChild;

const HU_COLOR: Record<string, string> = Object.fromEntries(
  Object.entries(PRESENTATION.colours.hu).map(([k, v]) => [k, v.fill.replace("#", "").toUpperCase()]));

// ------------------------------------------------------- content controls --
// A docx konyvtar nem ir content controlt; a mezoket konyvjelzokbe tesszuk,
// es a csomagolas utan a konyvjelzoket w:sdt elemekre csereljuk.
//   CBE__<tag>  szerkesztheto publikacios mezo   (lock: sdtLocked)
//   CBC__<tag>  kontrollalt metaadat            (export: contentLocked, template: sdtLocked)
//   CBF__<n>    fix design-elem                 (sdtContentLocked)
//   CBP__<tag>  kep (terkep)                    (picture control, sdtLocked)
//   CBWS__/CBWE__<tag>  csoportosito nyito/zaro jelolo (pl. a teljes bottom line)
interface Ctx {
  template: boolean;
  idx: Map<string, SourceEntry>;
  alias: Map<string, string>;
  fixedN: number;
}

function ctl(ctx: Ctx, kind: "E" | "C" | "P", tag: string | undefined, alias: string, children: Run[]): Run[] {
  if (!tag) return children;
  ctx.alias.set(tag, alias);
  return [new Bookmark({ id: `CB${kind}__${tag}`, children })];
}

/** Csoportosito vezerlo mas vezerlok kore. A docx konyvtar nem tud
 *  egymasba agyazott konyvjelzot irni, ezert ket ures jelolo (nyito /
 *  zaro) fogja kozre a tartalmat. */
function wrap(ctx: Ctx, tag: string | undefined, alias: string, children: Run[]): Run[] {
  if (!tag) return children;
  ctx.alias.set(tag, alias);
  return [new Bookmark({ id: `CBWS__${tag}`, children: [] }), ...children,
          new Bookmark({ id: `CBWE__${tag}`, children: [] })];
}

function fixed(ctx: Ctx, children: Run[]): Run[] {
  ctx.fixedN += 1;
  return [new Bookmark({ id: `CBF__${ctx.fixedN}`, children })];
}

const tr = (text: string, o: { bold?: boolean; italics?: boolean; color?: string; size?: number; style?: string } = {}) =>
  new TextRun({ text, bold: o.bold, italics: o.italics, color: o.color, size: o.size, style: o.style });

function para(children: Run[], o: { style?: string; after?: number; before?: number; keepNext?: boolean;
                                     heading?: (typeof HeadingLevel)[keyof typeof HeadingLevel]; numbering?: boolean } = {}) {
  return new Paragraph({
    style: o.style, heading: o.heading, keepNext: o.keepNext,
    spacing: o.after != null || o.before != null ? { after: o.after, before: o.before } : undefined,
    numbering: o.numbering ? { reference: "bullets", level: 0 } : undefined,
    children,
  });
}

function heading(ctx: Ctx, level: 1 | 2 | 3, text: string) {
  const h = level === 1 ? HeadingLevel.HEADING_1 : level === 2 ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3;
  return para(fixed(ctx, [tr(text)]), { heading: h });
}

function caption(ctx: Ctx, text: string, tag?: string, alias?: string) {
  return para(tag ? ctl(ctx, "E", tag, alias ?? "Caption", [tr(text)]) : fixed(ctx, [tr(text)]), { style: "Caption" });
}

/** "Cimke: szoveg" — a cimke fix, a szoveg szerkesztheto mezo. */
function labelled(ctx: Ctx, label: string, text: string, tag?: string, alias?: string, extra: Run[] = []) {
  return para([...fixed(ctx, [tr(`${label}: `, { bold: true })]),
               ...ctl(ctx, "E", tag, alias ?? label, [tr(text)]), ...extra], { after: 40 });
}

function srcRuns(ctx: Ctx, ids: string[], prefix = "Sources: "): Run[] {
  if (!ids?.length) return [];
  const out: Run[] = [];
  ids.forEach((id, i) => {
    if (i) out.push(tr(" · ", { color: "475569", size: 17 }));
    const s = ctx.idx.get(id);
    out.push(s
      ? new ExternalHyperlink({ link: s.url, children: [tr(id, { style: "Hyperlink", size: 17 })] })
      : tr(id, { size: 17 }));
    if (s && s.tier_rank === 1) out.push(tr(" (official)", { color: "64748B", size: 15 }));
  });
  return prefix ? [tr(prefix, { color: "475569", size: 17 }), ...out] : out;
}

function sourcesField(ctx: Ctx, ids: string[], tag: string | undefined, alias: string, prefix = "Sources: "): Run[] {
  const runs = srcRuns(ctx, ids, "");
  if (!runs.length) return [];
  return [...(prefix ? fixed(ctx, [tr(prefix, { color: "475569", size: 17 })]) : []), ...ctl(ctx, "C", tag, alias, runs)];
}

function huRuns(ctx: Ctx, level: string | undefined, tag?: string, alias = "HU relevance"): Run[] {
  // A szin MELLETT mindig ott a szoveges cimke (HU HIGH): szurkearnyalatos
  // nyomtatasban is ertelmezheto.
  return [tr("HU ", { bold: true, color: HU_COLOR[level ?? ""] ?? "334155" }),
          ...ctl(ctx, "C", tag, alias, [tr(level ?? "—", { bold: true, color: HU_COLOR[level ?? ""] ?? "334155" })])];
}

function cell(children: Run[] | string, width: number, header = false) {
  const runs = typeof children === "string" ? [tr(children, { bold: header, color: header ? "FFFFFF" : undefined })] : children;
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: header ? { type: ShadingType.CLEAR, color: "auto", fill: "1E293B" } : undefined,
    children: [new Paragraph({ children: runs })],
  });
}

function table(ctx: Ctx, headers: string[], widthsPct: number[], rows: (Run[] | string)[][]) {
  const total = CONTENT_W;
  const widths = widthsPct.map((w) => Math.floor((total * w) / 100));
  widths[widths.length - 1] += total - widths.reduce((a, b) => a + b, 0);
  return new Table({
    style: "BriefTable",
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(fixed(ctx, [tr(h, { bold: true, color: "FFFFFF" })]), widths[i], true)) }),
      ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i])) })),
    ],
  });
}

async function figure(ctx: Ctx, tag: string, alias: string, svg: string, svgW: number, svgH: number,
                      displayW: number, svg2png: Svg2Png) {
  const png = await svg2png(svg, (schemaBlock(tag === "CB_MAP_CEE" ? "map_cee" : "map_global")?.figure?.width_px) ?? 2400);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    children: ctl(ctx, "P", tag, alias, [new ImageRun({
      type: "png", data: png,
      transformation: { width: displayW, height: Math.round((displayW * svgH) / svgW) },
      altText: { title: alias, description: alias, name: tag },
    })]),
  });
}

function placeholderSvg(w: number, h: number, text: string) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
<rect x="1" y="1" width="${w - 2}" height="${h - 2}" fill="#f1f5f9" stroke="#64748b" stroke-width="2" stroke-dasharray="10 6"/>
<text x="${w / 2}" y="${h / 2}" font-family="DejaVu Sans" font-size="${Math.round(w / 34)}" fill="#334155" text-anchor="middle">${text}</text>
</svg>`;
}

function noDirect(ctx: Ctx, cs: string[] | undefined): Run[] {
  if (!cs?.length) return [];
  return [tr("No direct source — claim appears only in the body of ", { color: "92400E", size: 16 }),
    ...srcRuns(ctx, cs, ""), tr(" (context, not evidence)", { color: "92400E", size: 16 })];
}

const F = (blockId: string, key: string) => schemaBlock(blockId)?.fields?.find((f) => f.key === key);
const T = (blockId: string, key: string, n: number) => slotTag(F(blockId, key)?.tag, n);
const L = (blockId: string, key: string) => F(blockId, key)?.label ?? key;

function itemParas(ctx: Ctx, blockId: string, it: BriefItem, n: number) {
  return [
    para([tr(`${it.country} — `, { bold: true }),
          ...ctl(ctx, "E", T(blockId, "what_changed", n), `${blockId} ${n} · What changed`, [tr(it.what_changed, { bold: true })]),
          tr(`  (${it.domain ?? ""})`, { color: "64748B", size: 17 })], { before: 80, after: 20, keepNext: true }),
    ...(it.assessment ? [labelled(ctx, L(blockId, "assessment"), it.assessment, T(blockId, "assessment", n), `${blockId} ${n} · Assessment`)] : []),
    para([...huRuns(ctx, it.hu_relevance), tr(` · SIG ${it.significance}/5 · CONF ${(it.confidence ?? "—").toUpperCase()} · ${HORIZON_LABEL(it.horizon)}   `),
          ...(it.sources.length ? sourcesField(ctx, it.sources, T(blockId, "sources", n), `${blockId} ${n} · Sources`) : noDirect(ctx, it.context_sources))],
         { after: 40 }),
  ];
}

// ---------------------------------------------------------------- build --
export interface DocxOptions { template?: boolean }

export async function buildCommandBriefDocx(b: CommandBriefV2, svg2png: Svg2Png, opts: DocxOptions = {}): Promise<Buffer> {
  const ctx: Ctx = { template: !!opts.template, idx: new Map(b.page5.sources.map((s) => [s.id, s])),
                     alias: new Map(), fixedN: 0 };
  const m = b.meta;
  const d = m.draft;
  const body: (Paragraph | Table)[] = [];
  const doc0 = PRESENTATION.document;

  // --- cimlap-fejresz ---
  body.push(para(fixed(ctx, [tr(doc0.title)]), { heading: HeadingLevel.TITLE }));
  body.push(para([...fixed(ctx, [tr("Hungary-focused air power intelligence · ")]),
                  ...ctl(ctx, "C", "CB_WEEK", "Report week", [tr(b.week_label)]),
                  ...fixed(ctx, [tr(` · ${b.classification}`)])], { style: "Subtitle" }));
  body.push(new Paragraph({
    border: { top: { style: BorderStyle.SINGLE, size: 8, color: "B45309", space: 2 },
              bottom: { style: BorderStyle.SINGLE, size: 8, color: "B45309", space: 2 } },
    shading: { type: ShadingType.CLEAR, color: "auto", fill: "FEF3C7" },
    spacing: { after: 60 },
    children: fixed(ctx, [tr(ctx.template ? `${doc0.status_line} — MANUAL FALLBACK TEMPLATE v${TEMPLATE_VERSION}` : b.status_line, { bold: true, color: "78350F" })]),
  }));
  body.push(caption(ctx, ctx.template
    ? "Fallback when the web editor is unavailable: fill every field (click a grey placeholder and type), check the sources, Save As .docx, export PDF. Follow docs/COMMAND_BRIEF_SOP.md."
    : `${doc0.word_note} Editing this file does not change the report stored in Aircraft Tracker.`));
  const statusTxt = d ? (d.release_no ? `RELEASED R-${d.release_no}` : `${d.status.replace(/_/g, " ")} · draft rev ${d.revision}${d.canonical ? "" : " · NOT APPROVED"}`) : "GENERATED · NOT APPROVED";
  const metaRows: [string, string, string][] = [
    ["Report week", m.week_label, "CB_META_WEEK"],
    ["Reporting window", m.window_label ?? `${m.period_start} → ${m.period_end}`, "CB_META_WINDOW"],
    ["Generated", m.generated_utc ?? "—", "CB_META_GENERATED"],
    ["Methodology version", m.methodology_version ?? "—", "CB_META_METHODOLOGY"],
    ["HU relevance model version", m.hu_model_version ?? "—", "CB_META_HU_MODEL"],
    ["Template version", m.template_version ?? TEMPLATE_VERSION, "CB_META_TEMPLATE"],
    ["Brief status", ctx.template ? "[GENERATED / EDITING / READY FOR APPROVAL / APPROVED / RELEASED]" : statusTxt, "CB_META_STATUS"],
    ["Approved by", ctx.template ? "[name, date]" : (d?.approved_by ? `${d.approved_by} (${d.approved_utc ?? ""})` : "—"), "CB_META_APPROVED_BY"],
    ["Revision", m.revision ? `${m.revision.number}: ${m.revision.reason ?? ""} (${m.revision.restated_utc ?? ""})` : "none", "CB_META_REVISION"],
    ["Source traceability", ctx.template ? "[n original sources (S-xx), hyperlinked in section 5]" : `${b.page5.sources.length} original sources (S-xx), hyperlinked in section 5`, "CB_META_SOURCES"],
  ];
  body.push(table(ctx, ["Field", "Value"], [28, 72],
    metaRows.map(([k, v, tag]) => [fixed(ctx, [tr(k)]), ctl(ctx, "C", tag, k, [tr(v)])])));

  // --- 1. bottom line + primary KJ ---
  const p1 = b.page1;
  const P1 = schemaPage(1);
  body.push(heading(ctx, 1, `1. ${P1.title}`));
  body.push(heading(ctx, 2, schemaBlock("bottom_line")!.label));
  const blRuns: Run[] = [];
  p1.bottom_line.sentences.forEach((s, i) => {
    blRuns.push(...ctl(ctx, "E", T("bottom_line", "text", i + 1), `Bottom line ${i + 1}`, [tr((i ? " " : "") + s.text)]));
    if (s.sources.length) blRuns.push(tr(" ["), ...srcRuns(ctx, s.sources, ""), tr("]", { color: "475569", size: 17 }));
  });
  body.push(para(wrap(ctx, schemaBlock("bottom_line")!.tag, "Bottom line", blRuns), { after: 60 }));
  body.push(caption(ctx, p1.bottom_line.origin === "executive_synthesis"
    ? "Executive synthesis — every sentence cites its sources; numbers and countries are checked against them."
    : "Built from the assessed judgements, developments and coverage audit."));

  body.push(heading(ctx, 2, schemaBlock("primary")!.label));
  body.push(caption(ctx, "Ranked by Hungary relevance → air-power significance → confidence → immediacy. Max 3."));
  if (!p1.primary.length && p1.primary_empty) body.push(para([tr(p1.primary_empty)]));
  p1.primary.forEach((k, i) => {
    const n = i + 1, A = (f: string) => `KJ ${n} · ${L("primary", f)}`;
    body.push(para([...fixed(ctx, [tr(`KJ ${n} `)]), ...ctl(ctx, "C", `CB_KJ${n}_ID`, `KJ ${n} · ID`, [tr(k.id)]), tr(" — "),
                    ...ctl(ctx, "E", T("primary", "statement", n), A("statement"), [tr(k.statement)])], { heading: HeadingLevel.HEADING_3 }));
    body.push(para([...huRuns(ctx, k.hu_relevance.level, T("primary", "hu_relevance.level", n), A("hu_relevance.level")),
      tr(" · SIG "), ...ctl(ctx, "C", T("primary", "significance", n), A("significance"), [tr(String(k.significance))]), tr("/5 · CONF "),
      ...ctl(ctx, "C", T("primary", "confidence", n), A("confidence"), [tr((k.confidence ?? "—").toUpperCase())]), tr(" · "),
      ...ctl(ctx, "C", T("primary", "horizon", n), A("horizon"), [tr(HORIZON_LABEL(k.horizon))]),
      ...(k.origin === "executive_synthesis" ? [tr(" · EXECUTIVE SYNTHESIS", { bold: true, color: "6D28D9" })] : [])], { after: 40 }));
    for (const f of ["what_changed", "assessment", "why_hungary", "next_observable", "alternative_explanation"] as const) {
      body.push(labelled(ctx, L("primary", f), String(k[f] ?? "—"), T("primary", f, n), A(f)));
    }
    body.push(para(sourcesField(ctx, k.sources, T("primary", "sources", n), A("sources")), { after: 100 }));
  });
  if (p1.secondary_watch.length) {
    body.push(heading(ctx, 2, schemaBlock("secondary_watch")!.label));
    body.push(caption(ctx, "Globally significant, but of low direct relevance to Hungary."));
    p1.secondary_watch.forEach((s, i) => {
      const n = i + 1;
      body.push(para([...ctl(ctx, "E", T("secondary_watch", "line", n), `Watch ${n}`, [tr(s.line)]),
        tr(`  SIG ${s.significance}/5 · HU ${s.hu_level ?? "—"}  `, { color: "64748B", size: 17 }),
        ...sourcesField(ctx, s.sources, T("secondary_watch", "sources", n), `Watch ${n} · Sources`, "")], { numbering: true }));
    });
  }
  body.push(heading(ctx, 2, "Regional air picture"));
  body.push(ctx.template
    ? await figure(ctx, "CB_MAP_CEE", "CEE map", placeholderSvg(600, 470, "CEE map — right-click › Change Picture"), 600, 470, 400, svg2png)
    : await figure(ctx, "CB_MAP_CEE", "CEE map", ceeMapSvg(p1.map_cee), 600, 470, 400, svg2png));
  body.push(para([...fixed(ctx, [tr("Figure 1 — ")]), ...ctl(ctx, "E", T("map_cee", "caption", 1), "CEE map caption", [tr(p1.map_cee.caption ?? "")])], { style: "Caption" }));

  // --- 2. regio ---
  const p2 = b.page2;
  const P2 = schemaPage(2);
  body.push(heading(ctx, 1, `2. ${P2.title}`));
  body.push(caption(ctx, `${P2.subtitle}.`));
  if (p2.rows.length) {
    body.push(table(ctx, ["Country", "What changed", "Capability / operational effect", "HU relevance", "SIG", "CONF · horizon", "Next observable", "Sources"],
      [10, 22, 20, 14, 5, 8, 13, 8],
      p2.rows.map((r, i) => {
        const n = i + 1, A = (f: string) => `Region ${n} · ${L("regional_rows", f)}`;
        return [
          [tr(r.country, { bold: true })],
          ctl(ctx, "E", T("regional_rows", "what_changed", n), A("what_changed"), [tr(r.what_changed)]),
          ctl(ctx, "E", T("regional_rows", "effect", n), A("effect"), [tr(r.effect)]),
          [...huRuns(ctx, r.hu_relevance), tr(" "), ...ctl(ctx, "E", T("regional_rows", "hu_why", n), A("hu_why"), [tr(r.hu_why ?? "", { size: 16 })])],
          `${r.significance}/5`, `${r.confidence ?? "—"} · ${HORIZON_LABEL(r.horizon)}`,
          ctl(ctx, "E", T("regional_rows", "next_observable", n), A("next_observable"), [tr(r.next_observable ?? "—")]),
          r.sources.length ? sourcesField(ctx, r.sources, T("regional_rows", "sources", n), A("sources"), "") : noDirect(ctx, r.context_sources),
        ];
      })));
  } else {
    body.push(para([tr("NO MATERIAL CHANGE IDENTIFIED in the immediate and near region.", { bold: true })]));
  }
  body.push(para([...fixed(ctx, [tr("No material change identified: ", { bold: true })]),
                  ...ctl(ctx, "C", "CB_P2_NO_CHANGE", "No material change identified",
                         [tr(p2.no_material_change.map((x) => `${x.name} (${x.coverage.toLowerCase()})`).join(" · ") || "—")])], { after: 40 }));
  body.push(para([...fixed(ctx, [tr("Collection gap: ", { bold: true })]),
                  ...ctl(ctx, "C", "CB_P2_COLLECTION_GAP", "Collection gap", [tr(p2.collection_gap.join(" · ") || "—")]),
                  ...fixed(ctx, [tr(". Absence of reporting is not evidence of inactivity.")])], { after: 40 }));
  if (b.coverage_summary?.priority?.length) {
    body.push(labelled(ctx, "Coverage (60 days)", b.coverage_summary.priority.map((c) => `${c.name} ${c.status}${c.official_source ? "" : "*"}`).join(" · ")));
    body.push(caption(ctx, "* no official air force / MoD source in collection."));
  }
  if (p2.collection_requirements.length) {
    body.push(heading(ctx, 2, schemaBlock("collection_requirements")!.label));
    body.push(caption(ctx, "Gap → intelligence question → desired observable."));
    body.push(table(ctx, schemaBlock("collection_requirements")!.table!.columns, [12, 9, 19, 30, 30],
      p2.collection_requirements.map((q, i) => {
        const n = i + 1;
        return [[tr(q.country, { bold: true })], q.status, q.gap,
          ctl(ctx, "E", T("collection_requirements", "question", n), `Requirement ${n} · Question`, [tr(q.question)]),
          ctl(ctx, "E", T("collection_requirements", "observable", n), `Requirement ${n} · Observable`, [tr(q.observable)])];
      })));
  }
  if (p2.note) body.push(caption(ctx, p2.note));

  // --- 3. tagabb kep ---
  const p3 = b.page3;
  body.push(heading(ctx, 1, `3. ${schemaPage(3).title}`));
  let n3 = 0;
  for (const s of p3.sections) {
    body.push(heading(ctx, 2, `${s.title}${s.coverage ? ` (coverage ${s.coverage.toLowerCase()})` : ""}`));
    if (!s.items.length) body.push(para([tr(s.empty ?? "NO MATERIAL CHANGE IDENTIFIED", { bold: true, color: "475569" })]));
    for (const it of s.items) { n3 += 1; body.push(...itemParas(ctx, "p3_items", it, n3)); }
  }
  body.push(heading(ctx, 2, schemaBlock("maturity")!.label));
  const cols = p3.maturity.columns;
  body.push(table(ctx, ["Development", "HU", ...cols], [26, 10, ...cols.map(() => 64 / cols.length)],
    p3.maturity.rows.map((r, i) => {
      const at = r.column ? cols.indexOf(r.column) : -1;
      return [[...ctl(ctx, "E", T("maturity", "label", i + 1), `Maturity ${i + 1} · Label`, [tr(r.label)]), tr(` (${r.country})`)],
        r.hu_relevance ?? "—",
        ...cols.map((c, j) => r.withdrawal ? (j === 0 ? `withdrawal — ${r.stage}` : "")
          : j === at ? [tr(r.stage, { bold: true })] : j < at ? "✓" : "")];
    })));
  body.push(para([...ctl(ctx, "E", T("maturity_caption", "caption", 1), "Maturity caption", [tr(p3.maturity.caption ?? "")]),
                  ...fixed(ctx, [tr(" ✓ = earlier stage implied, not observed.")])], { style: "Caption" }));
  const ct = p3.change_table;
  body.push(heading(ctx, 2, `${schemaBlock("change_table")!.label}${ct.previous_week ? ` — against ${ct.previous_week} (published)` : ""}`));
  if (ct.rows.length) {
    body.push(table(ctx, ["Priority", "Country", "Capability", "Previous", "Current", "Change", "HU relevance", "Confidence"],
      [7, 12, 18, 15, 15, 17, 8, 8],
      ct.rows.map((r, i) => [String(r.priority), r.country,
        ctl(ctx, "E", T("change_table", "capability", i + 1), `Change ${i + 1} · Capability`, [tr(r.capability)]),
        r.previous ?? "—", r.current ?? "—",
        ctl(ctx, "E", T("change_table", "delta", i + 1), `Change ${i + 1} · Change`, [tr(r.delta ?? "—")]),
        r.hu_relevance ?? "—", r.confidence ?? "—"])));
  } else {
    body.push(para([tr(ct.note || "No prior published report — the comparison begins next period.")]));
  }

  // --- 4. globalis ---
  const p4 = b.page4;
  body.push(heading(ctx, 1, `4. ${schemaPage(4).title}`));
  body.push(heading(ctx, 2, schemaBlock("global_items")!.label));
  if (!p4.global.items.length) body.push(para([tr(p4.global.empty ?? "NO MATERIAL CHANGE IDENTIFIED", { bold: true, color: "475569" })]));
  p4.global.items.forEach((it, i) => body.push(...itemParas(ctx, "global_items", it, i + 1)));
  body.push(ctx.template
    ? await figure(ctx, "CB_MAP_GLOBAL", "Global map", placeholderSvg(800, 410, "Global map — right-click › Change Picture"), 800, 410, 560, svg2png)
    : await figure(ctx, "CB_MAP_GLOBAL", "Global map", globalMapSvg(p4.map_global), 800, 410, 560, svg2png));
  body.push(para([...fixed(ctx, [tr("Figure 2 — ")]), ...ctl(ctx, "E", T("map_global", "caption", 1), "Global map caption", [tr(p4.map_global.caption ?? "")])], { style: "Caption" }));
  body.push(heading(ctx, 2, schemaBlock("priority_watch")!.label));
  if (!p4.priority_watch.length) body.push(para([tr("No priority watch item this week.")]));
  p4.priority_watch.forEach((w, i) => {
    const n = i + 1;
    body.push(para([tr(`${n}. `, { bold: true }), ...ctl(ctx, "E", T("priority_watch", "question", n), `Watch ${n} · Item`, [tr(w.question, { bold: true })]),
      ...(w.hu_relevance ? [tr("  "), ...huRuns(ctx, w.hu_relevance)] : [])], { before: 60, after: 20, keepNext: true }));
    body.push(labelled(ctx, "Why", w.why ?? "—", T("priority_watch", "why", n), `Watch ${n} · Why`));
    body.push(labelled(ctx, "Next observable", w.next_observable ?? "—", T("priority_watch", "next_observable", n), `Watch ${n} · Next observable`,
      [tr(` (horizon ${w.horizon ?? "—"}, impact ${w.impact ?? "—"})`, { color: "64748B" })]));
  });
  body.push(heading(ctx, 2, schemaBlock("intelligence_gaps")!.label));
  p4.intelligence_gaps.forEach((g, i) => {
    body.push(para([...ctl(ctx, "E", T("intelligence_gaps", "text", i + 1), `Gap ${i + 1}`, [tr(g.text)]),
      ...(g.origin === "coverage_audit" ? [tr(" (coverage audit)", { color: "64748B", size: 17 })] : [])], { numbering: true }));
  });
  body.push(heading(ctx, 2, `${schemaBlock("outlook")!.label} — next 7–30 days`));
  p4.outlook.forEach((o, i) => {
    const n = i + 1;
    body.push(para([...ctl(ctx, "E", T("outlook", "subject", n), `Outlook ${n} · Subject`, [tr(o.subject, { bold: true })]),
      tr(` (${o.country}) — `, { color: "64748B" }),
      ...ctl(ctx, "E", T("outlook", "expected_observable", n), `Outlook ${n} · Expected observable`, [tr(o.expected_observable)]), tr("  "),
      ...sourcesField(ctx, o.sources, T("outlook", "sources", n), `Outlook ${n} · Sources`, "")], { numbering: true }));
  });
  if (p4.outlook_note) body.push(caption(ctx, p4.outlook_note));

  // --- 5. forrasok + jelmagyarazat ---
  const p5 = b.page5;
  body.push(heading(ctx, 1, `5. ${schemaPage(5).title}`));
  // (a) EVIDENCE-LINEAGE register — ugyanaz, mint a kanonikus PDF 5. oldala.
  const LR = p5.lineages ?? lineageRegister(p5.sources);
  const reg = PRESENTATION.register as unknown as { lineage_title: string; lineage_note: string };
  const pubRuns = (ids: string[]): Run[] => ids.flatMap((id, i) => {
    const s = ctx.idx.get(id);
    return [...(i ? [tr(" · ")] : []), tr(`${s?.source_name ?? id} `),
      s?.url ? new ExternalHyperlink({ link: s.url, children: [tr(id, { style: "Hyperlink" })] }) : tr(id)];
  });
  body.push(heading(ctx, 2, reg.lineage_title));
  body.push(caption(ctx, `${LR.independent_lineages} independent lineages · ${LR.publications} publications. ${reg.lineage_note}`));
  body.push(table(ctx, schemaBlock("lineage_register")!.table!.columns, [6, 20, 19, 28, 9, 18],
    LR.rows.map((r) => [
      [tr(r.id, { bold: true })],
      [tr(r.subject, { bold: true }), ...(r.country ? [tr(` · ${r.country}`, { color: "64748B" })] : [])],
      [tr(r.primary_kind === "official" ? "Official: " : "First report: ", { color: "64748B" }), ...pubRuns(r.primary)],
      r.corroboration.length ? [...pubRuns(r.corroboration), ...(r.state_controlled ? [tr(" · state-controlled: attributed statement", { color: "92400E" })] : [])]
        : "none — single report",
      r.first_published ?? "not recorded",
      r.used_by.join(", ") || "—",
    ])));
  if (LR.context_only.length) {
    body.push(para([tr("Context only — not evidence, no lineage: ", { bold: true }),
      ...LR.context_only.flatMap((c, i) => [...(i ? [tr(" · ")] : []), ...pubRuns([c.id]), tr(` (context for ${c.context_for.join(", ") || "—"})`)])],
      { after: 60 }));
  }
  // (b) a TELJES publikacio-szintu register (Wordben megtartva).
  body.push(heading(ctx, 2, p5.register_title ?? PRESENTATION.register.title));
  body.push(table(ctx, schemaBlock("source_register")!.table!.columns, [5, 12, 35, 9, 10, 8, 5, 9, 7],
    p5.sources.map((s) => {
      const ctxOnly = s.evidence_role === "CONTEXT_ONLY";
      return [
        [tr(s.id, { bold: true })],
        [tr(s.source_name), tr(` · ${s.tier.replace("Tier ", "T")}${s.tier_rank === 1 ? " official" : ""}`, { color: "64748B", size: 15 })],
        [s.url ? new ExternalHyperlink({ link: s.url, children: [tr(s.title, { style: "Hyperlink" })] }) : tr(s.title),
         ...(s.note ? [tr(` — ${s.note}`, { color: "64748B", size: 15 })] : [])],
        (s.published ?? "not recorded") + (s.published_basis && s.published_basis !== "feed" ? ` (${s.published_basis})` : ""),
        ctxOnly ? "Context only — not evidence" : s.role,
        `${s.country} · ${s.language}`, s.lineage ?? "—",
        s.used_by.join(", ") || "—", (s.context_for ?? []).join(", ") || "—",
      ];
    })));
  if (p5.source_note) body.push(caption(ctx, p5.source_note));
  // Jelmagyarazat ket hasabban (folytatolagos szakasz): ugyanaz a tartalom,
  // fele magassag — a Word igy nem nyulik feleslegesen.
  const legend: Paragraph[] = [heading(ctx, 2, "Legend")];
  for (const sec of p5.legend) {
    legend.push(heading(ctx, 3, sec.title));
    for (const [term, text] of sec.items) {
      legend.push(para(fixed(ctx, [tr(`${term} — `, { bold: true }), tr(text)]), { after: 20 }));
    }
  }
  legend.push(heading(ctx, 3, "Analytical discipline"));
  for (const x of p5.principles) legend.push(para(fixed(ctx, [tr(x)]), { numbering: true }));
  // (A micro-legend minden oldal lablecében szerepel.)

  const doc = new Document({
    creator: "Aircraft Tracker", title: `${doc0.title} ${b.week_label}`,
    description: `${ctx.template ? "Manual fallback template" : b.status_line}. Template v${m.template_version ?? TEMPLATE_VERSION}; methodology ${m.methodology_version ?? ""}; HU model ${m.hu_model_version ?? ""}.`,
    customProperties: [
      { name: "CB_TEMPLATE_VERSION", value: m.template_version ?? TEMPLATE_VERSION },
      { name: "CB_WEEK", value: b.week_label },
      { name: "CB_METHODOLOGY_VERSION", value: m.methodology_version ?? "" },
      { name: "CB_HU_MODEL_VERSION", value: m.hu_model_version ?? "" },
      { name: "CB_DRAFT_STATUS", value: ctx.template ? "TEMPLATE" : (d?.status ?? "GENERATED") },
      { name: "CB_DRAFT_REVISION", value: String(d?.revision ?? 0) },
      { name: "CB_RELEASE", value: d?.release_no ? `R-${d.release_no}` : "" },
      { name: "CB_CANONICAL", value: "false — Word is a working copy; the canonical product is the released PDF" },
    ],
    externalStyles: DOCX_STYLES,
    numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 360, hanging: 240 } } } }] }] },
    sections: [{
      properties: { page: { size: { width: PAGE_W, height: PAGE_H, orientation: PageOrientation.LANDSCAPE },
                            margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN, header: 400, footer: 400 } } },
      headers: { default: new Header({ children: [new Paragraph({ style: "Header", children: [
        tr(`${doc0.title} · ${b.week_label} · ${b.classification} · ${ctx.template ? "TEMPLATE" : statusTxt} · template v${m.template_version ?? TEMPLATE_VERSION}`)] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ style: "Footer", children: [
        tr(`${b.micro_legend}   ·   Page `), new TextRun({ children: [PageNumber.CURRENT] }),
        tr(" of "), new TextRun({ children: [PageNumber.TOTAL_PAGES] })] })] }) },
      children: body,
    }, {
      properties: { type: SectionType.CONTINUOUS, column: { count: 2, space: 425 },
                    page: { size: { width: PAGE_W, height: PAGE_H, orientation: PageOrientation.LANDSCAPE },
                            margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN, header: 400, footer: 400 } } },
      children: legend,
    }],
  });
  return finalizePackage(await Packer.toBuffer(doc), ctx);
}

// --------------------------------------------------------- post-process --
const xmlAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

/** Konyvjelzok -> Word content controls (w:sdt). A docx konyvtar minden
 *  konyvjelzonek ugyanazt a w:id-t adja, ezert a parokat a beagyazas
 *  (verem) alapjan illesztjuk. */
export function bookmarksToContentControls(xml: string, alias: Map<string, string>, template: boolean): string {
  const stack: (string | null)[] = [];
  let sdtId = 1000;
  return xml.replace(/<w:bookmarkStart\b[^>]*\/>|<w:bookmarkEnd\b[^>]*\/>/g, (tag) => {
    if (tag.startsWith("<w:bookmarkEnd")) {
      const k = stack.pop();
      if (k === "WS") return "";                        // nyito jelolo vege
      if (k === "WE") return "</w:sdtContent></w:sdt>"; // zaro jelolo
      return k ? "</w:sdtContent></w:sdt>" : tag;
    }
    const name = /w:name="([^"]*)"/.exec(tag)?.[1] ?? "";
    const mt = /^CB(WS|WE|[ECFP])__(.+)$/.exec(name);
    if (!mt) { stack.push(null); return tag; }
    const [, kind, rest] = mt;
    stack.push(kind);
    if (kind === "WE") return "";
    sdtId += 1;
    const t = kind === "F" ? "CB_FIXED" : rest;
    const al = kind === "F" ? "Fixed template text" : alias.get(rest) ?? rest;
    const lock = kind === "F" ? "sdtContentLocked"
      : kind === "C" && !template ? "sdtContentLocked" : "sdtLocked";
    const ph = template && (kind === "E" || kind === "C") ? "<w:showingPlcHdr/>" : "";
    const pic = kind === "P" ? "<w:picture/>" : "";
    return `<w:sdt><w:sdtPr><w:alias w:val="${xmlAttr(al)}"/><w:tag w:val="${xmlAttr(t)}"/><w:id w:val="${sdtId}"/>` +
           `<w:lock w:val="${lock}"/>${ph}${pic}</w:sdtPr><w:sdtContent>`;
  });
}

// A placeholder-szoveg szurke (Word "Placeholder Text" stilus).
const PLACEHOLDER_STYLE = `<w:style w:type="character" w:styleId="PlaceholderText"><w:name w:val="Placeholder Text"/><w:basedOn w:val="DefaultParagraphFont"/><w:uiPriority w:val="99"/><w:semiHidden/><w:rPr><w:color w:val="808080"/></w:rPr></w:style>`;

async function finalizePackage(buf: Buffer, ctx: Ctx): Promise<Buffer> {
  const mod = await import("jszip");
  const JSZip = ((mod as unknown as { default?: typeof mod.default }).default ?? mod) as typeof mod.default;
  const src = await JSZip.loadAsync(buf);
  const out = new JSZip();
  // A ZIP mappa-bejegyzesei (word/, word/_rels/ ...) miatt a felhos
  // tarsszerkesztok egy resze megtagadja a fajlt: csak fajl-bejegyzesek,
  // es a [Content_Types].xml elol — a Word igy varja.
  const names = Object.keys(src.files).filter((n) => !src.files[n].dir);
  names.sort((a, b) => (a === "[Content_Types].xml" ? -1 : b === "[Content_Types].xml" ? 1 : 0));
  for (const n of names) {
    let data: string | Uint8Array = await src.files[n].async("uint8array");
    if (n === "word/document.xml") {
      let xml = Buffer.from(data).toString("utf8");
      xml = bookmarksToContentControls(xml, ctx.alias, ctx.template);
      if (ctx.template) {
        // A helyorzo futasok szurke "Placeholder Text" stilust kapnak.
        xml = xml.replace(/(<w:sdtPr>(?:(?!<\/w:sdtPr>)[\s\S])*<w:showingPlcHdr\/>(?:(?!<\/w:sdtPr>)[\s\S])*<\/w:sdtPr><w:sdtContent>)((?:(?!<\/w:sdtContent>)[\s\S])*)/g,
          (_m, head: string, content: string) => head + content.replace(/<w:r>(<w:rPr>)?(<w:rStyle)?/g, (r, rp, rs) =>
            rs ? r : rp ? "<w:r><w:rPr><w:rStyle w:val=\"PlaceholderText\"/>" : "<w:r><w:rPr><w:rStyle w:val=\"PlaceholderText\"/></w:rPr>"));
      }
      data = xml;
    } else if (n === "word/styles.xml") {
      data = Buffer.from(data).toString("utf8").replace("</w:styles>", `${PLACEHOLDER_STYLE}</w:styles>`);
    } else if (n === "[Content_Types].xml" && ctx.template) {
      data = Buffer.from(data).toString("utf8").replace(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml");
    }
    out.file(n, data, { createFolders: false });
  }
  return out.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}
