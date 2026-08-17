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
    // --- v3: a WoW a PUBLIKALT elozo ertekbol szamol ---
    events_prev_week_published?: number | null;
    events_prev_week_recomputed?: number | null;
    wow?: number | null;
    wow_basis?: string | null;
    wow_drift?: { published: number; recomputed: number; note: string } | null;
    firm_actions_labelled?: number;
    firm_actions_note?: string;
    baseline_movement?: {
      events_moving_baseline?: number; total_on_order_delta?: number;
      note?: string;
    };
    programme_layer?: {
      programmes_touched?: number; programmes_proposed?: number;
      events_unlinked?: number; duplicate_pairs_flagged?: number;
    };
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
      new_confirmations_of_older_events?: number;
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
    country?: string; region?: string; baseline_scope?: string;
    entries?: {
      type?: string; domain?: string; active?: number | null;
      on_order?: number | null; stored?: number | null;
      // v2 nevek (visszafele kompatibilitas)
      this_week_stage?: string; this_week_quantity?: number | null;
      // --- v3: hatokor, programme-allapot, explicit heti szemantika ---
      variant_reported?: string | null; service?: string | null;
      baseline_scope_match?: "exact" | "variant_without_baseline" | "family" | "missing";
      baseline_shown?: boolean; baseline_note?: string | null;
      family_total_active?: number | null;
      programme_id?: string | null; programme_title?: string | null;
      programme_kind?: string | null;
      canonical_quantity?: number | null; quantity_basis?: string | null;
      this_period_stage?: string; this_period_stage_note?: string | null;
      this_period_quantity_claimed?: number | null;
      on_order_delta?: number; baseline_moved?: boolean;
      period_reading?: string; evidence_kinds?: string[];
      expected_ioc_year?: number | null; delivery_window?: string | null;
      baseline_missing?: boolean; baseline_anomaly?: boolean;
    }[];
  }[];
  capability_timeline?: {
    year?: number; basis?: string; label?: string; country?: string;
    type?: string; domain?: string; quantity?: number | null; stage?: string;
    is_withdrawal?: boolean;
    // --- v3: egy sor = egy programme + egy milestone ---
    year_label?: string;
    year_precision?: "year" | "mid" | "quarter" | "exact" | "unknown";
    milestone_kind?: string; milestone?: string;
    is_arrival?: boolean; programme?: string | null;
    arrival_kind?: "airframe" | "support" | "none";
    is_airframe_arrival?: boolean;
    confidence?: string | null; note?: string | null;
    source_layer?: string;
  }[];
  since_last_week?: {
    previous_week?: string | null; note?: string;
    programmes?: {
      programme?: string; programme_id?: string | null;
      previous?: string; current?: string; change?: string; moved?: boolean;
    }[];
    watch?: {
      issue?: string; state?: string; state_label?: string;
      next_observable?: string | null;
    }[];
  };
  briefing?: BriefingPayload;
  programme_state?: ProgrammeState[];
  programme_review?: {
    proposed?: { programme_id?: string; kind?: string; title?: string;
                 events?: number[] }[];
    duplicate_pairs?: {
      a?: string; b?: string; country_id?: string; type_id?: string;
      a_quantity?: number | null; b_quantity?: number | null;
      a_stage?: string | null; b_stage?: string | null; reason?: string;
    }[];
    unlinked_events?: { event_id?: number; reason?: string }[];
  };
  maturity_matrix?: Record<string, Record<string, string[]>>;
  capability_withdrawal?: {
    domain?: string; label?: string; stage?: string;
    effect_timing?: string; note?: string;
  }[];
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
  supporting_event_ids?: number[];
}

interface Development {
  title?: string; display_label?: string; capability_domain?: string;
  lifecycle_stage?: string; fact?: string; capability_delta?: string;
  effect_timing?: string; effect_timing_basis?: string; so_what?: string;
  novelty?: string; significance?: number; confidence?: string;
  reports_count?: number; independent_lineages?: number; lineage_note?: string;
  value_usd_m?: number | null; value_type?: string;
  expected_ioc_year?: number | null; first_delivery_year?: number | null;
  ioc_year?: number | null; meaningful_capability_year?: number | null;
  indicators_to_watch?: string[];
  auto_adjustment?: string;
  event_ids?: number[];
  // --- v3 ---
  full_capability_timing?: string | null;
  full_capability_year?: number | null;
  effect_timing_months?: number | null;
  effect_horizon_basis?: string | null;
  lineage_basis?: string | null;
  programme_id?: string | null; programme_kind?: string | null;
  programme_canonical_quantity?: number | null;
  programme_delta?: number; baseline_moved?: boolean;
  evidence_kinds?: string[]; is_new_confirmation?: boolean;
  occurred_year?: number | null;
  milestone_kind?: string | null;
}

export interface ProgrammeState {
  programme_id?: string; title?: string; kind?: string; kind_label?: string;
  variant?: string | null; service?: string | null;
  canonical_quantity?: number | null; quantity_basis?: string | null;
  lifecycle_stage?: string | null; contract_date?: string | null;
  first_delivery_year?: number | null; ioc_year?: number | null;
  foc_year?: number | null; meaningful_scale_year?: number | null;
  confidence?: string | null; independent_lineages?: number;
  first_reported_at?: string | null; last_evidence_at?: string | null;
  evidence_count?: number; supersessions?: number;
  no_airframe_arrival?: boolean;
  this_period?: {
    events?: number; on_order_delta?: number;
    quantity_claimed_max?: number | null; evidence_kinds?: string[];
    reading?: string;
  };
}

export interface BriefingPayload {
  week_label?: string;
  speaking_time_estimate_min?: number;
  note?: string;
  slides?: {
    n?: number; title?: string;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    body?: any;
  }[];
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
  // --- v3 ---
  lifecycle_stage_reported?: string | null;
  stage_correction_note?: string | null;
  programme_id?: string | null;
  variant_reported?: string | null; type_match_kind?: string | null;
  quantity_claimed?: number | null;
  on_order_delta?: number; on_order_delta_reason?: string | null;
  evidence_kind?: string; occurred_year?: number | null;
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
  const isV2 = payload.schema === "air_power_v2" || payload.schema === "air_power_v3"
    || (payload.developments?.length ?? 0) > 0;
  const prevAvg = s.events_prev_4wk_weekly_avg ?? s.events_prev_4wk_avg;
  const val = s.value?.by_value_type ?? {};
  const domains = s.airframes_by_domain ?? {};

  /* ---------------------------------------------------------------------
   * WEEK-OVER-WEEK — a v3 a PUBLIKALT elozo ertekhez mer.
   *
   * A W33 "18 in-period events"-et irt ki, a W34 "22 in-period events
   * (+0 WoW)"-t. Ket egymast koveto het ugyanazon metrikaja +4, nem +0.
   * Az ok: a W34 az elozo hetet UJRASZAMOLTA a sajat, kesobbi
   * adatallapotabol, es azt hasonlitotta magahoz.
   *
   * Most harom eset van, es mindharom LATHATO:
   *   1. van publikalt elozo ertek  -> WoW abbol, a drift kiirva
   *   2. nincs elozo jelentes       -> "WoW: first period"
   *   3. metodika valtozott         -> "WoW: not comparable"
   * ------------------------------------------------------------------- */
  const wowValue = s.wow ?? (s.events_prev_week != null
    ? s.events_this_week - s.events_prev_week : null);
  const wowLabel = (() => {
    if (s.volume_not_comparable) return "WoW: not comparable";
    if (s.wow_basis && s.wow == null) return `WoW: ${s.wow_basis}`;
    if (wowValue == null) return "WoW: no prior published report";
    return `${wowValue >= 0 ? "+" : ""}${wowValue} WoW`;
  })();

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
              in-period events ({wowLabel}
              {prevAvg != null ? ` · 4-wk wkly avg ${prevAvg}` : ""})
            </p>
            {s.collection_health && (
              <p className="text-[10px] text-slate-600">
                {(s.collection_health.future_dated_excluded ?? 0) > 0
                  ? `${s.collection_health.future_dated_excluded} future-dated excluded · ` : ""}
                {(s.collection_health.new_confirmations_of_older_events ?? 0) > 0
                  ? `${s.collection_health.new_confirmations_of_older_events} confirmation(s) of older events · ` : ""}
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
              {s.firm_actions_labelled != null
                && s.firm_actions_labelled !== (s.firm_procurement_actions ?? -1) && (
                <span className="text-xs font-normal text-amber-300/80">
                  {" "}/ {s.firm_actions_labelled} labelled
                </span>
              )}
            </p>
            <p className="text-xs text-slate-500">firm procurement actions</p>
            {s.firm_actions_note && (
              <p className="text-[10px] text-slate-600">
                contract evidence required, not just the label
              </p>
            )}
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

        {/* ---------- WoW-DRIFT: az ujraszamolt elozo het != a publikalt ----
            A W33/W34 kozotti "+0" pontosan ebbol keletkezett. A driftet nem
            elhallgatjuk, hanem kiirjuk, mert kulonben az osszehasonlithatosag
            latszatat tartjuk fenn. */}
        {s.wow_drift && (
          <div className="mt-3 rounded border border-amber-600/40 bg-amber-500/5 p-2">
            <p className="text-[11px] font-medium text-amber-300">
              Week-over-week baseline drift
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400">
              Previous period: <span className="text-slate-200">{s.wow_drift.published} published</span>
              {" · "}<span className="text-slate-300">{s.wow_drift.recomputed} on recomputation</span>.
              {" "}{s.wow_drift.note}
            </p>
          </div>
        )}

        {/* ---------- BASELINE-MOZGAS: a lengyel Apache-hiba ellenszere ----
            Ha a heti riportolas csak megismetli egy meglevo programot, a
            baseline NEM mozdul — es ezt kimondjuk, mert kulonben az olvaso
            osszeadja a "on order 190" es a "this period x94" szamokat. */}
        {s.baseline_movement && (
          <div className="mt-2 rounded border border-slate-800 bg-slate-900/40 p-2">
            <p className="text-[11px] font-medium text-slate-400">
              Baseline movement:{" "}
              <span className={(s.baseline_movement.events_moving_baseline ?? 0) > 0
                ? "text-cyan-200" : "text-slate-300"}>
                {(s.baseline_movement.events_moving_baseline ?? 0) === 0
                  ? "none this period"
                  : `${s.baseline_movement.events_moving_baseline} event(s), ${
                      (s.baseline_movement.total_on_order_delta ?? 0) >= 0 ? "+" : ""
                    }${s.baseline_movement.total_on_order_delta} on order`}
              </span>
            </p>
            {s.baseline_movement.note && (
              <p className="mt-0.5 text-[10px] text-slate-600">{s.baseline_movement.note}</p>
            )}
          </div>
        )}

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

      {/* ---------- 1. COMMAND BRIEF ---------- */}
      {(payload.key_judgements?.length ?? 0) > 0 && (
        <p className="mb-2 text-center text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
          Command brief
        </p>
      )}

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

      {/* ---------- SINCE LAST WEEK ----------------------------------------
          A W33 es a W34 egyarant jo heti PILLANATFELVETEL, de gyenge
          LONGITUDINALIS TRACKER: egyik sem mondta meg, mi valtozott az elozo
          het ota. Ez a blokk szandekosan 4-6 sor — ez teszi heti hirszerzo
          termékké, nem ujabb harom oldal. */}
      {((payload.since_last_week?.programmes?.length ?? 0) > 0
        || (payload.since_last_week?.watch?.length ?? 0) > 0) && (
        <section className="print-card mb-8 rounded-xl border border-cyan-500/25 bg-cyan-500/5 p-4 print:border-slate-300">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-cyan-300">Since last week</h2>
            {payload.since_last_week?.previous_week && (
              <span className="text-[11px] text-slate-500">
                against {payload.since_last_week.previous_week}
              </span>
            )}
          </div>

          {(payload.since_last_week?.programmes?.length ?? 0) > 0 && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full border-collapse text-[11px]">
                <thead>
                  <tr className="text-slate-500">
                    <th className="p-1 text-left">Programme</th>
                    <th className="p-1 text-left">Previous</th>
                    <th className="p-1 text-left">This period</th>
                    <th className="p-1 text-left">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.since_last_week!.programmes!.map((r, i) => (
                    <tr key={i} className="border-t border-slate-800/70">
                      <td className="p-1 font-medium text-slate-300">{r.programme}</td>
                      <td className="p-1 text-slate-500">{r.previous}</td>
                      <td className="p-1 text-slate-400">{r.current}</td>
                      <td className={`p-1 ${r.moved ? "text-cyan-200" : "text-slate-600"}`}>
                        {r.change}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(payload.since_last_week?.watch?.length ?? 0) > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-medium text-slate-400">
                Previous watch items
              </p>
              <ul className="mt-1 space-y-0.5 text-[11px]">
                {payload.since_last_week!.watch!.map((w, i) => (
                  <li key={i} className="text-slate-400">
                    <span className={
                      w.state === "escalated" ? "text-rose-300"
                        : w.state === "resolved" ? "text-emerald-300"
                        : w.state === "new" ? "text-cyan-300"
                        : w.state === "dropped" ? "text-slate-600"
                        : "text-slate-500"}>
                      [{w.state}]
                    </span>{" "}
                    {w.issue}
                    {w.next_observable && (
                      <span className="text-slate-600"> — next: {w.next_observable}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {payload.since_last_week?.note && (
            <p className="mt-2 text-[10px] text-slate-600">{payload.since_last_week.note}</p>
          )}
        </section>
      )}

      {/* ---------- 2. ANALYST LAYER ---------- */}
      {(payload.developments?.length ?? 0) > 0 && (
        <div className="mb-4 border-t border-slate-800 pt-3">
          <p className="text-center text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
            Analyst layer
          </p>
        </div>
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

                {/* EVIDENCIA-JELLEG: egy 2025-os veszteseg 2026-os vizualis
                    igazolasa NEM e heti esemeny. A W34-ben az A-100LL igy
                    keltette azt a benyomast, hogy a veszteseg most tortent. */}
                {d.is_new_confirmation && (
                  <p className="mt-1 text-[11px] font-medium text-amber-300">
                    New confirmation this period
                    {d.occurred_year ? ` — the event itself occurred in ${d.occurred_year}` : ""}
                  </p>
                )}

                <div className="mt-1 flex flex-wrap gap-1.5">
                  <Chip>{DOMAIN_LABELS[d.capability_domain ?? ""] ?? d.capability_domain}</Chip>
                  <Chip>{STAGE_LABELS[d.lifecycle_stage ?? ""] ?? d.lifecycle_stage}</Chip>

                  {/* KETTOS HORIZONT. A VC-25B (elso atadas 2028 kozepe, IOC
                      2028, hasznalhato 2029) korabban egyetlen ">3 years"
                      cimket kapott. A ket horizont KULON olvasat. */}
                  <Chip cls={TIMING_STYLE[d.effect_timing ?? "unknown"] ?? ""}>
                    earliest effect: {d.effect_timing ?? "unknown"}
                  </Chip>
                  {d.full_capability_timing && d.full_capability_timing !== d.effect_timing && (
                    <Chip cls={TIMING_STYLE[d.full_capability_timing] ?? ""}>
                      meaningful scale: {d.full_capability_timing}
                    </Chip>
                  )}

                  {(d.first_delivery_year || d.ioc_year || d.expected_ioc_year ||
                    d.meaningful_capability_year || d.full_capability_year) && (
                    <Chip>
                      {[d.first_delivery_year ? `1st delivery ${d.first_delivery_year}` : null,
                        (d.ioc_year ?? d.expected_ioc_year) ? `IOC ${d.ioc_year ?? d.expected_ioc_year}` : null,
                        (d.meaningful_capability_year ?? d.full_capability_year)
                          ? `usable ${d.meaningful_capability_year ?? d.full_capability_year}` : null,
                      ].filter(Boolean).join(" · ")}
                    </Chip>
                  )}
                  <Chip>sig {d.significance}/5 · conf {d.confidence}</Chip>
                  <Chip>
                    {d.reports_count ?? 1} report{(d.reports_count ?? 1) === 1 ? "" : "s"} ·{" "}
                    {d.independent_lineages ?? 1} lineage{(d.independent_lineages ?? 1) === 1 ? "" : "s"}
                  </Chip>
                  {d.value_usd_m != null && (
                    <Chip>${d.value_usd_m.toLocaleString()}M · {d.value_type ?? "unknown"}</Chip>
                  )}

                  {/* BASELINE-MOZGAS. A nulla is informacio: ez mondja meg,
                      hogy egy ujabb cikk nem uj repulogep. */}
                  {d.programme_delta != null && (
                    <Chip cls={d.baseline_moved
                      ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-200"
                      : "border-slate-700 bg-slate-800/60 text-slate-500"}>
                      {d.baseline_moved
                        ? `baseline ${d.programme_delta >= 0 ? "+" : ""}${d.programme_delta}`
                        : "baseline unchanged"}
                      {d.programme_canonical_quantity != null
                        ? ` · programme of record ${d.programme_canonical_quantity}` : ""}
                    </Chip>
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
                  <p className="mt-1 text-[11px] text-slate-500">
                    Timing basis: {d.effect_timing_basis}
                    {d.effect_horizon_basis ? ` (horizon from: ${d.effect_horizon_basis}` : ""}
                    {d.effect_horizon_basis && d.effect_timing_months != null
                      ? `, ${d.effect_timing_months} months)` : d.effect_horizon_basis ? ")" : ""}
                  </p>
                )}
                {(d.indicators_to_watch ?? []).length > 0 && (
                  <p className="mt-1 text-[11px] text-slate-500">Indicators: {d.indicators_to_watch!.join(" · ")}</p>
                )}
                {/* A lineage-alap DETERMINISZTIKUS szamitasbol. A W33 "2
                    lineage" allitasa ket olyan eventre epult, amelyek
                    ugyanabbol a cikkbol szarmaztak. */}
                {(d.lineage_basis || d.lineage_note) && (
                  <p className="mt-1 text-[11px] italic text-slate-500">
                    Sourcing: {d.lineage_basis ?? d.lineage_note}
                  </p>
                )}
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

      {/* ---------- CAPABILITY WITHDRAWAL (kulon ontologia) ---------- */}
      {(payload.capability_withdrawal?.length ?? 0) > 0 && (
        <section className="print-card mb-8 rounded-lg border border-rose-500/25 bg-rose-500/5 p-4 print:border-slate-300">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-rose-300">
            Capability transition / withdrawal
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            Retirements run parallel to the introduction lifecycle above, not inside it —
            an out-of-service milestone is not a maturity stage.
          </p>
          <ul className="mt-2 space-y-1 text-xs text-slate-300">
            {payload.capability_withdrawal!.map((w, i) => (
              <li key={i}>
                <span className="font-medium">{w.label}</span>
                <span className="text-slate-500"> · {DOMAIN_LABELS[w.domain ?? ""] ?? w.domain}</span>
                {w.effect_timing ? <span className="text-slate-500"> · effect {w.effect_timing}</span> : null}
                {w.note ? <span className="text-slate-400"> — {w.note}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------- ORBAT DELTA ---------- */}
      {(payload.orbat_delta?.length ?? 0) > 0 && (
        <section className="mb-8">
          <h2 className="mb-1 text-sm font-semibold text-slate-200">ORBAT delta — affected fleets</h2>
          <p className="mb-2 text-[11px] text-slate-500">
            Baseline keyed on <span className="text-slate-400">country + type + variant + service</span>.
            A family-wide total is never substituted for a variant-level action: where no
            variant-level baseline exists, the figure is withheld rather than approximated.
            &quot;Programme of record&quot; is the canonical programme quantity — the period
            column is <span className="text-slate-400">not additive to it</span>.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {payload.orbat_delta!.map((c, i) => (
              <div key={i} className="print-card rounded-lg border border-slate-800 bg-slate-900/40 p-3 print:border-slate-300">
                <p className="text-sm font-medium text-slate-200">
                  {c.country} <span className="text-[11px] font-normal text-slate-500">{c.region}</span>
                </p>
                {c.baseline_scope && (
                  <p className="text-[10px] text-slate-600">Scope: {c.baseline_scope}</p>
                )}
                <table className="mt-1.5 w-full border-collapse text-[11px]">
                  <thead>
                    <tr className="text-slate-500">
                      <th className="p-1 text-left">Type / variant</th>
                      <th className="p-1 text-right">Active</th>
                      <th className="p-1 text-right">On order</th>
                      <th className="p-1 text-right">Prog. of record</th>
                      <th className="p-1 text-left">This period</th>
                      <th className="p-1 text-left">Effect</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(c.entries ?? []).map((e, k) => {
                      /* A HATOKOR-ELTERES kezelese. Ha az esemeny
                       * varians-szintu, de csak csalad-szintu baseline van,
                       * a szamot NEM helyettesitjuk: ez adta a "USAF 26
                       * HH-60W" melle a "UH-60 Active 2000"-et, es a "brit
                       * AH-64E 50 gep" melle a "AH-64 Active 100"-at. */
                      const scope = e.baseline_scope_match;
                      const withheld = scope === "variant_without_baseline";
                      const missing = scope === "missing" || e.baseline_missing;
                      const cell = (v: number | null | undefined) => {
                        if (withheld) return (
                          <span className="text-amber-300/80" title={e.baseline_note ?? undefined}>
                            scope
                          </span>
                        );
                        if (missing) return (
                          <span className="text-amber-300/80" title="No catalogue baseline — missing data, not zero aircraft">
                            n/d
                          </span>
                        );
                        return v ?? 0;
                      };
                      const stage = e.this_period_stage ?? e.this_week_stage;
                      const qty = e.this_period_quantity_claimed ?? e.this_week_quantity;
                      return (
                        <tr key={k} className="border-t border-slate-800/70 text-slate-300 align-top">
                          <td className="p-1">
                            {e.type}
                            {e.variant_reported && e.variant_reported !== e.type && (
                              <span className="block text-[10px] text-cyan-200/70">
                                reported as {e.variant_reported}
                              </span>
                            )}
                            {e.service && (
                              <span className="block text-[10px] text-slate-500">{e.service}</span>
                            )}
                          </td>
                          <td className="p-1 text-right">{cell(e.active)}</td>
                          <td className="p-1 text-right">{cell(e.on_order)}</td>
                          <td className="p-1 text-right">
                            {e.canonical_quantity != null ? (
                              <span title={e.quantity_basis ? `basis: ${e.quantity_basis}` : undefined}>
                                {e.canonical_quantity}
                              </span>
                            ) : <span className="text-slate-600">—</span>}
                          </td>
                          <td className="p-1 text-slate-400">
                            {STAGE_LABELS[stage ?? ""] ?? stage}
                            {qty ? ` ×${qty}` : ""}
                            {/* A HETI OLVASAT KIMONDVA. Enelkul az olvaso
                                osszeadja a programme-szamot es a heti szamot. */}
                            {e.period_reading && (
                              <span className={`block text-[10px] ${
                                e.baseline_moved ? "text-cyan-200/80" : "text-slate-600"}`}>
                                {e.baseline_moved
                                  ? `baseline ${(e.on_order_delta ?? 0) >= 0 ? "+" : ""}${e.on_order_delta}`
                                  : "claim only — baseline unchanged"}
                              </span>
                            )}
                            {/* STADIUM-VISSZAMINOSITES lathatoan. Az uzbeg
                                "Contract signed ×24" itt mar nem all elo. */}
                            {e.this_period_stage_note && (
                              <span className="block text-[10px] text-amber-300/80">
                                downgraded: {e.this_period_stage_note}
                              </span>
                            )}
                          </td>
                          <td className="p-1 text-slate-500">
                            {e.expected_ioc_year ? `IOC ${e.expected_ioc_year}` : (e.delivery_window ?? "—")}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>

                {/* A visszatartott baseline-ok indoklasa a tabla alatt, egyszer. */}
                {(c.entries ?? []).some((e) => e.baseline_note) && (
                  <ul className="mt-1 space-y-0.5 text-[10px] text-slate-600">
                    {(c.entries ?? []).filter((e) => e.baseline_note).map((e, k) => (
                      <li key={k}>
                        <span className="text-slate-500">{e.variant_reported ?? e.type}:</span>{" "}
                        {e.baseline_note}
                      </li>
                    ))}
                  </ul>
                )}
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
            <span className="text-slate-400">One row = one programme + one milestone.</span>{" "}
            Earlier editions merged unrelated programmes into a shared year line with a single
            basis, which read as though a signed delivery and a sole-source notice were the same
            kind of event. A schedule slip is shown separately — a delay is not an arrival, and a
            support-facility milestone is not an aircraft delivery.
          </p>
          <div className="mt-2 space-y-2">
            {(() => {
              /* A datalt es a TBD sorok kulon csoportba. Egy tamogato
               * program hitelesitesi datuma gyakran nem ismert — az ilyen sor
               * TBD-kent all a lista vegen, es SOHA nem veszi at a beszerzesi
               * program gepatadasi evet. Pontosan ez volt a W34 hibaja:
               * "2028 Poland AH-64E MRO deal (first delivery)". */
              const groups = payload.capability_timeline!.reduce((acc, t) => {
                const key = t.year_label ?? String(t.year ?? "TBD");
                (acc[key] = acc[key] ?? []).push(t);
                return acc;
              }, {} as Record<string, NonNullable<ReportPayload["capability_timeline"]>>);
              const keys = Object.keys(groups).sort((a, b) => {
                if (a === "TBD") return 1;
                if (b === "TBD") return -1;
                return a.localeCompare(b);
              });
              return keys.map((year) => {
                const items = groups[year];
                return (
                  <div key={year} className="flex gap-3 text-xs">
                    <span className={`w-14 shrink-0 pt-0.5 font-semibold ${
                      year === "TBD" ? "text-slate-600" : "text-slate-300"}`}>
                      {year}
                      {items[0]?.year_precision === "mid" && (
                        <span className="block text-[9px] font-normal text-slate-600">mid</span>
                      )}
                      {items[0]?.year_precision === "quarter" && (
                        <span className="block text-[9px] font-normal text-slate-600">qtr</span>
                      )}
                    </span>
                    {/* KULON SOR minden milestone-nak. Nincs " · " osszefuzés. */}
                    <ul className="flex-1 space-y-1">
                      {items.map((t, i) => (
                        <li key={i} className="flex flex-wrap items-baseline gap-x-1.5">
                          <span className={
                            t.is_withdrawal ? "text-rose-200/80"
                              : t.milestone_kind === "schedule_slip" ? "text-amber-200/80"
                              : t.arrival_kind === "support" ? "text-violet-200/80"
                              : t.is_arrival === false ? "text-slate-500"
                              : "text-slate-300"}>
                            {t.programme ?? t.label ?? `${t.country ?? ""} ${t.type ?? ""}`.trim()}
                          </span>
                          {t.quantity ? (
                            <span className="text-slate-400">×{t.quantity}</span>
                          ) : null}
                          <span className={`text-[10px] ${
                            t.milestone_kind === "schedule_slip"
                              ? "text-amber-300/80" : "text-slate-600"}`}>
                            — {t.milestone ?? t.basis}
                          </span>
                          {t.confidence && (
                            <span className="text-[10px] text-slate-600">({t.confidence})</span>
                          )}
                          {t.note && (
                            <span className="block w-full text-[10px] italic text-slate-600">
                              {t.note}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              });
            })()}
          </div>
          <p className="mt-2 text-[10px] text-slate-600">
            Amber = schedule slip (not an arrival) · violet = support/infrastructure milestone
            (no airframe delivery) · rose = withdrawal or loss.{" "}
            {payload.capability_timeline!.some((t) => !t.year) && (
              <>A support programme with no published operational date is shown as{" "}
              <span className="text-slate-500">TBD</span> rather than borrowing the acquisition
              programme&apos;s delivery year.</>
            )}
          </p>
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

      {/* ---------- PROGRAMME REGISTER REVIEW ------------------------------
          A programme-reteg nem magat javitja ki: JELEZ. A duplikatum-gyanut
          embernek kell eldontenie, mert egy hibasan OSSZEVONT program ugyanolyan
          karos, mint egy hibasan szetvalasztott. A lengyel AH-64E 190/284/286
          esetben pontosan egy ilyen par all fenn. */}
      {((payload.programme_review?.duplicate_pairs?.length ?? 0) > 0
        || (payload.programme_review?.proposed?.length ?? 0) > 0
        || (payload.programme_review?.unlinked_events?.length ?? 0) > 0) && (
        <section className="print-card mb-8 rounded-lg border border-violet-500/25 bg-violet-500/5 p-3 print:border-slate-300">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-violet-300">
            Programme register — analyst review
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-500">
            The programme layer flags, it never merges on its own. A wrongly merged
            programme is as damaging as a wrongly split one.
          </p>

          {(payload.programme_review?.duplicate_pairs?.length ?? 0) > 0 && (
            <div className="mt-2">
              <p className="text-[11px] font-medium text-slate-400">
                Possible duplicate programmes ({payload.programme_review!.duplicate_pairs!.length})
              </p>
              <ul className="mt-1 space-y-1 text-[11px] text-slate-400">
                {payload.programme_review!.duplicate_pairs!.map((p, i) => (
                  <li key={i}>
                    <span className="text-slate-300">{p.a}</span>
                    {" ↔ "}
                    <span className="text-slate-300">{p.b}</span>
                    <span className="text-slate-600">
                      {" "}({p.a_quantity ?? "—"} vs {p.b_quantity ?? "—"} aircraft
                      {p.a_stage || p.b_stage ? `; ${p.a_stage ?? "—"} / ${p.b_stage ?? "—"}` : ""})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(payload.programme_review?.proposed?.length ?? 0) > 0 && (
            <div className="mt-2">
              <p className="text-[11px] font-medium text-slate-400">
                New programmes proposed this period ({payload.programme_review!.proposed!.length})
              </p>
              <ul className="mt-1 space-y-0.5 text-[11px] text-slate-500">
                {payload.programme_review!.proposed!.slice(0, 10).map((p, i) => (
                  <li key={i}>
                    <span className="text-slate-400">{p.programme_id}</span>
                    {p.kind ? <span className="text-slate-600"> [{p.kind}]</span> : null}
                    {p.title ? <span className="text-slate-500"> — {p.title}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(payload.programme_review?.unlinked_events?.length ?? 0) > 0 && (
            <p className="mt-2 text-[11px] text-slate-500">
              {payload.programme_review!.unlinked_events!.length} event(s) could not be attached to
              a programme (missing country or type resolution) — these are excluded from baseline
              movement rather than guessed.
            </p>
          )}
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
                  {e.lifecycle_stage && (
                    <Chip cls={e.stage_correction_note
                      ? "border-amber-600/40 bg-amber-500/10 text-amber-200" : ""}>
                      {STAGE_LABELS[e.lifecycle_stage] ?? e.lifecycle_stage}
                      {e.lifecycle_stage_reported
                        ? ` (was: ${STAGE_LABELS[e.lifecycle_stage_reported] ?? e.lifecycle_stage_reported})`
                        : ""}
                    </Chip>
                  )}
                  <span className="font-medium text-slate-200">
                    {e.country} · {e.aircraft}
                    {/* A forras tipusjele kulon. A kanonikus nev FK-rol jon —
                        nev alapjan itt sosem keresunk vissza, ez zarja le az
                        A-100LL -> A-10 hibat a megjelenitesi oldalon. */}
                    {e.variant_reported && e.variant_reported !== e.aircraft && (
                      <span className="ml-1 text-[11px] font-normal text-cyan-200/70">
                        (reported: {e.variant_reported})
                      </span>
                    )}
                    {e.quantity ? ` ×${e.quantity}` : ""}
                  </span>
                  {e.value_usd_m != null && (
                    <Chip>${e.value_usd_m.toLocaleString()}M{e.value_type ? ` (${e.value_type})` : ""}</Chip>
                  )}
                  {e.event_date && <span className="text-[11px] text-slate-600">{e.event_date}</span>}
                  {/* EVIDENCIA-JELLEG: a regi esemeny uj igazolasa nem e heti hir. */}
                  {e.evidence_kind && e.evidence_kind !== "new_event" && (
                    <Chip cls="border-amber-600/40 text-amber-300">
                      {e.evidence_kind.replace(/_/g, " ")}
                      {e.occurred_year ? ` · occurred ${e.occurred_year}` : ""}
                    </Chip>
                  )}
                  {e.type_match_kind === "none" && (
                    <Chip cls="border-rose-600/40 text-rose-300">type unresolved</Chip>
                  )}
                  {e.undated && <Chip cls="border-amber-600/40 text-amber-300">no event date</Chip>}
                  {e.pending && <Chip cls="border-slate-600 text-slate-400">pending review</Chip>}
                </div>
                <p className="mt-1 text-slate-400">{e.summary}</p>
                {/* Miert nem mozdult a baseline — a lengyel Apache-hiba
                    ellenszere az esemeny szintjen is lathato. */}
                {e.on_order_delta_reason && e.on_order_delta === 0 && (
                  <p className="mt-0.5 text-[10px] text-slate-600">
                    Baseline: {e.on_order_delta_reason}
                  </p>
                )}
                {(e.on_order_delta ?? 0) !== 0 && (
                  <p className="mt-0.5 text-[10px] text-cyan-200/70">
                    Baseline {(e.on_order_delta ?? 0) >= 0 ? "+" : ""}{e.on_order_delta}
                    {e.on_order_delta_reason ? ` — ${e.on_order_delta_reason}` : ""}
                  </p>
                )}
                {e.stage_correction_note && (
                  <p className="mt-0.5 text-[10px] text-amber-300/80">
                    Stage correction: {e.stage_correction_note}
                  </p>
                )}
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
