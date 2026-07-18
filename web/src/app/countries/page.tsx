import { loadBundle, approvedEvents } from "@/lib/db";
import { PageHeader } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function CountriesPage() {
  const b = await loadBundle();
  const events = approvedEvents(b);

  const eventCount = new Map<string, number>();
  for (const e of events) {
    if (e.country_id) eventCount.set(e.country_id, (eventCount.get(e.country_id) ?? 0) + 1);
  }
  const fleetCount = new Map<string, number>();
  for (const f of b.fleets) {
    fleetCount.set(f.country_id, (fleetCount.get(f.country_id) ?? 0) + 1);
  }

  const regions = new Map<string, typeof b.countries>();
  for (const c of b.countries) {
    const r = c.region ?? "Other";
    if (!regions.has(r)) regions.set(r, []);
    regions.get(r)!.push(c);
  }
  const sorted = [...regions.entries()].sort((a, z) => a[0].localeCompare(z[0]));

  return (
    <div>
      <PageHeader title="Countries" description="Operators grouped by region — event and fleet counts at a glance." />
      <div className="space-y-8">
        {sorted.map(([region, countries]) => (
          <section key={region}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{region}</h2>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {countries.sort((a, z) => a.name.localeCompare(z.name)).map((c) => (
                <Link key={c.country_id} href={`/countries/${c.country_id}`}
                      className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2.5 hover:border-slate-600">
                  <span className="text-sm text-slate-200">{c.name}</span>
                  <span className="flex gap-3 text-xs text-slate-500">
                    {(fleetCount.get(c.country_id) ?? 0) > 0 && (
                      <span>{fleetCount.get(c.country_id)} fleet</span>
                    )}
                    {(eventCount.get(c.country_id) ?? 0) > 0 && (
                      <span className="text-cyan-500">{eventCount.get(c.country_id)} events</span>
                    )}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
