import Link from "next/link";
import { EventBadge } from "@/components/ui";

export interface ReportPayload {
  stats: {
    events_this_week: number; events_prev_week: number; events_prev_4wk_avg: number;
    firm_deals: number; aircraft_in_firm_deals: number;
    disclosed_value_usd_m: number; pending_review: number;
  };
  overview: string;
  key_deals: ReportEvent[];
  by_type: { event_type: string; count: number; note?: string | null }[];
  by_region: { region: string; count: number; countries: string[] }[];
  watchlist: {
    items: ReportEvent[];
    assessment: { near_term?: string; long_term?: string };
  };
}

interface ReportEvent {
  event_id: number; event_type: string;
  country_id: string | null; country: string;
  type_id: string | null; aircraft: string;
  quantity: number | null; value_usd_m: number | null;
  summary: string; pending: boolean;
  article_title: string | null; article_url: string | null;
  analyst_comment?: string | null;
}

const PIE_COLORS: Record<string, string> = {
  order: "#10b981", delivery: "#06b6d4", upgrade: "#8b5cf6",
  export_sale: "#f59e0b", selection: "#14b8a6", negotiation: "#0ea5e9",
  retirement: "#f43f5e", incident: "#ef4444", other: "#64748b",
};

function Donut({ slices }: { slices: { event_type: string; count: number }[] }) {
  const total = slices.reduce((s, x) => s + x.count, 0) || 1;
  let offset = 25; // start at 12 o'clock
  return (
    <svg viewBox="0 0 42 42" className="h-44 w-44">
      <circle cx="21" cy="21" r="15.9" fill="none" stroke="#1e293b" strokeWidth="6" />
      {slices.map((s) => {
        const pct = (s.count / total) * 100;
        const el = (
          <circle key={s.event_type} cx="21" cy="21" r="15.9" fill="none"
            stroke={PIE_COLORS[s.event_type] ?? PIE_COLORS.other} strokeWidth="6"
            strokeDasharray={`${pct} ${100 - pct}`} strokeDashoffset={offset}
            pathLength={100} />
        );
        offset -= pct;
        return el;
      })}
      <text x="21" y="20" textAnchor="middle" className="fill-slate-100"
            style={{ font: "bold 6px sans-serif" }}>{total}</text>
      <text x="21" y="26" textAnchor="middle" className="fill-slate-500"
            style={{ font: "3px sans-serif" }}>events</text>
    </svg>
  );
}

function DealCard({ ev }: { ev: ReportEvent }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 print:border-slate-300">
      <div className="flex flex-wrap items-center gap-2">
        <EventBadge type={ev.event_type} />
        {ev.country_id
          ? <Link href={`/countries/${ev.country_id}`} className="text-xs font-medium text-slate-300 hover:text-cyan-300">{ev.country}</Link>
          : <span className="text-xs text-slate-400">{ev.country}</span>}
        {ev.type_id
          ? <Link href={`/aircraft/${ev.type_id}`} className="text-xs font-medium text-cyan-400 hover:text-cyan-300">{ev.aircraft}</Link>
          : <span className="text-xs text-slate-400">{ev.aircraft}</span>}
        {ev.quantity != null && <span className="text-xs text-slate-400">× {ev.quantity}</span>}
        {ev.value_usd_m != null && (
          <span className="text-xs text-slate-400">${Number(ev.value_usd_m).toLocaleString()}M</span>
        )}
      </div>
      <p className="mt-2 text-sm text-slate-300">{ev.summary}</p>
      {ev.analyst_comment && (
        <p className="mt-2 border-l-2 border-cyan-500/50 pl-2 text-xs italic text-cyan-200/80">
          {ev.analyst_comment}
        </p>
      )}
      {ev.article_url && (
        <a href={ev.article_url} target="_blank" rel="noopener noreferrer"
           className="mt-1 inline-block text-xs text-slate-500 hover:text-cyan-400 print:hidden">
          {ev.article_title ?? "source"} ↗
        </a>
      )}
    </div>
  );
}

export function WeeklyReportView({
  payload, weekLabel, periodStart, periodEnd,
}: {
  payload: ReportPayload; weekLabel: string; periodStart: string; periodEnd: string;
}) {
  const s = payload.stats;
  const wowDelta = s.events_this_week - s.events_prev_week;
  const groupedWatch = new Map<string, ReportEvent[]>();
  for (const it of payload.watchlist.items) {
    if (!groupedWatch.has(it.event_type)) groupedWatch.set(it.event_type, []);
    groupedWatch.get(it.event_type)!.push(it);
  }

  return (
    <div className="report-body">
      {/* 1. Overview */}
      <section className="mb-8 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5 print:border-slate-300">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-cyan-300">The week in one paragraph</h2>
          <span className="text-xs text-slate-500">
            {weekLabel} · {periodStart} → {periodEnd}
          </span>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">{payload.overview}</p>
        <div className="mt-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
          <div><p className="text-lg font-semibold text-slate-100">{s.events_this_week}</p>
            <p className="text-xs text-slate-500">events ({wowDelta >= 0 ? "+" : ""}{wowDelta} WoW · 4-wk avg {s.events_prev_4wk_avg})</p></div>
          <div><p className="text-lg font-semibold text-slate-100">{s.firm_deals}</p>
            <p className="text-xs text-slate-500">firm deals</p></div>
          <div><p className="text-lg font-semibold text-slate-100">{s.aircraft_in_firm_deals}</p>
            <p className="text-xs text-slate-500">aircraft</p></div>
          <div><p className="text-lg font-semibold text-slate-100">${s.disclosed_value_usd_m.toLocaleString()}M</p>
            <p className="text-xs text-slate-500">disclosed value</p></div>
        </div>
      </section>

      {/* 2. Key deals */}
      {payload.key_deals.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Key deals of the week</h2>
          <div className="space-y-3">
            {payload.key_deals.map((ev) => <DealCard key={ev.event_id} ev={ev} />)}
          </div>
        </section>
      )}

      {/* 3. Activity breakdown: pie + slice notes + regions */}
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">Activity breakdown</h2>
        <div className="grid gap-6 md:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center gap-3">
            <Donut slices={payload.by_type} />
            <div className="flex max-w-[200px] flex-wrap justify-center gap-x-3 gap-y-1">
              {payload.by_type.map((t) => (
                <span key={t.event_type} className="flex items-center gap-1 text-[11px] text-slate-400">
                  <span className="inline-block h-2 w-2 rounded-full"
                        style={{ backgroundColor: PIE_COLORS[t.event_type] ?? PIE_COLORS.other }} />
                  {t.event_type.replace(/_/g, " ")} ({t.count})
                </span>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            {payload.by_type.filter((t) => t.note).map((t) => (
              <div key={t.event_type} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 print:border-slate-300">
                <div className="flex items-center gap-2">
                  <EventBadge type={t.event_type} />
                  <span className="text-xs text-slate-500">{t.count} events</span>
                </div>
                <p className="mt-1 text-sm text-slate-300">{t.note}</p>
              </div>
            ))}
            {payload.by_region.length > 0 && (
              <div className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 print:border-slate-300">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">By region</p>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                  {payload.by_region.map((r) => (
                    <span key={r.region} className="text-xs text-slate-400">
                      <span className="text-slate-200">{r.region}</span> {r.count}
                      <span className="text-slate-600"> ({r.countries.slice(0, 4).join(", ")}{r.countries.length > 4 ? "…" : ""})</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* 4. Watchlist grouped + assessment */}
      {payload.watchlist.items.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Watchlist — deals in the making</h2>
          <div className="space-y-4">
            {[...groupedWatch.entries()].map(([etype, items]) => (
              <div key={etype}>
                <div className="mb-1.5 flex items-center gap-2">
                  <EventBadge type={etype} />
                  <span className="text-xs text-slate-500">{items.length}</span>
                </div>
                <div className="space-y-1.5">
                  {items.map((it) => (
                    <p key={it.event_id} className="border-l border-slate-700 pl-2 text-sm text-slate-400">
                      <span className="text-slate-300">{it.country}</span> / {it.aircraft} — {it.summary}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {(payload.watchlist.assessment?.near_term || payload.watchlist.assessment?.long_term) && (
            <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 print:border-slate-300">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-300">Analyst assessment</h3>
              {payload.watchlist.assessment.near_term && (
                <p className="mt-2 text-sm text-slate-300">
                  <span className="font-medium text-slate-200">Near term: </span>
                  {payload.watchlist.assessment.near_term}
                </p>
              )}
              {payload.watchlist.assessment.long_term && (
                <p className="mt-2 text-sm text-slate-300">
                  <span className="font-medium text-slate-200">Long term: </span>
                  {payload.watchlist.assessment.long_term}
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
