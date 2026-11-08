"use client";

/* COMMAND BRIEF — STRUKTURALT SZERKESZTO (nem Word-klon).
 *
 * Bal oldalt a presentation schema blokkjai (oldalankent), jobb oldalt az
 * elo oldal-elonezet (ugyanaz a komponens, amibol a PDF keszul), oldalankenti
 * tulcsordulas-jelzessel. Csak a publikacios szoveg (copy) szerkesztheto;
 * a forras, lineage, HU, SIG, CONF, horizon, datumok csak olvashatok.
 * Minden mentes verziozott es auditalt (ki, mikor, melyik mezo, elotte/utana).
 */
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { CommandBrief } from "@/components/CommandBrief";
import type { CommandBriefV2 } from "@/lib/briefTypes";
import {
  applyDraft, applyOps, baseItems, fieldId, itemId, statusLabel, DraftError,
  type BriefDraft, type DraftOp, type DraftStatus, type DraftState,
} from "@/lib/briefDraft";
import {
  PRESENTATION, controlledFields, copyFields, getField, hardLimit, type SchemaBlock,
} from "@/lib/presentation";

export interface EditorPayload extends DraftState {
  week_label: string; generated_at: string; template_version: string; brief: CommandBriefV2;
}

const cheapHash = (s: string) => {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return String(h >>> 0);
};

const STATUS_CHIP: Record<string, string> = {
  GENERATED: "border-slate-500 text-slate-200", EDITING: "border-amber-500 text-amber-200",
  READY_FOR_APPROVAL: "border-sky-500 text-sky-200", APPROVED: "border-emerald-500 text-emerald-200",
  RELEASED: "border-emerald-400 bg-emerald-500/20 text-emerald-100",
};

function fmt(v: unknown): string {
  if (v == null || v === "") return "—";
  if (Array.isArray(v)) return v.length ? v.map(fmt).join(", ") : "—";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    if ("level" in o) return String(o.level);
    if ("name" in o) return String(o.name);
    return JSON.stringify(o);
  }
  return String(v);
}

function sentences(t: string) {
  return (t.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [t]).filter((x) => x.trim()).length;
}

export function BriefEditor({ initial }: { initial: EditorPayload }) {
  const [srv, setSrv] = useState<EditorPayload>(initial);
  const [edits, setEdits] = useState<Record<string, string>>({});      // fieldId -> text
  const [reverts, setReverts] = useState<string[]>([]);                 // fieldId
  const [vis, setVis] = useState<Record<string, boolean>>({});         // itemId -> hidden?
  const [orders, setOrders] = useState<Record<string, string[]>>({});  // block -> keys
  const [actor, setActor] = useState("");
  const [token, setToken] = useState("");
  const [needToken, setNeedToken] = useState(false);
  const [tab, setTab] = useState<number | "audit" | "releases">(1);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [overflow, setOverflow] = useState<Record<string, number>>({});
  const previewRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try { setActor(localStorage.getItem("cb_actor") ?? ""); } catch { /* private mode */ }
    try { setToken(sessionStorage.getItem("cb_token") ?? ""); } catch { /* ignore */ }
  }, []);
  useEffect(() => { try { localStorage.setItem("cb_actor", actor); } catch { /* ignore */ } }, [actor]);

  const base = srv.brief;
  const draft = srv.draft;

  // ---- pending ops (a szerkesztett allapot -> muveletek) ----
  const pendingOps = useMemo<DraftOp[]>(() => {
    const ops: DraftOp[] = [];
    for (const [id, value] of Object.entries(edits)) {
      const [b, k, f] = id.split("/");
      ops.push({ type: "set", block: b, key: k, field: f, value });
    }
    for (const id of reverts) {
      const [b, k, f] = id.split("/");
      ops.push({ type: "revert", block: b, key: k, field: f });
    }
    for (const [id, hide] of Object.entries(vis)) {
      const [b, k] = id.split("/");
      ops.push({ type: hide ? "hide" : "show", block: b, key: k });
    }
    for (const [b, keys] of Object.entries(orders)) ops.push({ type: "order", block: b, keys });
    return ops;
  }, [edits, reverts, vis, orders]);

  const { preview, previewError } = useMemo(() => {
    if (!pendingOps.length) return { preview: draft, previewError: null as string | null };
    try {
      return { preview: applyOps(srv, base, pendingOps, actor || "preview", new Date().toISOString(), cheapHash),
               previewError: null as string | null };
    } catch (e) {
      return { preview: draft, previewError: e instanceof DraftError ? e.message : String(e) };
    }
  }, [pendingOps, srv, base, draft, actor]);

  const shown = useMemo(() => applyDraft(base, preview), [base, preview]);
  const dirty = pendingOps.length > 0;

  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  // ---- oldalankenti tulcsordulas (a PDF ugyanezt a DOM-ot nyomtatja) ----
  useLayoutEffect(() => {
    const root = previewRef.current;
    if (!root) return;
    const out: Record<string, number> = {};
    root.querySelectorAll<HTMLElement>(".cb-page").forEach((pg) => {
      const n = pg.getAttribute("data-cb-page") ?? "?";
      const body = pg.querySelector<HTMLElement>(".cb-body");
      if (!body || pg.classList.contains("cb-flow")) return;
      const over = body.scrollHeight - body.clientHeight;
      if (over > 2) out[n] = over;
    });
    setOverflow(out);
  }, [shown]);

  const post = useCallback(async (ops: DraftOp[], okText: string) => {
    if (!actor.trim()) { setMsg({ kind: "err", text: "Enter your name (analyst) first — every change is attributed." }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await fetch(`/api/command-brief/${encodeURIComponent(srv.week_label)}/draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { "x-brief-editor-token": token } : {}) },
        body: JSON.stringify({ actor, expected_revision: srv.draft.revision, ops }),
      });
      const j = await r.json();
      if (r.status === 401) { setNeedToken(true); setMsg({ kind: "err", text: "Editor token required." }); return; }
      if (!r.ok) { setMsg({ kind: "err", text: j.error ?? `save failed (${r.status})` }); return; }
      setSrv(j as EditorPayload);
      setEdits({}); setReverts([]); setVis({}); setOrders({});
      setMsg({ kind: "ok", text: okText });
    } catch (e) {
      setMsg({ kind: "err", text: String(e) });
    } finally { setBusy(false); }
  }, [actor, token, srv]);

  const status = draft.status as DraftStatus;
  const allowed = PRESENTATION.draft.transitions[status] ?? [];
  const overflowPages = Object.keys(overflow);

  // ---- mezo-szintu UI ----
  const fieldValue = (b: SchemaBlock, key: string, f: string, baseVal: string) => {
    const id = fieldId(b.id, key, f);
    if (id in edits) return edits[id];
    if (reverts.includes(id)) return baseVal;
    return draft.overrides[id]?.value ?? baseVal;
  };

  const setText = (id: string, baseVal: string, v: string) => {
    setReverts((r) => r.filter((x) => x !== id));
    setEdits((e) => {
      const n = { ...e };
      const stored = draft.overrides[id]?.value ?? baseVal;
      if (v === stored) delete n[id]; else n[id] = v;
      return n;
    });
  };

  const isHidden = (b: string, k: string) => {
    const id = itemId(b, k);
    return id in vis ? vis[id] : draft.hidden.includes(id);
  };

  const orderOf = (b: SchemaBlock): string[] => {
    const keys = [...baseItems(base, b).keys()];
    const o = orders[b.id] ?? draft.order[b.id];
    if (!o) return keys;
    return [...keys].sort((a, z) => o.indexOf(a) - o.indexOf(z));
  };

  const move = (b: SchemaBlock, k: string, dir: -1 | 1) => {
    const cur = orderOf(b);
    const i = cur.indexOf(k), j = i + dir;
    if (j < 0 || j >= cur.length) return;
    const next = [...cur];
    [next[i], next[j]] = [next[j], next[i]];
    setOrders((o) => ({ ...o, [b.id]: next }));
  };

  // Fuggvenyhivaskent renderelve (nem komponenskent), hogy a textarea
  // gepeles kozben ne veszitse el a fokuszt.
  function renderItem(b: SchemaBlock, k: string, it: Record<string, unknown>, pos: number) {
    const hidden = isHidden(b.id, k);
    const title = [k.startsWith("#") ? `#${pos + 1}` : k, fmt(it.country ?? it.countries ?? "")]
      .filter((x) => x && x !== "—").join(" · ");
    return (
      <div key={k} className={`rounded border p-2 ${hidden ? "border-slate-700 opacity-60" : "border-slate-600"} bg-slate-900/40`}
           data-editor-item={itemId(b.id, k)}>
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs font-bold text-slate-100">{title}</span>
          {controlledFields(b).map((f) => (
            <span key={f.key} title={`${f.label} — controlled analytical metadata (read-only here)`}
                  className="rounded border border-slate-600 bg-slate-800 px-1 text-[10px] text-slate-300"
                  data-controlled={f.key}>
              {f.label}: {fmt(getField(it, f.key))}
            </span>
          ))}
          <span className="ml-auto flex gap-1">
            {b.reorder && <>
              <button type="button" className="rounded border border-slate-600 px-1 text-xs" onClick={() => move(b, k, -1)} aria-label="Move up">↑</button>
              <button type="button" className="rounded border border-slate-600 px-1 text-xs" onClick={() => move(b, k, 1)} aria-label="Move down">↓</button>
            </>}
            {b.hide && (
              <button type="button" className="rounded border border-slate-600 px-1.5 text-[11px]"
                      onClick={() => setVis((v) => ({ ...v, [itemId(b.id, k)]: !hidden }))}>
                {hidden ? "Show" : "Hide"}
              </button>
            )}
          </span>
        </div>
        {!hidden && copyFields(b).map((f) => {
          const baseVal = String(getField(it, f.key) ?? "");
          const id = fieldId(b.id, k, f.key);
          const val = fieldValue(b, k, f.key, baseVal);
          const edited = val !== baseVal;
          const stale = srv.stale.includes(id);
          const hard = hardLimit(f);
          const n = val.length;
          const cls = hard && n > hard ? "text-red-400" : f.max_chars && n > f.max_chars ? "text-amber-300" : "text-slate-500";
          const ns = sentences(val);
          return (
            <label key={f.key} className="mt-1.5 block">
              <span className="flex items-center gap-2 text-[11px] font-semibold text-slate-300">
                {f.label}
                {edited && <span className="rounded bg-amber-500/20 px-1 text-[10px] font-normal text-amber-200">edited</span>}
                {stale && <span className="rounded bg-red-500/20 px-1 text-[10px] font-normal text-red-200" title="The generated text changed after this edit (restatement). Review it.">generated text changed</span>}
                <span className={`ml-auto font-normal ${cls}`}>{n}{f.max_chars ? ` / ${f.max_chars}` : ""}{f.max_sentences && ns > f.max_sentences ? ` · ${ns} sentences (max ${f.max_sentences})` : ""}</span>
              </span>
              <textarea data-field={id} value={val} rows={Math.min(6, Math.max(2, Math.ceil(n / 90)))}
                        onChange={(e) => setText(id, baseVal, e.target.value)}
                        className="mt-0.5 w-full rounded border border-slate-600 bg-slate-950 p-1.5 text-[12.5px] leading-snug text-slate-100 focus:border-sky-500 focus:outline-none" />
              {edited && (
                <details className="text-[10.5px] text-slate-500">
                  <summary className="cursor-pointer">Generated text (analytical layer, unchanged) ·{" "}
                    <button type="button" className="text-sky-400 hover:underline"
                            onClick={(e) => { e.preventDefault(); setEdits((x) => { const c = { ...x }; delete c[id]; return c; });
                                              if (draft.overrides[id]) setReverts((r) => [...r, id]); }}>
                      revert to generated
                    </button>
                  </summary>
                  <p className="mt-0.5 whitespace-pre-wrap">{baseVal}</p>
                </details>
              )}
            </label>
          );
        })}
      </div>
    );
  }

  const pageDef = typeof tab === "number" ? PRESENTATION.pages.find((p) => p.n === tab) : null;

  return (
    <div className="space-y-3" data-brief-editor={srv.week_label}>
      {/* ---- fejlec: statusz, szerzo, muveletek ---- */}
      <div className="sticky top-0 z-10 space-y-2 rounded border border-slate-700 bg-slate-950/95 p-2 backdrop-blur">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`rounded border px-2 py-0.5 font-bold ${STATUS_CHIP[status]}`} data-draft-status={status}>
            {statusLabel(status)}
          </span>
          <span className="text-slate-400">draft rev {draft.revision}</span>
          {draft.approval && <span className="text-emerald-300">approved by {draft.approval.by} · {draft.approval.at}</span>}
          {draft.releases.length > 0 && <span className="text-slate-400">last release R-{draft.releases.at(-1)!.release_no}</span>}
          <span className="text-slate-500">template v{srv.template_version}</span>
          <label className="ml-auto flex items-center gap-1 text-slate-300">
            Analyst
            <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="your name"
                   data-actor className="w-40 rounded border border-slate-600 bg-slate-900 px-1.5 py-0.5 text-slate-100" />
          </label>
          {needToken && (
            <input value={token} type="password" placeholder="editor token"
                   onChange={(e) => { setToken(e.target.value); try { sessionStorage.setItem("cb_token", e.target.value); } catch { /* ignore */ } }}
                   className="w-32 rounded border border-slate-600 bg-slate-900 px-1.5 py-0.5" />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button type="button" disabled={!dirty || busy || !!previewError} data-action="save"
                  onClick={() => post(pendingOps, "Saved.")}
                  className="rounded border border-sky-600 bg-sky-500/15 px-3 py-1 text-sky-100 disabled:opacity-40">
            Save changes{dirty ? ` (${pendingOps.length})` : ""}
          </button>
          {allowed.includes("READY_FOR_APPROVAL") && (
            <button type="button" disabled={busy || !!previewError} data-action="submit"
                    onClick={() => post([...pendingOps, { type: "status", to: "READY_FOR_APPROVAL" }], "Submitted for approval.")}
                    className="rounded border border-slate-500 px-3 py-1 disabled:opacity-40">Submit for approval</button>
          )}
          {allowed.includes("APPROVED") && (
            <button type="button" disabled={busy || dirty || srv.stale.length > 0} data-action="approve"
                    title={dirty ? "Save or discard changes first" : ""}
                    onClick={() => post([{ type: "status", to: "APPROVED" }], "Approved.")}
                    className="rounded border border-emerald-600 bg-emerald-500/15 px-3 py-1 text-emerald-100 disabled:opacity-40">Approve</button>
          )}
          {allowed.includes("RELEASED") && (
            <button type="button" disabled={busy || dirty || srv.approval_invalidated} data-action="release"
                    onClick={() => post([{ type: "release" }], "Released — the canonical PDF is now the release view.")}
                    className="rounded border border-emerald-500 bg-emerald-500/25 px-3 py-1 font-bold text-emerald-50 disabled:opacity-40">Release</button>
          )}
          {allowed.includes("EDITING") && status !== "GENERATED" && (
            <button type="button" disabled={busy} data-action="reopen"
                    onClick={() => post([{ type: "status", to: "EDITING" }], "Back in editing.")}
                    className="rounded border border-slate-600 px-3 py-1">Return to editing</button>
          )}
          {dirty && (
            <button type="button" onClick={() => { setEdits({}); setReverts([]); setVis({}); setOrders({}); }}
                    className="rounded border border-slate-700 px-2 py-1 text-slate-400">Discard</button>
          )}
          <a href={`/weekly/${srv.week_label}/command?view=draft`} target="_blank" rel="noopener noreferrer"
             className="ml-auto text-sky-300 hover:underline">Preview / print draft ↗</a>
          <a href={`/api/command-brief/${srv.week_label}/docx?view=draft`} className="text-sky-300 hover:underline">Word working copy (.docx)</a>
        </div>
        {(msg || previewError || overflowPages.length > 0 || srv.stale.length > 0 || srv.approval_invalidated) && (
          <div className="space-y-0.5 text-[11.5px]">
            {msg && <p className={msg.kind === "ok" ? "text-emerald-300" : "text-red-300"} data-editor-msg={msg.kind}>{msg.text}</p>}
            {previewError && <p className="text-red-300" data-editor-error>{previewError}</p>}
            {overflowPages.map((n) => (
              <p key={n} className="text-amber-300" data-overflow-page={n}>Page {n}: text does not fit the fixed A4 page ({overflow[n]} px over) — shorten it.</p>
            ))}
            {srv.stale.length > 0 && <p className="text-red-300">{srv.stale.length} edited field(s) were written against an older generated text (restatement) — review them before approval.</p>}
            {srv.approval_invalidated && <p className="text-red-300">The generated brief changed after approval — approval is no longer valid.</p>}
          </div>
        )}
        <div className="flex flex-wrap gap-1 text-xs">
          {PRESENTATION.pages.map((p) => (
            <button key={p.n} type="button" onClick={() => setTab(p.n)} data-tab={p.n}
                    className={`rounded px-2 py-0.5 ${tab === p.n ? "bg-slate-200 text-slate-900" : "border border-slate-700 text-slate-300"}`}>
              Page {p.n}{overflow[String(p.n)] ? " ⚠" : ""}
            </button>
          ))}
          <button type="button" onClick={() => setTab("audit")} data-tab="audit"
                  className={`rounded px-2 py-0.5 ${tab === "audit" ? "bg-slate-200 text-slate-900" : "border border-slate-700 text-slate-300"}`}>
            Audit ({draft.audit.length})
          </button>
          <button type="button" onClick={() => setTab("releases")} data-tab="releases"
                  className={`rounded px-2 py-0.5 ${tab === "releases" ? "bg-slate-200 text-slate-900" : "border border-slate-700 text-slate-300"}`}>
            Releases ({draft.releases.length})
          </button>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,46%)_minmax(0,1fr)]">
        <div className="space-y-3">
          {pageDef && pageDef.blocks.map((b) => {
            if (b.kind === "fixed") {
              return (
                <section key={b.id} className="rounded border border-slate-700 p-2 text-[11.5px] text-slate-400">
                  <h3 className="font-semibold text-slate-200">{b.label}</h3>
                  Fixed by the template (v{srv.template_version}). Changing it is a template change, not a weekly edit.
                </section>
              );
            }
            const items = baseItems(base, b);
            const keys = b.kind === "list" ? orderOf(b) : [...items.keys()];
            const editable = copyFields(b).length > 0 || b.hide || b.reorder;
            return (
              <section key={b.id} data-editor-block={b.id}>
                <h3 className="mb-1 text-sm font-semibold text-slate-100">
                  {b.label}
                  {!editable && <span className="ml-2 text-[11px] font-normal text-slate-500">controlled — read-only</span>}
                  {b.max_items && b.kind === "list" && <span className="ml-2 text-[11px] font-normal text-slate-500">max {b.max_items}</span>}
                </h3>
                {keys.length === 0 && <p className="text-[11.5px] text-slate-500">No items this week.</p>}
                <div className="space-y-1.5">
                  {keys.slice(0, b.id === "source_register" ? 40 : 50).map((k, i) => (
                    renderItem(b, k, items.get(k)!, i)
                  ))}
                </div>
              </section>
            );
          })}
          {tab === "audit" && (
            <table className="w-full text-left text-[11px] text-slate-300" data-audit-log>
              <thead className="text-slate-500"><tr><th>rev</th><th>time (UTC)</th><th>actor</th><th>action</th><th>field</th><th>previous → new</th></tr></thead>
              <tbody>
                {[...draft.audit].reverse().map((a, i) => (
                  <tr key={i} className="border-t border-slate-800 align-top">
                    <td className="pr-1 font-mono">{a.rev}</td><td className="pr-1">{a.at}</td><td className="pr-1">{a.actor}</td>
                    <td className="pr-1">{a.action}{a.note ? ` (${a.note})` : ""}</td>
                    <td className="pr-1 font-mono text-[10px]">{a.field ?? ""}</td>
                    <td className="text-[10.5px]">
                      {a.previous !== undefined && <span className="text-red-300/80 line-through">{fmt(a.previous)}</span>}
                      {a.next !== undefined && <span className="text-emerald-300"> {fmt(a.next)}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === "releases" && (
            <div className="space-y-1 text-[12px] text-slate-300">
              {draft.releases.length === 0 && <p className="text-slate-500">Nothing released yet. Approve the draft, then Release.</p>}
              {[...draft.releases].reverse().map((r) => (
                <p key={r.release_no} data-release={r.release_no}>
                  <b>R-{r.release_no}</b> · draft rev {r.draft_rev} · released {r.released_utc} by {r.released_by} · approved by {r.approved_by} ·
                  template v{r.template_version} · method {r.methodology_version} · HU model {r.hu_model_version} ·
                  <span className="font-mono text-[10.5px]"> sha256 {r.content_hash.slice(0, 16)}</span>{" "}
                  <a className="text-sky-300 hover:underline" href={`/weekly/${srv.week_label}/command?release=${r.release_no}`}>view / print</a>
                </p>
              ))}
            </div>
          )}
        </div>
        <div className="min-w-0">
          <p className="mb-1 text-[11px] text-slate-500">Live preview — the canonical PDF prints exactly these pages.</p>
          <div ref={previewRef} className="cb-preview overflow-x-hidden">
            <CommandBrief brief={shown} />
          </div>
        </div>
      </div>
    </div>
  );
}
