import { loadBundle, approvedEvents } from "@/lib/db";
import { PageHeader } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

const CATEGORY_ORDER = ["fighter", "bomber", "attack", "helicopter", "transport",
  "tanker", "special_mission", "maritime_patrol", "trainer", "uav"];
const CATEGORY_LABEL: Record<string, string> = {
  fighter: "Fighters", bomber: "Bombers", attack: "Attack",
  helicopter: "Helicopters", transport: "Transport", tanker: "Tankers",
  special_mission: "Special mission / AEW&C", maritime_patrol: "Maritime patrol",
  trainer: "Trainers", uav: "Large UAVs",
};

export default async function AircraftPage() {
  const b = await loadBundle();
  const events = approvedEvents(b);
  const eventCount = new Map<string, number>();
  for (const e of events) {
    if (e.type_id) eventCount.set(e.type_id, (eventCount.get(e.type_id) ?? 0) + 1);
  }
  const operatorCount = new Map<string, number>();
  for (const f of b.fleets) {
    if (f.fleet_status === "active") {
      operatorCount.set(f.type_id, (operatorCount.get(f.type_id) ?? 0) + 1);
    }
  }

  const byCategory = new Map<string, typeof b.types>();
  for (const t of b.types) {
    if (!byCategory.has(t.category)) byCategory.set(t.category, []);
    byCategory.get(t.category)!.push(t);
  }

  return (
    <div>
      <PageHeader title="Aircraft catalogue"
        description="Tracked military aircraft types with base data — click a type for operators and event history." />
      <div className="space-y-8">
        {CATEGORY_ORDER.filter((c) => byCategory.has(c)).map((cat) => (
          <section key={cat}>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              {CATEGORY_LABEL[cat] ?? cat}
            </h2>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {byCategory.get(cat)!.sort((a, z) => a.name.localeCompare(z.name)).map((t) => (
                <Link key={t.type_id} href={`/aircraft/${t.type_id}`}
                      className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2.5 hover:border-slate-600">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-200">{t.name}</span>
                    {(eventCount.get(t.type_id) ?? 0) > 0 && (
                      <span className="text-xs text-cyan-500">{eventCount.get(t.type_id)} events</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {t.manufacturer}
                    {t.production_status === "in_development" && " · in development"}
                  </p>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
