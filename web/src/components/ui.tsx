import Link from "next/link";
import type { FleetEvent, Article, Country, AircraftType } from "@/lib/db";

export const EVENT_STYLES: Record<string, { label: string; cls: string }> = {
  order:        { label: "Order",        cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
  delivery:     { label: "Delivery",     cls: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30" },
  upgrade:      { label: "Upgrade",      cls: "bg-violet-500/15 text-violet-300 border-violet-500/30" },
  export_sale:  { label: "Export sale",  cls: "bg-amber-500/15 text-amber-300 border-amber-500/30" },
  selection:    { label: "Selection",    cls: "bg-teal-500/15 text-teal-300 border-teal-500/30" },
  negotiation:  { label: "Negotiation",  cls: "bg-sky-500/15 text-sky-300 border-sky-500/30" },
  retirement:   { label: "Retirement",   cls: "bg-rose-500/15 text-rose-300 border-rose-500/30" },
  incident:     { label: "Incident",     cls: "bg-red-500/15 text-red-300 border-red-500/30" },
  other:        { label: "Other",        cls: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
};

export function EventBadge({ type }: { type: string }) {
  const s = EVENT_STYLES[type] ?? EVENT_STYLES.other;
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 text-[11px] font-medium ${s.cls}`}>
      {s.label}
    </span>
  );
}

export function PendingBadge() {
  return (
    <span className="inline-block rounded border border-yellow-500/30 bg-yellow-500/10 px-1.5 py-0.5 text-[11px] text-yellow-300">
      pending review
    </span>
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-xl font-semibold text-slate-100">{title}</h1>
      {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
    </header>
  );
}

export function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-100">{value}</p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function EventCard({
  ev, article, country, type, showCountry = true,
}: {
  ev: FleetEvent;
  article?: Article;
  country?: Country;
  type?: AircraftType;
  showCountry?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <EventBadge type={ev.event_type} />
        {ev.review_status === "pending" && <PendingBadge />}
        {showCountry && (country ? (
          <Link href={`/countries/${country.country_id}`}
                className="text-xs font-medium text-slate-300 hover:text-cyan-300">
            {country.name}
          </Link>
        ) : ev.unresolved_country_name ? (
          <span className="text-xs text-slate-500">{ev.unresolved_country_name}</span>
        ) : null)}
        {type ? (
          <Link href={`/aircraft/${type.type_id}`}
                className="text-xs font-medium text-cyan-400 hover:text-cyan-300">
            {type.name}
          </Link>
        ) : ev.unresolved_type_name ? (
          <span className="text-xs text-slate-500">{ev.unresolved_type_name}</span>
        ) : null}
        {ev.quantity != null && (
          <span className="text-xs text-slate-400">× {ev.quantity}</span>
        )}
        {ev.value_usd_m != null && (
          <span className="text-xs text-slate-400">${Number(ev.value_usd_m).toLocaleString()}M</span>
        )}
        <span className="ml-auto text-xs text-slate-600">
          {ev.event_date ?? ev.created_at?.slice(0, 10)}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-300">{ev.summary}</p>
      {article?.url && (
        <a href={article.url} target="_blank" rel="noopener noreferrer"
           className="mt-1 inline-block text-xs text-slate-500 hover:text-cyan-400">
          {article.title ?? "source"} ↗
        </a>
      )}
    </div>
  );
}
