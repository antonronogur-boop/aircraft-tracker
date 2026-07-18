import { loadBundle, indexBy, visibleEvents } from "@/lib/db";
import { PageHeader, EventCard } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function AircraftDetailPage({ params }: { params: { id: string } }) {
  const b = await loadBundle();
  const type = b.types.find((t) => t.type_id === params.id);
  if (!type) return <p className="text-sm text-slate-500">Unknown aircraft type.</p>;

  const countryIdx = indexBy(b.countries, "country_id");
  const articleIdx = indexBy(b.articles, "article_id");
  const fleets = b.fleets.filter((f) => f.type_id === type.type_id);
  const events = visibleEvents(b).filter((e) => e.type_id === type.type_id);

  const facts: Array<[string, string | null]> = [
    ["Designation", type.designation],
    ["Category", type.category],
    ["Manufacturer", type.manufacturer],
    ["Origin", countryIdx.get(type.origin_country ?? "")?.name ?? type.origin_country],
    ["Role", type.role],
    ["First flight", type.first_flight_year ? String(type.first_flight_year) : null],
    ["Production", type.production_status?.replace(/_/g, " ") ?? null],
  ];

  return (
    <div>
      <PageHeader title={type.name} description={type.role ?? undefined} />

      <div className="grid gap-8 lg:grid-cols-[1fr_2fr]">
        <div className="space-y-6">
          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-200">Base data</h2>
            <dl className="space-y-1.5 text-sm">
              {facts.filter(([, v]) => v).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4">
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="text-right text-slate-300">{v}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-200">
              Operators <span className="font-normal text-slate-500">({fleets.length})</span>
            </h2>
            {fleets.length === 0 ? (
              <p className="text-sm text-slate-600">No fleet baseline yet.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {fleets.map((f) => {
                  const c = countryIdx.get(f.country_id);
                  return (
                    <li key={f.fleet_id} className="flex items-center justify-between">
                      <Link href={`/countries/${f.country_id}`}
                            className="text-slate-300 hover:text-cyan-300">
                        {c?.name ?? f.country_id}
                      </Link>
                      <span className="text-xs text-slate-500">
                        {f.quantity ?? "?"} · {f.fleet_status.replace(/_/g, " ")}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        <section>
          <h2 className="mb-3 text-sm font-semibold text-slate-200">
            Events <span className="font-normal text-slate-500">({events.length})</span>
          </h2>
          <div className="space-y-3">
            {events.map((ev) => (
              <EventCard key={ev.event_id} ev={ev}
                article={ev.article_id ? articleIdx.get(ev.article_id) : undefined}
                country={ev.country_id ? countryIdx.get(ev.country_id) : undefined} />
            ))}
            {events.length === 0 && <p className="text-sm text-slate-600">No events recorded yet.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
