// COMMAND BRIEF PRESENTATION SCHEMA — az egyetlen megjelenitesi szabvany.
// Forras: config/command_brief_presentation.json (a Python generator, a web
// nezet, a PDF, a DOCX export es a .dotx template ugyanezt olvassa).
// Tukorpeldany: a Vercel build csak a web/ mappat latja. A kanonikus fajl
// config/command_brief_presentation.json; a ketto egyezeset a
// scripts/test_command_brief.py (I) ellenorzi.
import schemaJson from "./command_brief_presentation.json";

export type EditKind = "copy" | "controlled" | "fixed";

export interface SchemaField {
  key: string; label: string; edit: EditKind;
  max_chars?: number; max_sentences?: number; tag?: string;
}

export interface SchemaBlock {
  id: string; label: string; path: string;
  kind: "list" | "object" | "fixed";
  item_key?: string; max_items?: number; reorder?: boolean; hide?: boolean;
  tag?: string; slot_prefix?: string;
  figure?: { tag: string; width_px: number };
  table?: { columns: string[] };
  fields?: SchemaField[];
}

export interface SchemaPage { n: number; title: string; subtitle: string; blocks: SchemaBlock[] }

export interface PresentationSchema {
  schema: "command_brief_presentation";
  template_version: string; template_name: string; brief_schema: string;
  document: {
    title: string; kicker: string; classification: string; status_line: string; word_note: string;
    page: { size: string; orientation: string; width_mm: number; height_mm: number;
            margin_mm: { top: number; right: number; bottom: number; left: number } };
    word_page: { size: string; orientation: string;
                 margin_mm: { top: number; right: number; bottom: number; left: number } };
    canonical_pdf_pages: number;
  };
  micro_legend: string;
  colours: {
    hu: Record<string, { fill: string; text: string; label: string }>;
    collection: Record<string, { fill: string; label: string; border?: string }>;
    draft_status: Record<string, { fill: string; label: string }>;
  };
  draft: {
    statuses: string[]; transitions: Record<string, string[]>;
    canonical_pdf_from: string[]; word_export_from: string[]; hard_limit_factor: number;
  };
  pages: SchemaPage[];
  register: { title: string; note: string; evidence_roles: Record<string, string> };
  legend: { title: string; items: [string, string][] }[];
  principles: string[];
  maturity_columns: string[];
}

export const PRESENTATION = schemaJson as unknown as PresentationSchema;
export const TEMPLATE_VERSION = PRESENTATION.template_version;

export function page(n: number): SchemaPage {
  return PRESENTATION.pages.find((p) => p.n === n)!;
}

export function allBlocks(): { page: SchemaPage; block: SchemaBlock }[] {
  return PRESENTATION.pages.flatMap((p) => p.blocks.map((block) => ({ page: p, block })));
}

export function block(id: string): SchemaBlock | undefined {
  return allBlocks().find((b) => b.block.id === id)?.block;
}

/* A blokk "tarolo" listai: "page3.sections[].items" -> minden szekcio items
 * listaja kulon (a rejtes / sorrend a sajat listajan belul ertendo). */
export function blockLists(root: unknown, path: string): unknown[][] {
  const parts = path.split(".");
  const out: unknown[][] = [];
  const walk = (obj: unknown, i: number) => {
    if (obj == null) return;
    if (i === parts.length) { if (Array.isArray(obj)) out.push(obj); return; }
    const p = parts[i];
    const rec = obj as Record<string, unknown>;
    if (p.endsWith("[]")) {
      const arr = rec[p.slice(0, -2)];
      if (Array.isArray(arr)) arr.forEach((x) => walk(x, i + 1));
    } else walk(rec[p], i + 1);
  };
  walk(root, 0);
  return out;
}

export function blockObject(root: unknown, path: string): Record<string, unknown> | null {
  let cur: unknown = root;
  for (const p of path.split(".")) {
    if (cur == null || typeof cur !== "object") return null;
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur && typeof cur === "object" ? (cur as Record<string, unknown>) : null;
}

export function itemKey(b: SchemaBlock, item: unknown, index: number): string {
  const k = b.item_key ?? "#index";
  const v = k !== "#index" && item && typeof item === "object" ? (item as Record<string, unknown>)[k] : undefined;
  return v == null || v === "" ? `#${index}` : String(v);
}

export function getField(item: unknown, key: string): unknown {
  let cur: unknown = item;
  for (const p of key.split(".")) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

export function setField(item: Record<string, unknown>, key: string, value: unknown) {
  const parts = key.split(".");
  let cur = item;
  for (const p of parts.slice(0, -1)) cur = (cur[p] ??= {}) as Record<string, unknown>;
  cur[parts[parts.length - 1]] = value;
}

export const copyFields = (b: SchemaBlock) => (b.fields ?? []).filter((f) => f.edit === "copy");
export const controlledFields = (b: SchemaBlock) => (b.fields ?? []).filter((f) => f.edit === "controlled");

export function hardLimit(f: SchemaField): number | null {
  return f.max_chars ? Math.ceil(f.max_chars * PRESENTATION.draft.hard_limit_factor) : null;
}

/** Word content-control tag a megjelenitett pozicioval (1-tol). */
export function slotTag(tag: string | undefined, n: number): string | undefined {
  return tag?.replace("{n}", String(n));
}

export function fieldLabel(blockId: string, key: string): string {
  return block(blockId)?.fields?.find((f) => f.key === key)?.label ?? key;
}
