"use client";

import { useEffect, useMemo, useState } from "react";
import { EventBadge } from "@/components/ui";

interface PendingEvent {
  event_id: number;
  event_type: string;
  country_id: string | null;
  type_id: string | null;
  quantity: number | null;
  value_usd_m: number | null;
  event_date: string | null;
  summary: string;
  confidence: number | null;
  unresolved_type_name: string | null;
  unresolved_country_name: string | null;
  created_at: string;
  // Tanacsado besorolas (scripts/triage_events.py) — a dontes emberi marad.
  triage?: {
    country?: string; aircraft?: string; source?: string; source_tier?: string;
    domain?: string; stage?: string; hu_relevance?: string; relevance?: number | null;
    novelty?: string; duplicate_probability?: string; duplicate_of?: number | null;
    materiality?: string; triage_class?: string; rationale?: string;
  } | null;
}

const CLASS_ORDER: Record<string, number> = {
  likely_material: 0, routine: 1, likely_duplicate: 2, low_relevance: 3,
};
const CLASS_STYLE: Record<string, string> = {
  likely_material: "border-emerald-500/50 text-emerald-300",
  routine: "border-slate-600 text-slate-300",
  likely_duplicate: "border-amber-500/50 text-amber-300",
  low_relevance: "border-rose-500/50 text-rose-300",
};

const SUPA_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export default function ReviewPage() {
  const [events, setEvents] = useState<PendingEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await fetch(
        `${SUPA_URL}/rest/v1/ac_events?review_status=eq.pending&order=created_at.desc&limit=500`,
        { headers: { apikey: ANON_KEY, Authorization: `Bearer ${ANON_KEY}` } });
      const rows = (await res.json()) as PendingEvent[];
      // A triage szerinti sorrend: elol a valoszinuleg anyagi tetelek.
      rows.sort((a, b) => (CLASS_ORDER[a.triage?.triage_class ?? ""] ?? 4)
        - (CLASS_ORDER[b.triage?.triage_class ?? ""] ?? 4));
      setEvents(rows);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);

  async function decide(ids: number[], action: "approve" | "reject" | "approve_apply") {
    setBusy((b) => new Set([...b, ...ids]));
    for (const id of ids) {
      try {
        const res = await fetch("/api/admin/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event_id: id, action }),
        });
        if (res.ok) {
          setEvents((evs) => evs.filter((e) => e.event_id !== id));
          setSelected((s) => { const n = new Set(s); n.delete(id); return n; });
        }
      } catch { /* keep going */ }
    }
    setBusy((b) => { const n = new Set(b); ids.forEach((i) => n.delete(i)); return n; });
  }

  const resolvable = useMemo(
    () => events.filter((e) => e.country_id && e.type_id).map((e) => e.event_id),
    [events]);
  const byClass = (k: string[]) =>
    events.filter((e) => k.includes(e.triage?.triage_class ?? "")).map((e) => e.event_id);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    events.forEach((e) => { const k = e.triage?.triage_class ?? "untriaged"; c[k] = (c[k] ?? 0) + 1; });
    return c;
  }, [events]);

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Review queue</h1>
        <p className="mt-1 text-sm text-slate-500">
          {events.length} pending extracted events — approve what belongs on the public pages.
          The triage is advisory: it sorts the queue, the decision stays yours.
        </p>
        <p className="mt-1 flex flex-wrap gap-2 text-[11px]">
          {Object.entries(counts).map(([k, v]) => (
            <span key={k} className={`rounded border px-1.5 py-0.5 ${CLASS_STYLE[k] ?? "border-slate-700 text-slate-400"}`}>
              {k.replace("_", " ")}: {v}
            </span>
          ))}
        </p>
      </header>

      {error && <p className="mb-4 text-sm text-rose-400">{error}</p>}

      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-violet-500/30 bg-violet-500/5 p-3">
        <button onClick={() => setSelected(new Set(events.map((e) => e.event_id)))}
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500">
          Select all
        </button>
        <button onClick={() => setSelected(new Set(resolvable))}
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500">
          Select resolved only
        </button>
        <button onClick={() => setSelected(new Set(byClass(["likely_material"])))}
                className="rounded border border-emerald-700 px-2 py-1 text-xs text-emerald-300 hover:border-emerald-500">
          Select likely material
        </button>
        <button onClick={() => setSelected(new Set(byClass(["likely_duplicate", "low_relevance"])))}
                className="rounded border border-amber-700 px-2 py-1 text-xs text-amber-300 hover:border-amber-500">
          Select duplicates + low relevance
        </button>
        <button onClick={() => setSelected(new Set())}
                className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500">
          Clear
        </button>
        <span className="text-xs text-slate-500">{selected.size} selected</span>
        <div className="ml-auto flex gap-2">
          <button onClick={() => decide([...selected], "approve")} disabled={selected.size === 0}
                  className="rounded bg-emerald-600/80 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-40">
            Approve selected
          </button>
          <button onClick={() => decide([...selected], "reject")} disabled={selected.size === 0}
                  className="rounded bg-rose-600/80 px-3 py-1 text-xs font-medium text-white hover:bg-rose-600 disabled:opacity-40">
            Reject selected
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : (
        <div className="space-y-2">
          {events.map((e) => (
            <div key={e.event_id}
                 className={`flex items-start gap-3 rounded-lg border p-3 ${
                   busy.has(e.event_id) ? "opacity-40" : ""} ${
                   selected.has(e.event_id) ? "border-violet-500/50 bg-violet-500/5" : "border-slate-800 bg-slate-900/40"}`}>
              <input type="checkbox" checked={selected.has(e.event_id)}
                     onChange={() => setSelected((s) => {
                       const n = new Set(s);
                       if (n.has(e.event_id)) n.delete(e.event_id); else n.add(e.event_id);
                       return n;
                     })}
                     className="mt-1" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <EventBadge type={e.event_type} />
                  <span className="text-xs text-slate-400">
                    {e.country_id ?? e.unresolved_country_name ?? "?"} · {e.type_id ?? e.unresolved_type_name ?? "?"}
                  </span>
                  {!e.country_id && <span className="text-[11px] text-amber-400">country unresolved</span>}
                  {!e.type_id && <span className="text-[11px] text-amber-400">type unresolved</span>}
                  {e.quantity != null && <span className="text-xs text-slate-500">× {e.quantity}</span>}
                  {e.confidence != null && (
                    <span className="text-[11px] text-slate-600">conf {Number(e.confidence).toFixed(2)}</span>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-300">{e.summary}</p>
                {e.triage && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-400">
                    <span className={`rounded border px-1.5 py-0.5 font-medium ${CLASS_STYLE[e.triage.triage_class ?? ""] ?? ""}`}>
                      {(e.triage.triage_class ?? "").replace("_", " ")}
                    </span>
                    <span>{e.triage.country ?? "?"} · {e.triage.domain ?? "?"} · {e.triage.stage ?? "?"}</span>
                    <span>· HU {e.triage.hu_relevance ?? "—"}</span>
                    <span>· {e.triage.source ?? "?"} ({e.triage.source_tier ?? "?"})</span>
                    {e.triage.relevance != null && <span>· AI relevance {e.triage.relevance}</span>}
                    <span>· {e.triage.novelty}</span>
                    <span>· duplicate {e.triage.duplicate_probability}{e.triage.duplicate_of ? ` (#${e.triage.duplicate_of})` : ""}</span>
                    <span className="w-full text-slate-500">{e.triage.rationale}</span>
                  </div>
                )}
              </div>
              <div className="flex shrink-0 gap-1.5">
                {e.country_id && e.type_id && e.quantity != null &&
                  ["order", "delivery", "retirement", "incident"].includes(e.event_type) && (
                  <button onClick={() => decide([e.event_id], "approve_apply")}
                          title="Approve AND apply to fleet baseline (order -> on_order, delivery -> active, retirement/incident -> active-)"
                          className="rounded bg-cyan-600/70 px-2 py-1 text-xs text-white hover:bg-cyan-600">
                    ✓+fleet
                  </button>
                )}
                <button onClick={() => decide([e.event_id], "approve")}
                        className="rounded bg-emerald-600/70 px-2 py-1 text-xs text-white hover:bg-emerald-600">✓</button>
                <button onClick={() => decide([e.event_id], "reject")}
                        className="rounded bg-rose-600/70 px-2 py-1 text-xs text-white hover:bg-rose-600">✗</button>
              </div>
            </div>
          ))}
          {events.length === 0 && <p className="text-sm text-slate-600">Queue is empty — nice.</p>}
        </div>
      )}
    </div>
  );
}
