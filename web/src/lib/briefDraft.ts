// COMMAND BRIEF DRAFT — a publikacios reteg (tiszta logika, IO nelkul).
//
//   A. Analytical truth  — ac_events / ac_reports elemzoi retegei. A draft
//                          SOHA nem irja vissza.
//   B. Command Brief Draft — a generalt brief (payload.command_brief) +
//                          ember altal szerkesztett PUBLIKACIOS SZOVEG
//                          (overrides), rejtes, sorrend, statusz, audit.
//   C. Released product  — jovahagyott draftbol fagyasztott, verziozott
//                          pillanatkep (web / kanonikus PDF / DOCX).
//
// Csak a presentation schema "copy" mezoi szerkeszthetok; forras, lineage,
// HU-szint, SIG, CONF, horizon, datumok kontrollalt metaadatok.
import type { CommandBriefV2, SourceEntry } from "@/lib/briefTypes";
import {
  PRESENTATION, TEMPLATE_VERSION, allBlocks, block as schemaBlock, blockLists, blockObject,
  copyFields, getField, hardLimit, itemKey, setField, type SchemaBlock,
} from "@/lib/presentation";

export type DraftStatus = "GENERATED" | "EDITING" | "READY_FOR_APPROVAL" | "APPROVED" | "RELEASED";

export interface CopyOverride { value: string; base: string; at: string; by: string }

export interface AuditEntry {
  rev: number; at: string; actor: string;
  action: "edit" | "revert" | "hide" | "show" | "reorder" | "status" | "release" | "rebase";
  field?: string; previous?: unknown; next?: unknown; note?: string;
}

export interface ReleaseRecord {
  release_no: number; draft_rev: number; released_utc: string; released_by: string;
  approved_by: string; approved_utc: string;
  template_version: string; methodology_version?: string | null; hu_model_version?: string | null;
  base_hash: string; content_hash: string;
  brief: CommandBriefV2;
}

export interface BriefDraft {
  schema: "command_brief_draft_v1";
  week_label: string;
  template_version: string;
  status: DraftStatus;
  revision: number;
  base_hash: string;
  overrides: Record<string, CopyOverride>;   // "block/itemKey/field"
  hidden: string[];                          // "block/itemKey"
  order: Record<string, string[]>;           // block -> itemKeys
  approval: { by: string; at: string; rev: number; base_hash: string } | null;
  audit: AuditEntry[];
  releases: ReleaseRecord[];
  created_utc: string; updated_utc: string;
}

export type DraftOp =
  | { type: "set"; block: string; key: string; field: string; value: string }
  | { type: "revert"; block: string; key: string; field: string }
  | { type: "hide" | "show"; block: string; key: string }
  | { type: "order"; block: string; keys: string[] }
  | { type: "status"; to: DraftStatus; note?: string }
  | { type: "release" };

export type Hasher = (s: string) => string;

// ------------------------------------------------------------ helpers --
export function stableStringify(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v ?? null);
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(",")}]`;
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o).filter((k) => o[k] !== undefined).sort()
    .map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`).join(",")}}`;
}

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
export const fieldId = (b: string, k: string, f: string) => `${b}/${k}/${f}`;
export const itemId = (b: string, k: string) => `${b}/${k}`;

/* Regi (S-13 javitas elotti) briefek: a kontextus-forras a "used_by"
 * mezoben szerepelt. Megjeleniteskor szetvalasztjuk — a tarolt adathoz nem
 * nyulunk. */
export function normalizeBrief(b: CommandBriefV2): CommandBriefV2 {
  const out = clone(b);
  out.page5.sources = out.page5.sources.map((s: SourceEntry) => {
    if (s.evidence_role) return { ...s, context_for: s.context_for ?? [] };
    const ctx = (s.role ?? "").startsWith("Context");
    return ctx
      ? { ...s, evidence_role: "CONTEXT_ONLY", context_for: s.used_by ?? [], used_by: [], lineage: null }
      : { ...s, evidence_role: "EVIDENCE", context_for: [] };
  });
  out.meta.template_version ??= TEMPLATE_VERSION;
  return out;
}

export function emptyDraft(brief: CommandBriefV2, hash: Hasher, now: string): BriefDraft {
  return {
    schema: "command_brief_draft_v1", week_label: brief.week_label,
    template_version: TEMPLATE_VERSION, status: "GENERATED", revision: 0,
    base_hash: hashBase(brief, hash), overrides: {}, hidden: [], order: {},
    approval: null, audit: [], releases: [], created_utc: now, updated_utc: now,
  };
}

export const hashBase = (brief: CommandBriefV2, hash: Hasher) => hash(stableStringify(brief));

/** A generalt (alap) brief tetelei egy blokkban: kulcs -> tetel. */
export function baseItems(brief: CommandBriefV2, b: SchemaBlock): Map<string, Record<string, unknown>> {
  const m = new Map<string, Record<string, unknown>>();
  if (b.kind === "list") {
    for (const list of blockLists(brief, b.path)) {
      list.forEach((it, i) => m.set(itemKey(b, it, i), it as Record<string, unknown>));
    }
  } else if (b.kind === "object") {
    const o = blockObject(brief, b.path);
    if (o) m.set("#0", o);
  }
  return m;
}

export interface DraftState {
  draft: BriefDraft;
  /** Szerkesztett mezok, amelyek alapszovege azota megvaltozott (ujrageneralas). */
  stale: string[];
  /** A jovahagyas ota az alap brief megvaltozott -> ujra-jovahagyas kell. */
  approval_invalidated: boolean;
}

export function draftState(draft: BriefDraft | null | undefined, brief: CommandBriefV2,
                           hash: Hasher, now: string): DraftState {
  const d = draft ? clone(draft) : emptyDraft(brief, hash, now);
  const cur = hashBase(brief, hash);
  const stale: string[] = [];
  for (const [id, ov] of Object.entries(d.overrides)) {
    const [b, k, f] = id.split("/");
    const blk = schemaBlock(b);
    const it = blk ? baseItems(brief, blk).get(k) : undefined;
    const baseNow = it ? getField(it, f) : undefined;
    if (typeof baseNow !== "string" || baseNow !== ov.base) stale.push(id);
  }
  const approval_invalidated = !!d.approval && d.approval.base_hash !== cur
    && (d.status === "APPROVED" || d.status === "READY_FOR_APPROVAL");
  return { draft: d, stale, approval_invalidated };
}

export function canonical(status: DraftStatus): boolean {
  return PRESENTATION.draft.canonical_pdf_from.includes(status);
}

// --------------------------------------------------------------- apply --
/** A publikalt brief = generalt brief + publikacios szoveg + rejtes +
 *  sorrend. A kontrollalt mezok valtozatlanok. */
export function applyDraft(brief: CommandBriefV2, draft: BriefDraft | null | undefined): CommandBriefV2 {
  const out = normalizeBrief(brief);
  const d = draft;
  for (const { block: b } of allBlocks()) {
    if (b.kind === "list") {
      for (const list of blockLists(out, b.path)) {
        const keyed = list.map((it, i) => ({ k: itemKey(b, it, i), it: it as Record<string, unknown> }));
        if (d) {
          for (const { k, it } of keyed) {
            for (const f of copyFields(b)) {
              const ov = d.overrides[fieldId(b.id, k, f.key)];
              if (ov) setField(it, f.key, ov.value);
            }
          }
        }
        let kept = keyed.filter(({ k }) => !d?.hidden.includes(itemId(b.id, k)));
        const ord = d?.order[b.id];
        if (ord?.length) {
          const pos = new Map(ord.map((k, i) => [k, i]));
          kept = [...kept].sort((a, z) => (pos.get(a.k) ?? 1e6) - (pos.get(z.k) ?? 1e6));
        }
        list.splice(0, list.length, ...kept.map((x) => x.it));
      }
    } else if (b.kind === "object" && d) {
      const o = blockObject(out, b.path);
      if (!o) continue;
      for (const f of copyFields(b)) {
        const ov = d.overrides[fieldId(b.id, "#0", f.key)];
        if (ov) setField(o, f.key, ov.value);
      }
    }
  }
  const status = d?.status ?? "GENERATED";
  out.meta.template_version = d?.template_version ?? TEMPLATE_VERSION;
  out.meta.draft = {
    status, revision: d?.revision ?? 0,
    canonical: canonical(status),
    approved_by: d?.approval?.by ?? null, approved_utc: d?.approval?.at ?? null,
    edited_fields: d ? Object.keys(d.overrides).length : 0,
    hidden_items: d ? d.hidden.length : 0,
    release_no: null,
  };
  return out;
}

// ----------------------------------------------------------------- ops --
export class DraftError extends Error {}

function assertCopyField(brief: CommandBriefV2, blockId: string, key: string, field: string) {
  const b = schemaBlock(blockId);
  if (!b) throw new DraftError(`unknown block ${blockId}`);
  const f = (b.fields ?? []).find((x) => x.key === field);
  if (!f) throw new DraftError(`unknown field ${blockId}.${field}`);
  if (f.edit !== "copy") {
    throw new DraftError(`${blockId}.${field} is controlled analytical metadata — it cannot be edited in the Command Brief editor`);
  }
  const it = baseItems(brief, b).get(key);
  if (!it) throw new DraftError(`unknown item ${blockId}/${key}`);
  return { b, f, it };
}

const EDITABLE: DraftStatus[] = ["GENERATED", "EDITING", "READY_FOR_APPROVAL", "APPROVED", "RELEASED"];

export function applyOps(state: DraftState, brief: CommandBriefV2, ops: DraftOp[],
                         actor: string, now: string, hash: Hasher): BriefDraft {
  const who = (actor ?? "").trim();
  if (!who) throw new DraftError("actor (analyst name) is required for every change");
  if (who.length > 80) throw new DraftError("actor name too long");
  const d = clone(state.draft);
  const rev = d.revision + 1;
  const log = (e: Omit<AuditEntry, "rev" | "at" | "actor">) => d.audit.push({ rev, at: now, actor: who, ...e });
  const touchContent = () => {
    // Tartalmi valtozas jovahagyott / kiadott / jovahagyasra varo draftban:
    // a jovahagyas ervenyet veszti, vissza EDITING-be (lathatoan, auditalva).
    if (d.status !== "EDITING") {
      const prev = d.status;
      d.status = "EDITING";
      d.approval = null;
      log({ action: "status", previous: prev, next: "EDITING",
            note: prev === "GENERATED" ? "first edit" : "content changed — approval no longer valid" });
    }
  };
  let changed = false;
  for (const op of ops) {
    if (op.type === "set") {
      const { f, it } = assertCopyField(brief, op.block, op.key, op.field);
      const value = String(op.value ?? "").replace(/\r\n/g, "\n").trim();
      if (!value) throw new DraftError(`${op.block}.${op.field}: empty text — hide the item instead`);
      if (/…|\.\.\./.test(value)) throw new DraftError(`${op.block}.${op.field}: no ellipsis — write whole sentences`);
      const hard = hardLimit(f);
      if (hard && value.length > hard) {
        throw new DraftError(`${op.block}.${op.field}: ${value.length} characters exceeds the hard limit ${hard} (target ${f.max_chars})`);
      }
      const base = getField(it, f.key);
      const id = fieldId(op.block, op.key, op.field);
      const prev = d.overrides[id]?.value ?? (typeof base === "string" ? base : "");
      if (value === prev) continue;
      touchContent();
      if (typeof base === "string" && value === base) {
        delete d.overrides[id];
      } else {
        d.overrides[id] = { value, base: typeof base === "string" ? base : "", at: now, by: who };
      }
      log({ action: "edit", field: id, previous: prev, next: value });
      changed = true;
    } else if (op.type === "revert") {
      assertCopyField(brief, op.block, op.key, op.field);
      const id = fieldId(op.block, op.key, op.field);
      if (!d.overrides[id]) continue;
      touchContent();
      log({ action: "revert", field: id, previous: d.overrides[id].value, next: d.overrides[id].base });
      delete d.overrides[id];
      changed = true;
    } else if (op.type === "hide" || op.type === "show") {
      const b = schemaBlock(op.block);
      if (!b || !b.hide) throw new DraftError(`items of ${op.block} cannot be hidden`);
      if (!baseItems(brief, b).has(op.key)) throw new DraftError(`unknown item ${op.block}/${op.key}`);
      const id = itemId(op.block, op.key);
      const has = d.hidden.includes(id);
      if ((op.type === "hide") === has) continue;
      touchContent();
      d.hidden = op.type === "hide" ? [...d.hidden, id] : d.hidden.filter((x) => x !== id);
      log({ action: op.type, field: id });
      changed = true;
    } else if (op.type === "order") {
      const b = schemaBlock(op.block);
      if (!b || !b.reorder) throw new DraftError(`items of ${op.block} cannot be reordered`);
      const keys = [...baseItems(brief, b).keys()];
      const want = op.keys ?? [];
      if (want.length !== keys.length || new Set(want).size !== want.length || !want.every((k) => keys.includes(k))) {
        throw new DraftError(`order for ${op.block} must list each item exactly once`);
      }
      const prev = d.order[op.block] ?? keys;
      if (prev.join("|") === want.join("|")) continue;
      touchContent();
      d.order[op.block] = want;
      log({ action: "reorder", field: op.block, previous: prev, next: want });
      changed = true;
    } else if (op.type === "status") {
      const allowed = PRESENTATION.draft.transitions[d.status] ?? [];
      if (op.to === "RELEASED") throw new DraftError("use the release action to release");
      if (!allowed.includes(op.to)) throw new DraftError(`status ${d.status} → ${op.to} is not allowed`);
      const prev = d.status;
      if (op.to === "APPROVED") {
        if (state.stale.length) {
          throw new DraftError(`${state.stale.length} edited field(s) were based on an older generated text — review them first`);
        }
        d.approval = { by: who, at: now, rev, base_hash: hashBase(brief, hash) };
      } else if (op.to === "EDITING" || op.to === "READY_FOR_APPROVAL") {
        if (op.to === "EDITING") d.approval = null;
      }
      d.status = op.to;
      log({ action: "status", previous: prev, next: op.to, note: op.note });
      changed = true;
    } else if (op.type === "release") {
      if (d.status !== "APPROVED" || !d.approval) throw new DraftError("only an APPROVED draft can be released");
      if (d.approval.base_hash !== hashBase(brief, hash)) {
        throw new DraftError("the generated brief changed after approval — re-approve before release");
      }
      const no = (d.releases.at(-1)?.release_no ?? 0) + 1;
      d.status = "RELEASED";
      const published = applyDraft(brief, d);
      published.meta.draft = { ...published.meta.draft!, status: "RELEASED", revision: rev,
                               canonical: true, release_no: no };
      const rec: ReleaseRecord = {
        release_no: no, draft_rev: rev, released_utc: now, released_by: who,
        approved_by: d.approval.by, approved_utc: d.approval.at,
        template_version: d.template_version,
        methodology_version: brief.meta.methodology_version ?? null,
        hu_model_version: brief.meta.hu_model_version ?? null,
        base_hash: d.approval.base_hash, content_hash: hash(stableStringify(published)),
        brief: published,
      };
      d.releases.push(rec);
      log({ action: "release", next: `R-${no}`, note: `content ${rec.content_hash.slice(0, 12)}` });
      changed = true;
    } else {
      throw new DraftError("unknown operation");
    }
  }
  if (!EDITABLE.includes(d.status)) throw new DraftError("invalid status");
  if (changed) {
    d.revision = rev;
    d.updated_utc = now;
    d.base_hash = hashBase(brief, hash);
  }
  return d;
}

/** Mit mutat a nyilvanos nezet: a legutobbi kiadas, vagy (ha nincs) a
 *  munkapeldany — a statusz MINDIG latszik. */
export function publishedView(brief: CommandBriefV2, draft: BriefDraft | null | undefined,
                              view: "auto" | "draft" | "release" = "auto"):
  { brief: CommandBriefV2; kind: "release" | "draft"; release?: ReleaseRecord; newerDraft: boolean } {
  const rel = draft?.releases?.at(-1);
  if (rel && view !== "draft") {
    const b = normalizeBrief(rel.brief);
    return { brief: b, kind: "release", release: rel,
             newerDraft: !!draft && draft.revision > rel.draft_rev };
  }
  return { brief: applyDraft(brief, draft), kind: "draft", newerDraft: false };
}

export function statusLabel(s: DraftStatus): string {
  return PRESENTATION.colours.draft_status[s]?.label ?? s;
}
