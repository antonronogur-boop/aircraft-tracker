import type { BriefingPayload } from "@/components/WeeklyReportView";

/* ------------------------------------------------------------------ *
 * BRIEFING VIEW — 4 slide egy 5-8 perces szobeli briefinghez
 *
 * A 13-14 oldalas jelentes marad a REFERENCE PRODUCT. Ez a nezet abbol
 * eloadhato terméket csinal, ES NEM AD HOZZA SEMMIT: kizarolag a QA-n
 * atment tartalombol epul, hogy a visszatartasi kapu ne legyen
 * megkerulhetó egy "osszefoglalo" nezeten keresztul.
 *
 *   1. This week in air power  — 1 bottom line + 3 legfontosabb valtozas
 *   2. What actually changed   — NOW | 1-3 YEARS | >3 YEARS
 *   3. Deep dive               — a het temaja negy kerdesre bontva
 *   4. Watch next              — watchok + az elozo hetiek allapota
 *
 * Nyomtatasban minden slide sajat lapra kerul (print:break-after-page),
 * igy a "4 slide" nem metafora: ki lehet nyomtatni beadonak.
 * ------------------------------------------------------------------ */

const DOMAIN_LABELS: Record<string, string> = {
  fighter_strike: "Fighter / strike", attack_helicopter: "Attack helicopter",
  air_mobility_rotary: "Air mobility — rotary",
  air_mobility_fixed: "Air mobility — fixed wing",
  uncrewed_cca: "Uncrewed / CCA", counter_uas: "Counter-UAS",
  isr_aew_sigint: "ISR / AEW&C / SIGINT", tanker: "Air-to-air refuelling",
  training: "Training / pilot pipeline", maritime_patrol: "Maritime patrol",
  other: "Other",
};

const TIMING_STYLE: Record<string, string> = {
  immediate: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  "<12 months": "border-amber-500/40 bg-amber-500/10 text-amber-200",
  "1-3 years": "border-sky-500/40 bg-sky-500/10 text-sky-200",
  ">3 years": "border-slate-600 bg-slate-800/60 text-slate-300",
  unknown: "border-slate-700 bg-slate-800/40 text-slate-400",
};

const WATCH_STYLE: Record<string, string> = {
  escalated: "text-rose-300", resolved: "text-emerald-300",
  new: "text-cyan-300", dropped: "text-slate-600", unchanged: "text-slate-500",
};

function Chip({ children, cls = "" }: { children: React.ReactNode; cls?: string }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[11px] ${
      cls || "border-slate-700 bg-slate-800/60 text-slate-300"}`}>
      {children}
    </span>
  );
}

function Slide({
  n, title, subtitle, children,
}: {
  n: number; title: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <section className="print-card mb-6 rounded-xl border border-slate-800 bg-slate-900/40 p-5 print:mb-0 print:break-after-page print:border-slate-300">
      <div className="mb-3 flex items-baseline gap-2 border-b border-slate-800 pb-2">
        <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-600">
          Slide {n}
        </span>
        <h2 className="text-base font-semibold text-slate-100">{title}</h2>
        {subtitle && <span className="text-[11px] text-slate-500">{subtitle}</span>}
      </div>
      {children}
    </section>
  );
}

export function BriefingView({
  briefing, weekLabel, periodStart, periodEnd,
}: {
  briefing: BriefingPayload;
  weekLabel: string; periodStart?: string; periodEnd?: string;
}) {
  const slides = briefing.slides ?? [];
  const body = (n: number) => slides.find((s) => s.n === n)?.body;
  const s1 = body(1); const s2 = body(2); const s3 = body(3); const s4 = body(4);

  return (
    <div className="report-body">
      <p className="mb-4 text-[11px] text-slate-500">
        {weekLabel}
        {periodStart && periodEnd ? ` · ${periodStart} → ${periodEnd}` : ""}
        {briefing.speaking_time_estimate_min
          ? ` · approx. ${briefing.speaking_time_estimate_min} min spoken`
          : ""}
        {" · "}
        <span className="text-slate-600">
          derived only from QA-passed content; the full report remains the reference product
        </span>
      </p>

      {/* ============ SLIDE 1 — THIS WEEK IN AIR POWER ============ */}
      {s1 && (
        <Slide n={1} title="This week in air power">
          {s1.bottom_line ? (
            <p className="text-sm leading-relaxed text-slate-200">{s1.bottom_line}</p>
          ) : (
            <p className="text-sm italic text-slate-500">
              No bottom line was produced for this period.
            </p>
          )}

          {(s1.headline_changes ?? []).length > 0 && (
            <ol className="mt-4 space-y-2">
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {s1.headline_changes.map((h: any, i: number) => (
                <li key={i} className="border-l-2 border-cyan-500/50 pl-3">
                  <p className="text-sm font-medium text-slate-100">
                    <span className="text-cyan-300">{i + 1}.</span> {h.label}
                  </p>
                  {h.what && <p className="text-xs text-slate-400">{h.what}</p>}
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    <Chip>confidence: {h.confidence ?? "—"}</Chip>
                    <Chip cls={TIMING_STYLE[h.effect_timing ?? "unknown"] ?? ""}>
                      earliest effect: {h.effect_timing ?? "unknown"}
                    </Chip>
                    {/* A ket horizont KULON. Egy 2028-as IOC 1-3 eves hatas,
                        meg ha a teljes kepesseg 2030 is. */}
                    {h.full_capability_timing
                      && h.full_capability_timing !== h.effect_timing && (
                      <Chip cls={TIMING_STYLE[h.full_capability_timing] ?? ""}>
                        meaningful scale: {h.full_capability_timing}
                      </Chip>
                    )}
                    <Chip cls={h.baseline_moved
                      ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-200"
                      : "border-slate-700 bg-slate-800/60 text-slate-500"}>
                      {h.baseline_moved ? "baseline moved" : "baseline unchanged"}
                    </Chip>
                  </div>
                </li>
              ))}
            </ol>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-800 pt-2 text-[11px] text-slate-500">
            <span>
              <span className="text-slate-300">{s1.volume?.events ?? "—"}</span> in-period events
            </span>
            {/* A WoW itt is a publikalt alapon all. Ha nem hasonlithato, azt
                kiirjuk — nem "+0"-t mutatunk, mint a W34. */}
            <span>
              {s1.volume?.comparable === false || s1.volume?.wow == null
                ? <span className="text-amber-300/80">
                    week-over-week: {s1.volume?.wow_basis ?? "not comparable"}
                  </span>
                : <>WoW <span className="text-slate-300">
                    {s1.volume.wow >= 0 ? "+" : ""}{s1.volume.wow}
                  </span></>}
            </span>
            {(s1.withheld ?? 0) > 0 && (
              <span className="text-amber-300/80">
                {s1.withheld} judgement(s) withheld for analyst review
              </span>
            )}
          </div>
        </Slide>
      )}

      {/* ============ SLIDE 2 — WHAT ACTUALLY CHANGED ============ */}
      {s2 && (
        <Slide n={2} title="What actually changed">
          <div className="grid gap-3 md:grid-cols-3">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {(s2.columns ?? []).map((col: any) => (
              <div key={col.key} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-300">
                  {col.title}
                </p>
                <p className="text-[10px] text-slate-600">{col.subtitle}</p>
                {(col.items ?? []).length === 0 ? (
                  <p className="mt-2 text-[11px] italic text-slate-600">
                    nothing in this horizon
                  </p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {col.items.map((it: any, i: number) => (
                      <li key={i}>
                        <p className="text-xs font-medium text-slate-200">
                          {it.label}
                          {it.year ? (
                            <span className="ml-1 font-normal text-slate-500">{it.year}</span>
                          ) : null}
                        </p>
                        {it.domain && (
                          <p className="text-[10px] text-slate-600">
                            {DOMAIN_LABELS[it.domain] ?? it.domain}
                            {it.confidence ? ` · ${it.confidence}` : ""}
                          </p>
                        )}
                        {it.note && <p className="text-[11px] text-slate-400">{it.note}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
          {s2.note && <p className="mt-2 text-[10px] text-slate-600">{s2.note}</p>}
          {(s2.undated ?? 0) > 0 && (
            <p className="mt-1 text-[10px] text-amber-300/70">
              {s2.undated} development(s) have no datable horizon and are therefore not placed in a
              column — an undated item is not a capability forecast.
            </p>
          )}
        </Slide>
      )}

      {/* ============ SLIDE 3 — DEEP DIVE ============ */}
      {s3 && (
        <Slide n={3} title="Deep dive" subtitle={s3.title}>
          <div className="space-y-3">
            {s3.what_happened && (
              <div>
                <p className="text-xs font-semibold text-slate-300">What happened?</p>
                <p className="text-sm text-slate-300">{s3.what_happened}</p>
              </div>
            )}
            {s3.capability_delta && (
              <div className="border-l-2 border-cyan-500/50 pl-2">
                <p className="text-xs font-semibold text-cyan-200">Capability delta</p>
                <p className="text-sm text-cyan-100/90">{s3.capability_delta}</p>
              </div>
            )}
            {s3.why_it_matters && (
              <div>
                <p className="text-xs font-semibold text-slate-300">Why it matters</p>
                <p className="text-sm text-slate-300">{s3.why_it_matters}</p>
              </div>
            )}
            {/* "What we don't know" — ez a slide legfontosabb resze. A W33
                Iran-KJ pontosan azert volt tulallitva, mert ez a szakasz nem
                allt szemben az iteletttel. */}
            {(s3.what_we_dont_know ?? []).length > 0 && (
              <div className="rounded border border-amber-600/30 bg-amber-500/5 p-2">
                <p className="text-xs font-semibold text-amber-300">What we don&apos;t know</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-slate-400">
                  {s3.what_we_dont_know.map((x: string, i: number) => <li key={i}>{x}</li>)}
                </ul>
              </div>
            )}
            {s3.judgement && (
              <p className="text-xs text-slate-400">
                <span className="font-medium text-slate-300">Judgement. </span>{s3.judgement}
              </p>
            )}
            <div className="flex flex-wrap gap-1.5 border-t border-slate-800 pt-2">
              <Chip>confidence: {s3.confidence ?? "—"}</Chip>
              <Chip cls={TIMING_STYLE[s3.effect_timing ?? "unknown"] ?? ""}>
                earliest effect: {s3.effect_timing ?? "unknown"}
              </Chip>
              {s3.full_capability_timing
                && s3.full_capability_timing !== s3.effect_timing && (
                <Chip cls={TIMING_STYLE[s3.full_capability_timing] ?? ""}>
                  meaningful scale: {s3.full_capability_timing}
                </Chip>
              )}
            </div>
            {s3.timing_basis && (
              <p className="text-[10px] text-slate-600">Timing basis: {s3.timing_basis}</p>
            )}
            {s3.lineage && (
              <p className="text-[10px] italic text-slate-600">Sourcing: {s3.lineage}</p>
            )}
          </div>
        </Slide>
      )}

      {/* ============ SLIDE 4 — WATCH NEXT ============ */}
      {s4 && (
        <Slide n={4} title="Watch next">
          {(s4.watch ?? []).length > 0 && (
            <ol className="space-y-2">
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {s4.watch.map((w: any, i: number) => (
                <li key={i} className="rounded border border-slate-800 bg-slate-900/50 p-2">
                  <p className="text-sm font-medium text-slate-200">
                    {w.issue}
                    <span className="ml-1 text-[11px] font-normal text-slate-500">
                      ({w.horizon ?? "—"} · impact {w.impact ?? "—"})
                    </span>
                  </p>
                  {w.why && <p className="text-xs text-slate-400">Why: {w.why}</p>}
                  {w.next_observable && (
                    <p className="text-xs text-slate-300">Next observable: {w.next_observable}</p>
                  )}
                </li>
              ))}
            </ol>
          )}

          {/* AZ ELOZO HETI WATCHOK ALLAPOTA. Enelkul a watchlista minden heten
              ujraindul, es a termek nem longitudinalis. */}
          {(s4.previous_watch ?? []).length > 0 && (
            <div className="mt-4 border-t border-slate-800 pt-2">
              <p className="text-xs font-medium text-slate-400">
                Previous period&apos;s watch items
              </p>
              <ul className="mt-1 space-y-0.5 text-[11px] text-slate-400">
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {s4.previous_watch.map((w: any, i: number) => (
                  <li key={i}>
                    <span className={WATCH_STYLE[w.state] ?? "text-slate-500"}>
                      [{w.state}]
                    </span>{" "}
                    {w.issue}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(s4.since_last_week ?? []).length > 0 && (
            <div className="mt-4 border-t border-slate-800 pt-2">
              <p className="text-xs font-medium text-slate-400">Programme movement</p>
              <table className="mt-1 w-full border-collapse text-[11px]">
                <tbody>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {s4.since_last_week.map((r: any, i: number) => (
                    <tr key={i} className="border-t border-slate-800/70">
                      <td className="p-1 font-medium text-slate-300">{r.programme}</td>
                      <td className={`p-1 ${r.moved ? "text-cyan-200" : "text-slate-600"}`}>
                        {r.change}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Slide>
      )}

      {slides.length === 0 && (
        <p className="text-sm italic text-slate-500">
          No briefing view is available for this period — it is generated alongside the report from
          v3.0 onward.
        </p>
      )}
    </div>
  );
}
