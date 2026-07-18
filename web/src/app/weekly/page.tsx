import { loadBundle, indexBy, visibleEvents, type FleetEvent } from "@/lib/db";
import { PageHeader, EventBadge, EventCard } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

const DAY = 24 * 3600 * 1000;

/** Weekly report — computed live from the last 7 days of events, so it is
 * always current and costs nothing to generate. Structured to be readable
 * top-down: headline -> key deals -> by category -> by region -> watchlist. */
export default async function WeeklyReport() {
  const b = await loadBundle();
  const countryIdx = indexBy(b.countries, "country_id");
  const typeIdx = indexBy(b.types, "type_id");
  const articleIdx = indexBy(b.articles, "article_id");

  const now = Date.now();
  const events = visibleEvents(b);
  const thisWeek = events.filter((e) => now - new Date(e.created_at).getTime() < 7 * DAY);
  const prevWeek = events.filter((e) => {
    const age = now - new Date(e.created_at).getTime();
    return age >= 7 * DAY && age < 14 * DAY;
  });

  const hardEvents = thisWeek.filter((e) => ["order", "delivery", "export_sale"].includes(e.event_type));
  const totalValue = thisWeek.reduce((s, e) => s + (Number(e.value_usd_m) || 0), 0);
  const totalAircraft = hardEvents.reduce((s, e) => s + (e.quantity || 0), 0);

  // Key deals: firm events ranked by disclosed value, then quantity
  const keyDeals = [...hardEvents].sort((a, z) =>
    (Number(z.value_usd_m) || 0) - (Number(a.value_usd_m) || 0) ||
    (z.quantity || 0) - (a.quantity || 0)).slice(0, 6);

  // Grouping helpers
  const groupBy = (evs: FleetEvent[], key: (e: FleetEvent) => string | null) => {
    const m = new Map<string, FleetEvent[]>();
    for (const e of evs) {
      const k = key(e);
      if (!k) continue;
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(e);
    }
    return [...m.entries()].sort((a, z) => z[1].length - a[1].length);
  };

  const byType = groupBy(thisWeek, (e) => e.event_type);
  const byRegion = groupBy(thisWeek,
    (e) => (e.country_id ? countryIdx.get(e.country_id)?.region ?? null : null));
  const watchlist = thisWeek.filter((e) => ["negotiation", "selection"].includes(e.event_type));

  const weekStart = new Date(now - 7 * DAY).toISOString().slice(0, 10);
  const weekEnd = new Date(now).toISOString().slice(0, 10);
  const delta = thisWeek.length - prevWeek.length;

  return (
    <div>
      <PageHeader
        title="Weekly report"
        description={`${weekStart} → ${weekEnd} — auto-generated from ${thisWeek.length} events captured this week.`}
      />

      {/* 1. Headline */}
      <section className="mb-8 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
        <h2 className="text-sm font-semibold text-cyan-300">The week in one paragraph</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          {thisWeek.length === 0
            ? "No fleet events were captured this week."
            : <>
                <strong className="text-slate-100">{thisWeek.length} events</strong> were recorded
                ({delta >= 0 ? `+${delta}` : delta} vs. previous week), of which{" "}
                <strong className="text-slate-100">{hardEvents.length} were firm</strong> (orders,
                deliveries or sales) covering <strong className="text-slate-100">
                {totalAircraft} aircraft</strong>
                {totalValue > 0 && <> with a disclosed value of{" "}
                <strong className="text-slate-100">${Math.round(totalValue).toLocaleString()}M</strong></>}.
                {" "}The most active region was{" "}
                <strong className="text-slate-100">{byRegion[0]?.[0] ?? "—"}</strong>
                {watchlist.length > 0 && <>, and {watchlist.length} deals are in the
                negotiation/selection pipeline worth watching</>}.
              </>}
        </p>
      </section>

      {/* 2. Key deals */}
      {keyDeals.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Key deals of the week</h2>
          <div className="space-y-3">
            {keyDeals.map((ev) => (
              <EventCard key={ev.event_id} ev={ev}
                article={ev.article_id ? articleIdx.get(ev.article_id) : undefined}
                country={ev.country_id ? countryIdx.get(ev.country_id) : undefined}
                type={ev.type_id ? typeIdx.get(ev.type_id) : undefined} />
            ))}
          </div>
        </section>
      )}

      <div className="mb-8 grid gap-8 md:grid-cols-2">
        {/* 3. By event type */}
        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Activity by event type</h2>
          <div className="space-y-1.5">
            {byType.map(([t, evs]) => (
              <div key={t} className="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2">
                <EventBadge type={t} />
                <div className="h-1.5 flex-1 rounded bg-slate-800">
                  <div className="h-1.5 rounded bg-cyan-500/60"
                       style={{ width: `${(evs.length / thisWeek.length) * 100}%` }} />
                </div>
                <span className="w-6 text-right text-xs text-slate-400">{evs.length}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 4. By region */}
        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Activity by region</h2>
          <div className="space-y-1.5">
            {byRegion.map(([region, evs]) => (
              <div key={region} className="rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-300">{region}</span>
                  <span className="text-xs text-slate-500">{evs.length} events</span>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {[...new Set(evs.map((e) => e.country_id && countryIdx.get(e.country_id)?.name)
                    .filter(Boolean))].slice(0, 6).join(", ")}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* 5. Watchlist */}
      {watchlist.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold text-slate-200">Watchlist — deals in the making</h2>
          <p className="mb-3 text-xs text-slate-500">
            Negotiations, approvals and selections that have not been signed yet — these are next
            week&apos;s potential orders.
          </p>
          <div className="space-y-2">
            {watchlist.map((ev) => {
              const c = ev.country_id ? countryIdx.get(ev.country_id) : undefined;
              const t = ev.type_id ? typeIdx.get(ev.type_id) : undefined;
              return (
                <div key={ev.event_id} className="flex items-start gap-2 rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2">
                  <EventBadge type={ev.event_type} />
                  <div className="min-w-0">
                    <p className="text-sm text-slate-300">{ev.summary}</p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {c && <Link href={`/countries/${c.country_id}`} className="hover:text-cyan-400">{c.name}</Link>}
                      {c && t && " · "}
                      {t && <Link href={`/aircraft/${t.type_id}`} className="hover:text-cyan-400">{t.name}</Link>}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
