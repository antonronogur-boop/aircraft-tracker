// Command Brief draft tarolas — CSAK szerveroldal (service role kulcs).
//
// Hol: ac_reports.payload.command_brief_draft (uj tabla es kezi SQL nelkul;
// a jelentes sorahoz tartozik, igy a heti termek es a publikacios rete
// egyutt archivalodik). Az iras optimista zarolassal megy: csak akkor
// sikerul, ha a sor draft-revizioja es generated_at-je azota nem valtozott
// (kulonben 409 — senki munkaja nem iródik felul csendben). A payload
// TOBBI kulcsat (az elemzoi reteget) valtozatlanul irjuk vissza.
//
// AC_DRAFT_STORE=file:<mappa>  -> helyi JSON-fajlok (E2E / fejlesztes,
//                                 az AC_REPORT_FIXTURE sorokkal egyutt).
import { createHash } from "crypto";
import type { ReportRow } from "@/lib/reports";
import { loadReport } from "@/lib/reports";
import type { BriefDraft } from "@/lib/briefDraft";

export const sha256 = (s: string) => createHash("sha256").update(s, "utf8").digest("hex");

export interface StoredRow { row: ReportRow; draft: BriefDraft | null }

function fileDir(): string | null {
  const v = process.env.AC_DRAFT_STORE ?? "";
  return v.startsWith("file:") ? v.slice(5) : null;
}

function supa() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  return {
    url,
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
  };
}

export async function loadDraftRow(week: string): Promise<StoredRow | null> {
  const dir = fileDir();
  if (dir) {
    const row = await loadReport(week);
    if (!row) return null;
    const { readFile } = await import("fs/promises");
    const path = await import("path");
    let draft: BriefDraft | null = null;
    try {
      draft = JSON.parse(await readFile(path.join(dir, `${row.week_label}.json`), "utf-8")) as BriefDraft;
    } catch { draft = null; }
    return { row, draft };
  }
  const s = supa();
  if (!s) {
    // Olvasashoz eleg a publikus ut (anon) — ilyenkor iras nincs.
    const row = await loadReport(week);
    if (!row) return null;
    const p = row.payload as unknown as Record<string, unknown>;
    return { row, draft: (p.command_brief_draft as BriefDraft) ?? null };
  }
  const q = week === "latest"
    ? "order=period_end.desc&limit=1"
    : `week_label=eq.${encodeURIComponent(week)}&limit=1`;
  const r = await fetch(`${s.url}/rest/v1/ac_reports?select=*&${q}`, { headers: s.headers, cache: "no-store" });
  if (!r.ok) throw new Error(`supabase read failed (${r.status})`);
  const rows = (await r.json()) as ReportRow[];
  if (!rows.length) return null;
  const p = rows[0].payload as unknown as Record<string, unknown>;
  return { row: rows[0], draft: (p.command_brief_draft as BriefDraft) ?? null };
}

export type SaveResult = { ok: true } | { ok: false; conflict: boolean; error: string };

export async function saveDraft(stored: StoredRow, next: BriefDraft): Promise<SaveResult> {
  const week = stored.row.week_label;
  const expectRev = stored.draft?.revision ?? 0;
  const dir = fileDir();
  if (dir) {
    const { readFile, writeFile, mkdir } = await import("fs/promises");
    const path = await import("path");
    await mkdir(dir, { recursive: true });
    const f = path.join(dir, `${week}.json`);
    let cur: BriefDraft | null = null;
    try { cur = JSON.parse(await readFile(f, "utf-8")) as BriefDraft; } catch { cur = null; }
    if ((cur?.revision ?? 0) !== expectRev) {
      return { ok: false, conflict: true, error: "draft changed since it was loaded — reload" };
    }
    await writeFile(f, JSON.stringify(next, null, 1), "utf-8");
    return { ok: true };
  }
  const s = supa();
  if (!s) return { ok: false, conflict: false, error: "server not configured for writing (SUPABASE_SERVICE_ROLE_KEY)" };
  const payload = { ...(stored.row.payload as unknown as Record<string, unknown>), command_brief_draft: next };
  const filters = [
    `week_label=eq.${encodeURIComponent(week)}`,
    `generated_at=eq.${encodeURIComponent(stored.row.generated_at)}`,
    stored.draft
      ? `payload->command_brief_draft->>revision=eq.${expectRev}`
      : "payload->command_brief_draft=is.null",
  ].join("&");
  const r = await fetch(`${s.url}/rest/v1/ac_reports?${filters}&select=week_label`, {
    method: "PATCH",
    headers: { ...s.headers, Prefer: "return=representation" },
    body: JSON.stringify({ payload }),
    cache: "no-store",
  });
  if (!r.ok) return { ok: false, conflict: false, error: `supabase update failed (${r.status})` };
  const rows = (await r.json()) as unknown[];
  if (!rows.length) {
    return { ok: false, conflict: true, error: "the report or its draft changed since it was loaded — reload" };
  }
  return { ok: true };
}

/** Opcionalis vedelem: ha BRIEF_EDITOR_TOKEN be van allitva, az iro
 *  kereseknek x-brief-editor-token fejlecben meg kell adniuk. */
export function editorAuthorized(req: Request): boolean {
  const tok = process.env.BRIEF_EDITOR_TOKEN;
  if (!tok) return true;
  return req.headers.get("x-brief-editor-token") === tok;
}
