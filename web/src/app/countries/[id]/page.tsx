import { loadBundle, indexBy, visibleEvents, type Fleet } from "@/lib/db";
import { PageHeader, EventCard } from "@/components/ui";
import Link from "next/link";

export const dynamic = "force-dynamic";

const FLEET_STATUS_ORDER = ["active", "on_order", "option", "selected", "negotiation", "retiring", "retired"];
const FLEET_STATUS_LABEL: Record<string, string> = {
  active: "Active", on_order: "On order", option: "Option",
  selected: "Selected", negotiation: "In negotiation",
  retiring: "Retiring", retired: "Retired",
};

// A hitelesites allapota. NEM diszites: ez mondja meg, hogy egy szamra
// szabad-e hivatkozni. A negy ertek negy kulonbozo dolgot jelent, ezert
// mindegyik sajat szinnel es sajat magyarazattal all — az "ellenorizetlen"
// es a "nem ellenorizheto" kulonosen nem ugyanaz.
function VerificationBadge({ row }: { row: Fleet }) {
  const v = row.verification_verdict;
  if (!v) {
    return <span className="text-xs text-slate-600">not reviewed</span>;
  }
  const style: Record<string, string> = {
    confirmed: "border-emerald-700 text-emerald-300",
    corrected: "border-sky-700 text-sky-300",
    unverifiable: "border-amber-700 text-amber-300",
    needs_split: "border-rose-700 text-rose-300",
  };
  const label: Record<string, string> = {
    confirmed: "verified",
    corrected: "corrected",
    unverifiable: "not verifiable",
    needs_split: "record mixes two types",
  };
  const tip = [
    row.verification_note,
    row.verification_source,
    row.verification_confidence ? `confidence: ${row.verification_confidence}` : null,
  ].filter(Boolean).join(" — ");
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span
        title={tip || undefined}
        className={`inline-block w-fit rounded border px-1.5 py-0.5 text-[11px] ${style[v] ?? "border-slate-700 text-slate-400"}`}
      >
        {label[v] ?? v}
      </span>
      {row.program_total != null && (
        // A programkeret KULON all. Egy 29 gepes program nem 29 uzemelo gep —
        // ez volt a kulso ellenorzes leggyakoribb talalata.
        <span className="text-[11px] text-slate-500">
          programme total: {row.program_total}
        </span>
      )}
    </span>
  );
}

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
                  <th className="px-3 py-2">Verification</th>
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
                      {/* A DARABSZAM HELYETT A TUDOTT BIZONYTALANSAG.
                          Ha a kulso ellenorzes azt allapitotta meg, hogy a
                          valos ertek tartomany ("kb. 160-165", "legalabb
                          11"), akkor a regi pontos szamot kiirni hamis
                          pontossag — pont az a hiba, ami ellen az egesz
                          ellenorzes szolt. Ilyenkor a tartomany latszik, a
                          korabbi szam pedig alatta, halvanyan, hogy
                          nyomon kovetheto maradjon. */}
                      <td className="px-3 py-2 text-right text-slate-200">
                        {f.quantity_range_note ? (
                          <span>
                            <span className="text-amber-300">{f.quantity_range_note}</span>
                            {f.quantity != null && (
                              <span className="ml-2 text-xs text-slate-600 line-through">
                                {f.quantity}
                              </span>
                            )}
                          </span>
                        ) : (
                          f.quantity ?? "—"
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-500">
                        {f.verified_as_of ?? f.as_of ?? "—"}
                      </td>
                      <td className="px-3 py-2">
                        <VerificationBadge row={f} />
                      </td>
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
