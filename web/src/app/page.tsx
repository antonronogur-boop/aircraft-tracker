import { loadBundle, indexBy, visibleEvents } from "@/lib/db";
import { PageHeader, StatCard, EventCard } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function Dashboard() {
  const b = await loadBundle();
  const countryIdx = indexBy(b.countries, "country_id");
  const typeIdx = indexBy(b.types, "type_id");
  const articleIdx = indexBy(b.articles, "article_id");

  const events = visibleEvents(b);
  const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const thisWeek = events.filter((e) => new Date(e.created_at).getTime() >= weekAgo);
  const activeCountries = new Set(thisWeek.map((e) => e.country_id).filter(Boolean));
  const pending = b.events.filter((e) => e.review_status === "pending").length;

  // Countries ranked by activity in the feed window
  const perCountry = new Map<string, number>();
  for (const e of thisWeek) {
    if (e.country_id) perCountry.set(e.country_id, (perCountry.get(e.country_id) ?? 0) + 1);
  }
  const movers = [...perCountry.entries()].sort((a, z) => z[1] - a[1]).slice(0, 8);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="What changed in the world's military aircraft fleets — orders, deliveries, upgrades, sales and retirements, extracted from open sources."
      />

      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Events this week" value={thisWeek.length} />
        <StatCard label="Active countries" value={activeCountries.size} sub="with events this week" />
        <StatCard label="Pending review" value={pending} sub="awaiting approval" />
        <StatCard label="Tracked types" value={b.types.length} />
      </div>

      <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Latest signals</h2>
          <div className="space-y-3">
            {events.slice(0, 30).map((ev) => (
              <EventCard
                key={ev.event_id}
                ev={ev}
                article={ev.article_id ? articleIdx.get(ev.article_id) : undefined}
                country={ev.country_id ? countryIdx.get(ev.country_id) : undefined}
                type={ev.type_id ? typeIdx.get(ev.type_id) : undefined}
              />
            ))}
            {events.length === 0 && (
              <p className="text-sm text-slate-600">
                No events yet — run the pipeline (collect_rss.py + process_articles.py).
              </p>
            )}
          </div>
        </section>

        <aside>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">Most active countries</h2>
          <div className="space-y-1.5">
            {movers.map(([cid, n]) => {
              const c = countryIdx.get(cid);
              if (!c) return null;
              return (
                <Link key={cid} href={`/countries/${cid}`}
                      className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-900/40 px-3 py-2 text-sm text-slate-300 hover:border-slate-600">
                  <span>{c.name}</span>
                  <span className="text-xs text-cyan-400">{n} events</span>
                </Link>
              );
            })}
            {movers.length === 0 && <p className="text-sm text-slate-600">Quiet week so far.</p>}
          </div>
        </aside>
      </div>
    </div>
  );
}
