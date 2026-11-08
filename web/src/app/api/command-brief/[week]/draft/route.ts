// /api/command-brief/<week|latest>/draft — a publikacios reteg (draft).
//
// GET  -> generalt brief + draft allapot (stale mezok, jovahagyas ervenye)
// POST -> { actor, expected_revision, ops: DraftOp[] }
//
// Csak a presentation schema "copy" mezoi modosithatok; minden mas
// (forras, lineage, HU, SIG, CONF, datumok, esemeny, ertekeles) kontrollalt
// — a keres 400-at kap. Az elemzoi reteget ez a vegpont nem irja.
import { NextRequest } from "next/server";
import { loadDraftRow, saveDraft, sha256, editorAuthorized } from "@/lib/draftStore";
import { applyOps, draftState, normalizeBrief, DraftError, type DraftOp } from "@/lib/briefDraft";
import type { CommandBriefV2 } from "@/lib/briefTypes";
import { TEMPLATE_VERSION } from "@/lib/presentation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const nowIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

async function load(week: string) {
  const stored = await loadDraftRow(week);
  const brief = stored?.row.payload?.command_brief as unknown as CommandBriefV2 | undefined;
  if (!stored || !brief || brief.schema !== "command_brief_v2") return null;
  return { stored, brief };
}

function body(stored: NonNullable<Awaited<ReturnType<typeof load>>>["stored"], brief: CommandBriefV2,
              state: ReturnType<typeof draftState>) {
  return {
    week_label: stored.row.week_label, generated_at: stored.row.generated_at,
    template_version: TEMPLATE_VERSION, brief: normalizeBrief(brief), ...state,
  };
}

export async function GET(_req: Request, { params }: { params: { week: string } }) {
  const x = await load(params.week);
  if (!x) return Response.json({ error: "No v2 Command Brief for this week." }, { status: 404 });
  const state = draftState(x.stored.draft, x.brief, sha256, nowIso());
  return Response.json(body(x.stored, x.brief, state), { headers: { "Cache-Control": "no-store" } });
}

export async function POST(req: NextRequest, { params }: { params: { week: string } }) {
  if (!editorAuthorized(req)) return Response.json({ error: "editor token required" }, { status: 401 });
  const inp = (await req.json().catch(() => null)) as
    { actor?: string; expected_revision?: number; ops?: DraftOp[] } | null;
  if (!inp || !Array.isArray(inp.ops) || !inp.ops.length || inp.ops.length > 200) {
    return Response.json({ error: "bad request: ops[] required" }, { status: 400 });
  }
  const x = await load(params.week);
  if (!x) return Response.json({ error: "No v2 Command Brief for this week." }, { status: 404 });
  const now = nowIso();
  const state = draftState(x.stored.draft, x.brief, sha256, now);
  if (typeof inp.expected_revision === "number" && inp.expected_revision !== state.draft.revision) {
    return Response.json({ error: `draft is at revision ${state.draft.revision}, you edited revision ${inp.expected_revision} — reload`,
                           conflict: true }, { status: 409 });
  }
  let next;
  try {
    next = applyOps(state, x.brief, inp.ops, inp.actor ?? "", now, sha256);
  } catch (e) {
    if (e instanceof DraftError) return Response.json({ error: e.message }, { status: 400 });
    throw e;
  }
  if (next.revision === state.draft.revision) {
    return Response.json({ ...body(x.stored, x.brief, state), unchanged: true });
  }
  const saved = await saveDraft(x.stored, next);
  if (!saved.ok) {
    return Response.json({ error: saved.error, conflict: saved.conflict }, { status: saved.conflict ? 409 : 502 });
  }
  return Response.json(body(x.stored, x.brief, draftState(next, x.brief, sha256, now)));
}
