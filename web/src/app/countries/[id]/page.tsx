import { loadBundle, indexBy, visibleEvents } from "@/lib/db";
import { PageHeader, EventCard } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

const FLEET_STATUS_ORDER = ["active", "on_order", "option", "selected", "negotiation", "retiring", "retired"];
const FLEET_STATUS_LABEL: Record<string, string> = {
  active: "Active", on_order: "On order", option: "Option",
  selected: "Selected", negotiation: "In negotiation",
  retiring: "Retiring", retired: "Retired",
};

export default async function CountryPage({ params }: { params: { id: string } }) {
  const b = await loadBundle();
  const country = b.countries.find((c) => c.country_id === params.id);
  if (!country) {
    return <p className="text-sm text-slate-500">Unknown country.</p>;
  }
  const typeIdx = indexBy(b.types, "type_id");
  const articleIdx = indexBy(b.articles, "article_id");

  const fleets = b.fleets
    .filter((f) => f.country_id === country.country_id)
    .sort((a, z) =>
      FLEET_STATUS_ORDER.indexOf(a.fleet_status) - FLEET_STATUS_ORDER.indexOf(z.fleet_status));

  const events = visibleEvents(b).filter(
    (e) => e.country_id === country.country_id || e.counterparty_country_id === country.country_id);

  return (
    <div>
      <PageHeader title={country.name} description={country.region ?? undefined} />

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">Fleet baseline</h2>
        {fleets.length === 0 ? (
          <p className="text-sm text-slate-600">
            No baseline recorded yet — fleet rows can be added via CSV import (Sprint 3) or SQL.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/60 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Aircraft</th>
                  <th className="px-3 py-2">Variant</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 text-right">Qty</th>
                  <th className="px-3 py-2">As of</th>
                </tr>
              </thead>
              <tbody>
                {fleets.map((f) => {
                  const t = typeIdx.get(f.type_id);
                  return (
                    <tr key={f.fleet_id} className="border-t border-slate-800/60">
                      <td className="px-3 py-2">
                        {t ? (
                          <Link href={`/aircraft/${t.type_id}`} className="text-cyan-400 hover:text-cyan-300">
                            {t.name}
                          </Link>
                        ) : f.type_id}
                      </td>
                      <td className="px-3 py-2 text-slate-400">{f.variant ?? "—"}</td>
                      <td className="px-3 py-2 text-slate-300">
                        {FLEET_STATUS_LABEL[f.fleet_status] ?? f.fleet_status}
                      </td>
                      <td className="px-3 py-2 text-right text-slate-200">{f.quantity ?? "—"}</td>
                      <td className="px-3 py-2 text-slate-500">{f.as_of ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-200">
          Event timeline <span className="font-normal text-slate-500">({events.length})</span>
        </h2>
        <div className="space-y-3">
          {events.map((ev) => (
            <EventCard key={ev.event_id} ev={ev} showCountry={false}
              article={ev.article_id ? articleIdx.get(ev.article_id) : undefined}
              type={ev.type_id ? typeIdx.get(ev.type_id) : undefined} />
          ))}
          {events.length === 0 && <p className="text-sm text-slate-600">No events recorded yet.</p>}
        </div>
      </section>
    </div>
  );
}
