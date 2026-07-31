import Link from "next/link";
import { EventBadge } from "@/components/ui";

/* ------------------------------------------------------------------ *
 * AIR POWER DEVELOPMENT INTELLIGENCE BRIEF
 *
 * A jelentes nem azt mondja meg, mi kerult az adatbazisba, hanem hogy
 * melyik fejlemeny valtoztatja meg a legi kepessegkepet, mikorra, es
 * mennyire biztosan. A regi (v1) payloadok is renderelhetok maradnak.
 * ------------------------------------------------------------------ */

export interface ReportPayload {
  schema?: string;
  report_meta?: {
    period_start?: string; period_end?: string; collection_cutoff_utc?: string;
    generated_utc?: string; status?: string; version?: string;
  };
  stats: {
    events_this_week: number; events_prev_week?: number;
    events_prev_4wk_weekly_avg?: number; events_prev_4wk_avg?: number;
    volume_not_comparable?: boolean;
    firm_procurement_actions?: number;
    value?: {
      by_value_type?: Record<string, { usd_m: number; events: number; label: string }>;
      currency_years?: number[] | null; note?: string;
    };
    airframes_by_domain?: Record<string, { airframes: number; actions: number; label: string }>;
    by_lifecycle_stage?: Record<string, number>;
    by_capability_domain?: Record<string, number>;
    by_region?: Record<string, number>;
    collection_health?: {
      unique_events?: number; events_missing_event_date?: number;
      future_dated_excluded?: number; pending_review?: number;
      wow_comparable?: boolean;
    };
    // v1
    firm_deals?: number; aircraft_in_firm_deals?: number;
    disclosed_value_usd_m?: number; pending_review?: number;
  };
  bottom_line?: string;
  key_judgements?: Judgement[];
  judgements_requiring_review?: Judgement[];
  developments?: Development[];
  background_items?: Development[];
  priority_watch?: {
    issue?: string; why_it_matters?: string; next_observable?: string;
    horizon?: string; impact_if_confirmed?: string;
  }[];
  intelligence_gaps?: string[];
  orbat_delta?: {
    country?: string; region?: string;
    entries?: {
      type?: string; domain?: string; active?: number; on_order?: number;
      stored?: number; this_week_stage?: string; this_week_quantity?: number | null;
      expected_ioc_year?: number | null; delivery_window?: string | null;
    }[];
  }[];
  capability_timeline?: {
    year?: number; basis?: string; country?: string; type?: string;
    domain?: string; quantity?: number | null; stage?: string;
  }[];
  maturity_matrix?: Record<string, Record<string, string[]>>;
  self_checks?: { check?: string; item?: string }[];
  annex_events?: ReportEvent[];
  // ---- v1 mezok (visszafele kompatibilitas) ----
  overview?: string;
  key_deals?: ReportEvent[];
  by_type?: { event_type: string; count: number; note?: string | null }[];
  by_region?: { region: string; count: number; countries: string[] }[];
  watchlist?: {
    items: ReportEvent[];
    assessment: { near_term?: string; long_term?: string };
  };
}

interface Judgement {
  id?: string; domain?: string; judgement?: string; confidence?: string;
  basis?: string; assessment?: string; effect_timing?: string;
  alternative_explanation?: string | null; indicators?: string[];
  auto_adjustment?: string; review_reasons?: string[];
}

interface Development {
  title?: string; display_label?: string; capability_domain?: string;
  lifecycle_stage?: string; fact?: string; capability_delta?: string;
  effect_timing?: string; effect_timing_basis?: string; so_what?: string;
  novelty?: string; significance?: number; confidence?: string;
  reports_count?: number; independent_lineages?: number; lineage_note?: string;
  value_usd_m?: number | null; value_type?: string;
  expected_ioc_year?: number | null; indicators_to_watch?: string[];
  auto_adjustment?: string;
}

interface ReportEvent {
  event_id: number; event_type: string;
  lifecycle_stage?: string; capability_domain?: string;
  country_id?: string | null; country: string;
  type_id?: string | null; aircraft: string;
  quantity: number | null; value_usd_m: number | null;
  value_type?: string; event_date?: string | null;
  expected_ioc_year?: number | null;
  summary: string; pending: boolean; undated?: boolean;
  article_title: string | null; article_url: string | null;
  analyst_comment?: string | null;
}

const DOMAIN_LABELS: Record<string, string> = {
  fighter_strike: "Fighter / strike", attack_helicopter: "Attack helicopter",
  air_mobility_rotary: "Air mobility — rotary",
  air_mobility_fixed: "Air mobility — fixed wing",
  uncrewed_cca: "Uncrewed / CCA", counter_uas: "Counter-UAS",
  isr_aew_sigint: "ISR / AEW&C / SIGINT", tanker: "Air-to-air refuelling",
  training: "Training / pilot pipeline", maritime_patrol: "Maritime patrol",
  other: "Other",
};

const STAGE_LABELS: Record<string, string> = {
  requirement: "Requirement", rfi_sources_sought: "RFI / sources sought",
  rfp: "RFP", bid: "Bid", selection: "Selection",
  national_approval: "National approval", export_approval: "Export clearance",
  contract_signed: "Contract signed", production: "In production",
  delivery: "Delivery", ioc: "IOC", foc: "FOC",
  upgrade_programme: "Upgrade programme", retirement: "Retirement",
  loss: "Loss", other: "Other",
};

const TIMING_STYLE: Record<string, string> = {
  immediate: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  "<12 months": "border-amber-500/40 bg-amber-500/10 text-amber-200",
  "1-3 years": "border-sky-500/40 bg-sky-500/10 text-sky-200",
  ">3 years": "border-slate-600 bg-slate-800/60 text-slate-300",
  unknown: "border-slate-700 bg-slate-800/40 text-slate-400",
};

const MATURITY_ORDER = ["Intent", "Committed", "Contracted", "Fielding", "Operational"];

function Chip({ children, cls = "" }: { children: React.ReactNode; cls?: string }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[11px] ${cls || "border-slate-700 bg-slate-800/60 text-slate-300"}`}>
      {children}
    </span>
  );
}

export function WeeklyReportView({
  payload, weekLabel, periodStart, periodEnd,
}: {
  payload: ReportPayload; weekLabel: string; periodStart: string; periodEnd: string;
}) {
  const s = payload.stats;
  const isV2 = payload.schema === "air_power_v2" || (payload.developments?.length ?? 0) > 0;
  const prevAvg = s.events_prev_4wk_weekly_avg ?? s.events_prev_4wk_avg;
  const wow = s.events_prev_week != null ? s.events_this_week - s.events_prev_week : null;
  const val = s.value?.by_value_type ?? {};
  const domains = s.airframes_by_domain ?? {};

  return (
    <div className="report-body">
      {/* ---------- HEADER + BOTTOM LINE ---------- */}
      <section className="print-card mb-8 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5 print:border-slate-300">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-emerald-300">
            {isV2 ? "Bottom line — air power development" : "The week in one paragraph"}
          </h2>
          <span className="text-xs text-slate-500">{weekLabel} · {periodStart} → {periodEnd}</span>
        </div>
        {payload.report_meta && (
          <p className="mt-1 text-[10px] text-slate-600">
            Collection cutoff {payload.report_meta.collection_cutoff_utc}
            {" · generated "}{payload.report_meta.generated_utc}
            {" · "}{payload.report_meta.version}
            {payload.report_meta.status ? ` · ${payload.report_meta.status}` : ""}
          </p>
        )}
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          {payload.bottom_line || payload.overview}
        </p>

        <div className="mt-4 grid grid-cols-2 gap-3 text-center sm:grid-cols-4">
          <div>
            <p className="text-lg font-semibold text-slate-100">{s.events_this_week}</p>
            <p className="text-xs text-slate-500">
              in-period events{s.volume_not_comparable
                ? " (WoW: not comparable)"
                : wow != null ? ` (${wow >= 0 ? "+" : ""}${wow} WoW${prevAvg != null ? ` · 4-wk wkly avg ${prevAvg}` : ""})` : ""}
            </p>
            {s.collection_health && (
              <p className="text-[10px] text-slate-600">
                {(s.collection_health.future_dated_excluded ?? 0) > 0
                  ? `${s.collection_health.future_dated_excluded} future-dated excluded · ` : ""}
                {(s.collection_health.events_missing_event_date ?? 0) > 0
                  ? `${s.collection_health.events_missing_event_date} undated` : "all dated"}
              </p>
            )}
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-100">
              {payload.developments?.length ?? s.firm_deals ?? 0}
            </p>
            <p className="text-xs text-slate-500">
              {isV2 ? "capability developments" : "firm deals"}
            </p>
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-100">
              {s.firm_procurement_actions ?? s.firm_deals ?? 0}
            </p>
            <p className="text-xs text-slate-500">firm procurement actions</p>
          </div>
          {(() => {
            // A fejlec-kartya azt az erteket mutatja, amelyik alapon tenyleg
            // van adat — es MEGNEVEZI az alapot. Egy "signed contract value"
            // cimke unknown-alapu osszeg folott felrevezeto lenne.
            const pick = val.firm ? ["firm", val.firm] as const
              : (Object.entries(val).sort((a, b) => b[1].usd_m - a[1].usd_m)[0] as
                 [string, { usd_m: number; events: number; label: string }] | undefined);
            const amount = pick ? `$${pick[1].usd_m.toLocaleString()}M`
              : s.disclosed_value_usd_m ? `$${s.disclosed_value_usd_m.toLocaleString()}M` : "—";
            return (
              <div>
                <p className="text-lg font-semibold text-slate-100">{amount}</p>
                <p className="text-xs text-slate-500">
                  {pick ? pick[1].label : "disclosed value"}
                </p>
              </div>
            );
          })()}
        </div>

        {/* Ertek ertektipusonkent — az osszeadas tiltva */}
        {Object.keys(val).length > 0 && (
          <div className="mt-3 rounded border border-slate-800 bg-slate-900/40 p-2">
            <p className="text-[11px] font-medium text-slate-400">Disclosed value by basis (not summed)</p>
            <ul className="mt-1 space-y-0.5 text-[11px] text-slate-500">
              {Object.entries(val).map(([k, v]) => (
                <li key={k}>
                  ${v.usd_m.toLocaleString()}M — {v.label} ({v.events} event{v.events === 1 ? "" : "s"})
                </li>
              ))}
            </ul>
            {(s.value?.currency_years?.length ?? 0) > 0 && (
              <p className="mt-1 text-[10px] text-slate-600">
                Figures quoted in {s.value!.currency_years!.join(", ")} prices — not inflation-adjusted.
              </p>
            )}
          </div>
        )}

        {/* Darabszam kepesseg-domainenkent */}
        {Object.keys(domains).length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {Object.entries(domains).sort((a, b) => b[1].airframes - a[1].airframes).map(([k, v]) => (
              <Chip key={k}>{v.label}: {v.airframes} airframes</Chip>
            ))}
            <span className="text-[10px] text-slate-600">
              (airframe counts are not comparable across domains and are never summed)
            </span>
          </div>
        )}
      </section>

      {/* ---------- KEY JUDGEMENTS ---------- */}
      {(payload.key_judgements?.length ?? 0) > 0 && (
        <section className="print-card mb-8 rounded-xl border border-blue-500/25 bg-blue-500/5 p-5 print:border-slate-300">
          <h2 className="text-sm font-semibold text-blue-300">Key judgements</h2>
          <div className="mt-3 space-y-4">
            {payload.key_judgements!.map((j, i) => (
              <div key={j.id ?? i} className="border-l-2 border-blue-500/50 pl-3">
                <p className="text-sm font-medium text-slate-100">
                  <span className="text-blue-300">{j.id ?? "KJ"}</span>
                  {j.domain ? <span className="text-slate-500"> · {DOMAIN_LABELS[j.domain] ?? j.domain}</span> : null}
                  {" — "}{j.judgement}
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <Chip>confidence: {j.confidence ?? "—"}</Chip>
                  {j.effect_timing && (
                    <Chip cls={TIMING_STYLE[j.effect_timing] ?? ""}>effect: {j.effect_timing}</Chip>
                  )}
                </div>
                {j.basis && (
                  <p className="mt-1.5 text-sm text-slate-400">
                    <span className="font-medium text-slate-300">Basis. </span>{j.basis}
                  </p>
                )}
                {j.assessment && (
                  <p className="mt-1 text-sm text-slate-300">
                    <span className="font-medium text-slate-200">Assessment. </span>{j.assessment}
                  </p>
                )}
                {j.alternative_explanation && (
                  <p className="mt-1 text-xs italic text-slate-500">
                    Alternative explanation: {j.alternative_explanation}
                  </p>
                )}
                {(j.indicators ?? []).length > 0 && (
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-500">
                    {j.indicators!.map((x, k) => <li key={k}>Watch: {x}</li>)}
                  </ul>
                )}
                {j.auto_adjustment && (
                  <p className="mt-1 text-[11px] text-amber-300/80">system adjustment: {j.auto_adjustment}</p>
                )}
              </div>
            ))}
          </div>

          {(payload.judgements_requiring_review?.length ?? 0) > 0 && (
            <div className="mt-4 rounded border border-amber-600/40 bg-amber-500/5 p-3">
              <p className="text-xs font-semibold text-amber-300">Withheld — judgements requiring analyst review</p>
              <p className="mt-0.5 text-[11px] text-slate-500">
                These did not pass automated analytical QA and are NOT presented as findings.
              </p>
              <div className="mt-2 space-y-2">
                {payload.judgements_requiring_review!.map((j, i) => (
                  <div key={j.id ?? i} className="border-l-2 border-amber-600/50 pl-2">
                    <p className="text-xs text-slate-400">
                      <span className="text-amber-300">{j.id}</span> — {j.judgement}
                    </p>
                    {(j.review_reasons ?? []).length > 0 && (
                      <p className="text-[11px] text-amber-200/70">failed: {j.review_reasons!.join("; ")}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(payload.intelligence_gaps?.length ?? 0) > 0 && (
            <div className="mt-4 rounded border border-slate-800 bg-slate-900/50 p-3">
              <p className="text-xs font-medium text-slate-300">
                Intelligence gaps — what this period&apos;s collection could not answer
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-500">
                {payload.intelligence_gaps!.map((g, i) => <li key={i}>{g}</li>)}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* ---------- CAPABILITY DEVELOPMENTS ---------- */}
      {(payload.developments?.length ?? 0) > 0 && (
        <section className="mb-8">
          <h2 className="mb-1 text-sm font-semibold text-slate-200">Capability developments this period</h2>
          <p className="mb-3 text-[11px] text-slate-500">
            Selected on capability effect, not on contract value. Lifecycle stage, effect timing,
            confidence and lineage are separate dimensions. Aircraft counts are procurement facts,
            not combat capability.
          </p>
          <div className="space-y-3">
            {payload.developments!.map((d, i) => (
              <div key={i} className="print-card rounded-lg border border-slate-800 bg-slate-900/40 p-3 print:border-slate-300">
                <p className="text-sm font-medium text-slate-200">{d.title}</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <Chip>{DOMAIN_LABELS[d.capability_domain ?? ""] ?? d.capability_domain}</Chip>
                  <Chip>{STAGE_LABELS[d.lifecycle_stage ?? ""] ?? d.lifecycle_stage}</Chip>
                  <Chip cls={TIMING_STYLE[d.effect_timing ?? "unknown"] ?? ""}>
                    effect: {d.effect_timing ?? "unknown"}
                    {d.expected_ioc_year ? ` · IOC ${d.expected_ioc_year}` : ""}
                  </Chip>
                  <Chip>sig {d.significance}/5 · conf {d.confidence}</Chip>
                  <Chip>
                    {d.reports_count ?? 1} report{(d.reports_count ?? 1) === 1 ? "" : "s"} ·{" "}
                    {d.independent_lineages ?? 1} lineage{(d.independent_lineages ?? 1) === 1 ? "" : "s"}
                  </Chip>
                  {d.value_usd_m != null && (
                    <Chip>${d.value_usd_m.toLocaleString()}M · {d.value_type ?? "unknown"}</Chip>
                  )}
                </div>
                {d.fact && <p className="mt-2 text-sm text-slate-300"><span className="font-medium text-slate-200">Fact. </span>{d.fact}</p>}
                {d.capability_delta && (
                  <p className="mt-1.5 border-l-2 border-cyan-500/50 pl-2 text-sm text-cyan-100/90">
                    <span className="font-medium">Capability delta. </span>{d.capability_delta}
                  </p>
                )}
                {d.so_what && (
                  <p className="mt-1 text-sm text-slate-300"><span className="font-medium text-slate-200">So what. </span>{d.so_what}</p>
                )}
                {d.effect_timing_basis && (
                  <p className="mt-1 text-[11px] text-slate-500">Timing basis: {d.effect_timing_basis}</p>
                )}
                {(d.indicators_to_watch ?? []).length > 0 && (
                  <p className="mt-1 text-[11px] text-slate-500">Indicators: {d.indicators_to_watch!.join(" · ")}</p>
                )}
                {d.lineage_note && <p className="mt-1 text-[11px] italic text-slate-500">Sourcing: {d.lineage_note}</p>}
                {d.auto_adjustment && <p className="mt-1 text-[11px] text-amber-300/80">system adjustment: {d.auto_adjustment}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---------- MATURITY MATRIX ---------- */}
      {payload.maturity_matrix && Object.keys(payload.maturity_matrix).length > 0 && (
        <section className="print-card mb-8 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/40 p-4 print:border-slate-300">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
            Capability domain × programme maturity
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            What is intent and what will become actual military capability.
          </p>
          <table className="mt-2 w-full border-collapse text-[11px]">
            <thead>
              <tr>
                <th className="border border-slate-800 p-1.5 text-left text-slate-400">Domain</th>
                {MATURITY_ORDER.map((m) => (
                  <th key={m} className="border border-slate-800 p-1.5 text-left text-slate-400">{m}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(payload.maturity_matrix).map(([dom, cells]) => (
                <tr key={dom}>
                  <td className="border border-slate-800 p-1.5 font-medium text-slate-300">
                    {DOMAIN_LABELS[dom] ?? dom}
                  </td>
                  {MATURITY_ORDER.map((m) => (
                    <td key={m} className="border border-slate-800 p-1.5 align-top text-slate-400">
                      {(cells[m] ?? []).join(" · ")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ---------- ORBAT DELTA ---------- */}
      {(payload.orbat_delta?.length ?? 0) > 0 && (
        <section className="mb-8">
          <h2 className="mb-1 text-sm font-semibold text-slate-200">ORBAT delta — affected fleets</h2>
          <p className="mb-2 text-[11px] text-slate-500">
            Fleet baseline from the catalogue (approximate, open sources) against this period&apos;s activity.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {payload.orbat_delta!.map((c, i) => (
              <div key={i} className="print-card rounded-lg border border-slate-800 bg-slate-900/40 p-3 print:border-slate-300">
                <p className="text-sm font-medium text-slate-200">
                  {c.country} <span className="text-[11px] font-normal text-slate-500">{c.region}</span>
                </p>
                <table className="mt-1.5 w-full border-collapse text-[11px]">
                  <thead>
                    <tr className="text-slate-500">
                      <th className="p-1 text-left">Type</th>
                      <th className="p-1 text-right">Active</th>
                      <th className="p-1 text-right">On order</th>
                      <th className="p-1 text-left">This period</th>
                      <th className="p-1 text-left">Effect</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(c.entries ?? []).map((e, k) => (
                      <tr key={k} className="border-t border-slate-800/70 text-slate-300">
                        <td className="p-1">{e.type}</td>
                        <td className="p-1 text-right">{e.active ?? 0}</td>
                        <td className="p-1 text-right">{e.on_order ?? 0}</td>
                        <td className="p-1 text-slate-400">
                          {STAGE_LABELS[e.this_week_stage ?? ""] ?? e.this_week_stage}
                          {e.this_week_quantity ? ` ×${e.this_week_quantity}` : ""}
                        </td>
                        <td className="p-1 text-slate-500">
                          {e.expected_ioc_year ? `IOC ${e.expected_ioc_year}` : (e.delivery_window ?? "—")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---------- CAPABILITY ARRIVAL TIMELINE ---------- */}
      {(payload.capability_timeline?.length ?? 0) > 0 && (
        <section className="print-card mb-8 rounded-lg border border-slate-800 bg-slate-900/40 p-4 print:border-slate-300">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-300">
            Capability arrival timeline
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            When procurement becomes usable capability. A contract signed today with IOC beyond
            three years has near-term operational effect of zero.
          </p>
          <div className="mt-2 space-y-1.5">
            {Object.entries(
              payload.capability_timeline!.reduce((acc, t) => {
                const y = String(t.year ?? "?");
                (acc[y] = acc[y] ?? []).push(t);
                return acc;
              }, {} as Record<string, NonNullable<ReportPayload["capability_timeline"]>>)
            ).map(([year, items]) => (
              <div key={year} className="flex gap-3 text-xs">
                <span className="w-12 shrink-0 font-semibold text-slate-300">{year}</span>
                <span className="text-slate-400">
                  {items.map((t, i) => (
                    <span key={i}>
                      {i > 0 ? " · " : ""}{t.country} {t.type}
                      {t.quantity ? ` ×${t.quantity}` : ""}
                      <span className="text-slate-600"> ({t.basis})</span>
                    </span>
                  ))}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---------- PRIORITY WATCH ---------- */}
      {(payload.priority_watch?.length ?? 0) > 0 && (
        <section className="print-card mb-8 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 print:border-slate-300">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-amber-300">
            Priority intelligence watch
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Maximum five, ranked by impact. Everything else is in the annex.
          </p>
          <div className="mt-2 space-y-2">
            {payload.priority_watch!.map((w, i) => (
              <div key={i} className="rounded border border-slate-800 bg-slate-900/40 p-2 text-sm">
                <p className="font-medium text-slate-200">
                  {w.issue}
                  <span className="ml-1 text-[11px] font-normal text-slate-500">
                    ({w.horizon ?? "—"} · impact {w.impact_if_confirmed ?? "—"})
                  </span>
                </p>
                {w.why_it_matters && <p className="text-xs text-slate-400">Why: {w.why_it_matters}</p>}
                {w.next_observable && (
                  <p className="text-xs text-slate-300">Next observable: {w.next_observable}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---------- SELF-CHECKS ---------- */}
      {(payload.self_checks?.length ?? 0) > 0 && (
        <section className="print-card mb-8 rounded-lg border border-amber-600/30 bg-amber-500/5 p-3 print:border-slate-300">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-amber-300">Automated analytical QA</h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Where a check fires, treat the related wording as weaker than it reads.
          </p>
          <ul className="mt-1.5 space-y-0.5 text-xs text-slate-400">
            {payload.self_checks!.map((c, i) => (
              <li key={i}><span className="font-medium text-amber-200">{c.check}</span> — {c.item}</li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- EVIDENCE ANNEX ---------- */}
      {((payload.annex_events?.length ?? 0) > 0 || (payload.key_deals?.length ?? 0) > 0) && (
        <>
          <div className="mb-6 mt-2 border-t-2 border-slate-700 pt-4">
            <h2 className="text-center text-sm font-bold uppercase tracking-[0.2em] text-slate-400">
              Evidence annex — procurement event feed
            </h2>
            <p className="mt-1 text-center text-[11px] text-slate-600">
              Supporting data layer. The assessment above is the decision product.
            </p>
          </div>

          {(s.by_region || payload.by_region) && (
            <div className="mb-6 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
              {s.by_region
                ? Object.entries(s.by_region).sort((a, b) => b[1] - a[1])
                    .map(([r, n]) => <span key={r}>{r} <span className="text-slate-600">{n}</span></span>)
                : payload.by_region!.map((r) => (
                    <span key={r.region}>{r.region} <span className="text-slate-600">{r.count}</span></span>
                  ))}
            </div>
          )}

          <div className="space-y-2">
            {(payload.annex_events ?? payload.key_deals ?? []).map((e) => (
              <div key={e.event_id} className="rounded border border-slate-800 bg-slate-900/30 p-2.5 text-sm">
                <div className="flex flex-wrap items-center gap-1.5">
                  <EventBadge type={e.event_type} />
                  {e.lifecycle_stage && <Chip>{STAGE_LABELS[e.lifecycle_stage] ?? e.lifecycle_stage}</Chip>}
                  <span className="font-medium text-slate-200">
                    {e.country} · {e.aircraft}
                    {e.quantity ? ` ×${e.quantity}` : ""}
                  </span>
                  {e.value_usd_m != null && (
                    <Chip>${e.value_usd_m.toLocaleString()}M{e.value_type ? ` (${e.value_type})` : ""}</Chip>
                  )}
                  {e.event_date && <span className="text-[11px] text-slate-600">{e.event_date}</span>}
                  {e.undated && <Chip cls="border-amber-600/40 text-amber-300">no event date</Chip>}
                  {e.pending && <Chip cls="border-slate-600 text-slate-400">pending review</Chip>}
                </div>
                <p className="mt-1 text-slate-400">{e.summary}</p>
                {e.analyst_comment && <p className="mt-1 text-xs text-cyan-200/80">{e.analyst_comment}</p>}
                {e.article_url && (
                  <Link href={e.article_url} target="_blank" rel="noopener noreferrer"
                        className="mt-1 inline-block text-[11px] text-slate-500 underline hover:text-slate-300">
                    {e.article_title ?? "source"}
                  </Link>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ---------- v1 fallback: type slices + watchlist ---------- */}
      {!isV2 && (payload.by_type?.length ?? 0) > 0 && (
        <section className="mt-8 space-y-3">
          {payload.by_type!.map((t) => (
            <div key={t.event_type} className="rounded border border-slate-800 bg-slate-900/30 p-3">
              <p className="text-sm font-medium text-slate-200">
                <EventBadge type={t.event_type} /> <span className="ml-1">{t.count} events</span>
              </p>
              {t.note && <p className="mt-1 text-sm text-slate-400">{t.note}</p>}
            </div>
          ))}
          {(payload.watchlist?.items?.length ?? 0) > 0 && (
            <div className="print-card mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 print:border-slate-300">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-300">Analyst assessment</h3>
              {payload.watchlist!.assessment?.near_term && (
                <p className="mt-2 text-sm text-slate-300">
                  <span className="font-medium text-slate-200">Near term: </span>
                  {payload.watchlist!.assessment.near_term}
                </p>
              )}
              {payload.watchlist!.assessment?.long_term && (
                <p className="mt-2 text-sm text-slate-300">
                  <span className="font-medium text-slate-200">Long term: </span>
                  {payload.watchlist!.assessment.long_term}
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
