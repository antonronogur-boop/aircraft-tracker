/* COMMAND AIR INTELLIGENCE BRIEF — 4 fix oldal (A4 fekvo).
 *
 * UGYANAZ a komponens jelenik meg a teljes heti jelentes elejen, az onallo
 * /weekly/command-brief oldalon es a 4 oldalas PDF-ben (bongeszo nyomtatas).
 * A tartalom kizarolag a payload.command_brief-bol jon, amit a generator a
 * MAR QA-n atment jelentes-objektumokbol epit — itt nincs uj elemzes.
 *
 * Papirszeru megjelenes kepernyon is: ami itt latszik, az kerul a PDF-be.
 * Minden oldal fix meretu (297x210 mm), a szovegmezok sorkorlatosak, igy a
 * PDF determinisztikusan 4 oldal. A teljes szoveg a reszletes jelentesben van
 * — minden tetel hivatkozik ra (web: horgony, PDF: "Detailed assessment → D-03").
 */
import { CEE, CEE_VIEWBOX } from "@/lib/geo/cee";
import { WORLD, WORLD_VIEWBOX } from "@/lib/geo/world";

// ------------------------------------------------------------------ types --
export interface HuView {
  level: string; score: number;
  factors: { label: string; points: number }[];
  rationale?: string;
}
export interface BriefKJ {
  id: string; origin: "report_key_judgement" | "executive_synthesis";
  statement: string; hu_relevance: HuView;
  significance: number; significance_label: string;
  confidence?: string; horizon?: string;
  what_changed?: string; assessment?: string;
  why_hungary?: string; why_hungary_origin?: string;
  next_observable?: string; alternative_explanation?: string;
  alternative_origin?: string;
  refs: string[]; detail_ref?: string; countries?: string[];
}
export interface BriefRow {
  country: string; country_id: string; group: string;
  what_changed?: string; effect?: string;
  hu_relevance?: string; hu_why?: string; significance: number;
  significance_label?: string; confidence?: string; horizon?: string;
  next_observable?: string; coverage?: string; ref: string; detail_ref?: string;
}
export interface BriefItem {
  ref: string; country: string; domain?: string; what_changed?: string;
  assessment?: string; significance: number; significance_label?: string;
  confidence?: string; horizon?: string; hu_relevance?: string; hu_why?: string;
  detail_ref?: string;
}
export interface CommandBriefPayload {
  schema: string; week_label: string; title?: string; classification?: string;
  period?: { start?: string; end?: string; timezone?: string; window_label?: string };
  generated_utc?: string; status?: string; methodology_version?: string;
  hu_model_version?: string;
  restatement?: { reason: string; number?: number; restated_utc?: string } | null;
  page1: {
    bottom_line: { origin: string; sentences: { text: string; refs: string[] }[]; note?: string };
    key_judgements: BriefKJ[];
    map_cee: {
      hotspots: { country_id: string; name: string; level: string; score: number;
                  significance: number; refs: string[]; labels: string[] }[];
      collection_gaps: string[]; home: string; legend?: string;
    };
  };
  page2: {
    groups: { key: string; title: string; countries: string[] }[];
    rows: BriefRow[]; overflow?: number;
    no_material_change: { name: string; coverage: string }[];
    collection_gap: string[]; note?: string;
  };
  page3: { sections: { key: string; title: string; items: BriefItem[];
                       coverage?: string | null; empty?: string | null }[] };
  change_table: {
    previous_week?: string | null; note?: string; overflow?: number;
    rows: { priority: number; country: string; capability: string; previous?: string;
            current?: string; delta?: string; moved?: boolean; hu_relevance?: string;
            confidence?: string | null; ref?: string | null }[];
  };
  page4: {
    global: { items: BriefItem[]; empty?: string | null };
    priority_watch: { question: string; why?: string; next_observable?: string;
                      horizon?: string; impact?: string; hu_relevance?: string }[];
    intelligence_gaps: { text: string; origin: string }[];
    next_30_days: { what: string; why?: string; horizon?: string }[];
    next_30_days_empty?: string | null;
  };
  map_global: { hotspots: { country_id: string; name: string; significance: number; refs: string[] }[];
                legend?: string };
  coverage_summary?: {
    priority: { name: string; status: string; events_window: number; official_source: boolean }[];
    note?: string;
  };
  traceability?: { executive_synthesis_items: string[]; withheld_judgements_excluded: string[] };
}

// ----------------------------------------------------------------- tokens --
const HU_FILL: Record<string, string> = {
  HIGH: "#b91c1c", MEDIUM: "#ea580c", LOW: "#ca8a04", MINIMAL: "#94a3b8",
};
const HU_CHIP: Record<string, string> = {
  HIGH: "bg-red-700 text-white", MEDIUM: "bg-orange-600 text-white",
  LOW: "bg-yellow-500 text-slate-900", MINIMAL: "bg-slate-300 text-slate-800",
};
const SIG_FILL = ["#e2e8f0", "#cbd5e1", "#93c5fd", "#3b82f6", "#1d4ed8", "#1e3a8a"];
const COV_CHIP: Record<string, string> = {
  ADEQUATE: "border-emerald-600 text-emerald-800",
  PARTIAL: "border-amber-600 text-amber-800",
  GAP: "border-red-600 text-red-700",
};
const DOMAIN_SHORT: Record<string, string> = {
  fighter_strike: "Fighter/strike", attack_helicopter: "Attack helo",
  air_mobility_rotary: "Rotary lift", air_mobility_fixed: "Airlift",
  uncrewed_cca: "Uncrewed/CCA", counter_uas: "Counter-UAS",
  isr_aew_sigint: "ISR/AEW", tanker: "Tanker", training: "Training",
  maritime_patrol: "Maritime patrol", other: "Other",
};

function clampStyle(lines: number): React.CSSProperties {
  return { display: "-webkit-box", WebkitLineClamp: lines, WebkitBoxOrient: "vertical", overflow: "hidden" };
}

function HuChip({ level }: { level?: string }) {
  if (!level) return null;
  return <span className={`rounded px-1 py-px text-[9px] font-bold tracking-wide ${HU_CHIP[level] ?? HU_CHIP.MINIMAL}`}>HU {level}</span>;
}

function Meta({ children }: { children: React.ReactNode }) {
  return <span className="rounded border border-slate-300 px-1 py-px text-[9px] text-slate-700">{children}</span>;
}

function Ref({ refs, base, children }: { refs: string[]; base: string; children?: React.ReactNode }) {
  const first = refs.find(Boolean);
  if (!first) return null;
  return (
    <a href={`${base}#${first}`} className="cb-ref whitespace-nowrap font-mono text-[9px] text-sky-800 hover:underline">
      {children ?? <>→ Detailed assessment {refs.join(", ")}</>}
    </a>
  );
}

function PageFrame({ n, brief, title, subtitle, children }: {
  n: number; brief: CommandBriefPayload; title: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <section className="cb-page" data-cb-page={n} aria-label={`Command brief page ${n}`}>
      <header className="cb-head">
        <div className="min-w-0">
          <p className="text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Command Air Intelligence Brief · Hungary
          </p>
          <h2 className="truncate text-[15px] font-bold leading-tight text-slate-900">{title}</h2>
          {subtitle && <p className="text-[9.5px] text-slate-600">{subtitle}</p>}
        </div>
        <div className="shrink-0 text-right text-[9px] leading-snug text-slate-600">
          <p className="font-bold text-slate-900">{brief.week_label}</p>
          <p>{brief.period?.start} → {brief.period?.end} · {brief.period?.timezone ?? "Europe/Budapest"}</p>
          <p className="font-semibold tracking-wide text-slate-800">{brief.classification ?? "UNCLASSIFIED // OSINT"}</p>
        </div>
      </header>
      {brief.restatement && (
        <p className="mb-1 rounded border border-amber-500 bg-amber-50 px-2 py-0.5 text-[9px] text-amber-900">
          RESTATEMENT #{brief.restatement.number ?? 1}: {brief.restatement.reason}
        </p>
      )}
      <div className="cb-body">{children}</div>
      {/* div, nem <footer>: a globalis print-szabaly a footer elemeket elrejti */}
      <div className="cb-foot">
        <span>
          Page {n}/4 · Built from weekly report {brief.week_label} (methodology {brief.methodology_version ?? "—"},
          HU model {brief.hu_model_version ?? "—"}) · FACT ≠ ASSESSMENT · significance ≠ confidence ·
          procurement ≠ operational capability
        </span>
        <span>{brief.generated_utc}</span>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------- maps --
function CeeMap({ map }: { map: CommandBriefPayload["page1"]["map_cee"] }) {
  const hot = new Map(map.hotspots.map((h) => [h.country_id, h]));
  const gaps = new Set(map.collection_gaps);
  return (
    <svg viewBox={CEE_VIEWBOX} className="h-auto w-full" role="img"
         aria-label="Central and Eastern Europe — hotspots by Hungary relevance">
      <rect x="0" y="0" width="600" height="470" fill="#dbe7f0" />
      {Object.entries(CEE).map(([id, g]) => {
        const h = hot.get(id);
        const fill = id === map.home ? "#fef3c7" : h ? HU_FILL[h.level] ?? "#cbd5e1" : "#f4f4f2";
        return (
          <path key={id} d={g.d} fill={fill} fillOpacity={h ? 0.85 : 1}
                stroke={gaps.has(id) ? "#dc2626" : id === map.home ? "#92400e" : "#64748b"}
                strokeWidth={id === map.home ? 1.6 : gaps.has(id) ? 1.1 : 0.7}
                strokeDasharray={gaps.has(id) ? "3 2" : undefined} />
        );
      })}
      {Object.entries(CEE).map(([id, g]) => {
        const h = hot.get(id);
        if (!h && id !== map.home) {
          // Tajekozodasi cimke a nem-hotspot orszagokra (halvany).
          return CEE_ORIENT.has(id) ? (
            <text key={`o-${id}`} x={g.c[0]} y={g.c[1]} textAnchor="middle" fontSize={8.5} fill="#64748b">
              {id.toUpperCase()}
            </text>
          ) : null;
        }
        return (
          <g key={`l-${id}`}>
            <text x={g.c[0]} y={g.c[1]} textAnchor="middle" fontSize={id === map.home ? 11 : 10}
                  fontWeight={700} fill={id !== map.home && h && h.level !== "MINIMAL" ? "#ffffff" : "#1e293b"}
                  stroke={id !== map.home && h && h.level !== "MINIMAL" ? "#00000055" : "none"} strokeWidth={0.3}>
              {id.toUpperCase()}
            </text>
            {h && (
              <text x={g.c[0]} y={g.c[1] + 11} textAnchor="middle" fontSize={8.5} fill="#0f172a"
                    fontWeight={600}>
                {h.refs.slice(0, 3).join(" ")}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

const CEE_ORIENT = new Set(["aut", "svk", "cze", "pol", "ukr", "rou", "srb", "hrv", "svn", "bih",
  "blr", "rus", "bgr", "mda", "ltu", "lva", "est", "deu", "ita", "grc", "tur", "mne", "mkd", "alb", "xkx"]);

function GlobalMap({ map }: { map: CommandBriefPayload["map_global"] }) {
  const hot = new Map(map.hotspots.map((h) => [h.country_id, h]));
  // A kozep-kelet-europai hotspotok a page-1 terkepen vannak: itt csak a
  // kitoltes marad, a cimkeket egyetlen "Europe → p.1" jelolo valtja ki.
  const europe = map.hotspots.filter((h) => CEE[h.country_id] && h.country_id !== "rus" && h.country_id !== "tur");
  const eu = WORLD["deu"];
  return (
    <svg viewBox={WORLD_VIEWBOX} className="h-auto w-full" role="img"
         aria-label="Global hotspots by air-power significance">
      <rect x="0" y="0" width="800" height="410" fill="#eef4f8" />
      {Object.entries(WORLD).map(([id, g]) => {
        const h = hot.get(id);
        return <path key={id} d={g.d} fill={h ? SIG_FILL[h.significance] : "#f8fafc"}
                     stroke="#94a3b8" strokeWidth={0.4} />;
      })}
      {europe.length > 0 && eu && (
        <g>
          <circle cx={eu.c[0] + 8} cy={eu.c[1]} r={14} fill="none" stroke="#0f172a" strokeWidth={1} strokeDasharray="2 2" />
          <text x={eu.c[0] - 30} y={eu.c[1] - 18} fontSize={9} fontWeight={700} fill="#0f172a">
            EUROPE ({europe.length}) → p.1 map
          </text>
        </g>
      )}
      {map.hotspots.map((h) => {
        const g = WORLD[h.country_id];
        if (!g || europe.includes(h)) return null;
        return (
          <g key={h.country_id}>
            <circle cx={g.c[0]} cy={g.c[1]} r={3 + h.significance} fill="none" stroke="#0f172a" strokeWidth={1} />
            <text x={g.c[0] + 6 + h.significance} y={g.c[1] + 3} fontSize={9} fontWeight={700} fill="#0f172a">
              {h.country_id.toUpperCase()} {h.refs[0]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ------------------------------------------------------------------ pages --
function Page1({ b, base }: { b: CommandBriefPayload; base: string }) {
  const kjs = b.page1.key_judgements;
  const roomy = kjs.length <= 3;
  const bl = b.page1.bottom_line;
  return (
    <PageFrame n={1} brief={b} title="Hungary Air Intelligence Bottom Line"
               subtitle="What changed → why it matters → what it means for Hungary / MH / NATO → what to watch">
      <div className="grid h-full grid-cols-[39%_1fr] gap-3">
        <div className="flex min-h-0 flex-col gap-2">
          <div className="rounded border-l-4 border-slate-900 bg-slate-50 px-2.5 py-2">
            <p className="mb-1 flex items-center justify-between text-[9px] font-bold uppercase tracking-wide text-slate-700">
              <span>Bottom line</span>
              <span className={`rounded px-1 py-px text-[8.5px] font-semibold normal-case ${
                bl.origin === "executive_synthesis" ? "bg-violet-700 text-white" : "bg-slate-200 text-slate-700"}`}>
                {bl.origin === "executive_synthesis" ? "Executive synthesis" : "Deterministic from judgements"}
              </span>
            </p>
            <p className="text-[10.5px] leading-[1.38] text-slate-900" style={clampStyle(21)}>
              {bl.sentences.map((s, i) => (
                <span key={i}>
                  {s.text}
                  {s.refs.length > 0 && (
                    <a href={`${base}#${s.refs[0]}`} className="cb-ref ml-0.5 align-super font-mono text-[7.5px] text-sky-800">
                      [{s.refs.join(",")}]
                    </a>
                  )}{" "}
                </span>
              ))}
            </p>
          </div>
          <div className="min-h-0">
            <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">Regional air picture</p>
            <div className="overflow-hidden rounded border border-slate-300">
              <CeeMap map={b.page1.map_cee} />
            </div>
            <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[8.5px] text-slate-600">
              {(["HIGH", "MEDIUM", "LOW"] as const).map((l) => (
                <span key={l} className="inline-flex items-center gap-0.5">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: HU_FILL[l] }} />{l}
                </span>
              ))}
              <span className="inline-flex items-center gap-0.5">
                <span className="inline-block h-2 w-3 rounded-sm border border-dashed border-red-600" />collection gap
              </span>
              <span className="inline-flex items-center gap-0.5">
                <span className="inline-block h-2 w-3 rounded-sm border border-amber-800 bg-amber-100" />Hungary
              </span>
            </p>
            <p className="text-[8px] leading-tight text-slate-500" style={clampStyle(2)}>{b.page1.map_cee.legend}</p>
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-1.5">
          <p className="text-[9px] font-bold uppercase tracking-wide text-slate-700">
            Key judgements — ranked by Hungary relevance → significance → confidence → immediacy
          </p>
          {kjs.length === 0 && (
            <p className="text-[10px] text-slate-600">No judgement passed QA this period — see the detailed report.</p>
          )}
          {kjs.map((k) => (
            <article key={k.id} id={k.origin === "executive_synthesis" ? k.id : undefined}
                     className={`scroll-mt-20 rounded border px-2 py-1.5 ${
              k.origin === "executive_synthesis" ? "border-violet-400 bg-violet-50/40" : "border-slate-300"}`}>
              <p className="text-[10.5px] font-bold leading-snug text-slate-900" style={clampStyle(2)}>
                <span className="font-mono">{k.id}</span> — {k.statement}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-1">
                <HuChip level={k.hu_relevance.level} />
                <Meta>SIG {k.significance}/5 {k.significance_label}</Meta>
                <Meta>Conf. {k.confidence ?? "—"}</Meta>
                <Meta>{k.horizon}</Meta>
                {k.origin === "executive_synthesis" && (
                  <span className="rounded bg-violet-700 px-1 py-px text-[8.5px] text-white">Executive synthesis</span>
                )}
                <span className="ml-auto"><Ref refs={k.refs} base={base} /></span>
              </p>
              <div className="mt-0.5 grid grid-cols-2 gap-x-2.5 text-[9.5px] leading-[1.3] text-slate-800">
                <div>
                  <p style={clampStyle(roomy ? 3 : 2)}><b>What changed:</b> {k.what_changed}</p>
                  <p style={clampStyle(roomy ? 4 : 3)}><b>Assessment:</b> {k.assessment}</p>
                </div>
                <div>
                  <p style={clampStyle(roomy ? 3 : 2)}><b>Why Hungary should care:</b> {k.why_hungary}</p>
                  <p style={clampStyle(1)}><b>Next observable:</b> {k.next_observable || "—"}</p>
                  <p className="text-slate-600" style={clampStyle(2)}>
                    <b>What would make this wrong:</b> {k.alternative_explanation || "—"}
                  </p>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </PageFrame>
  );
}

const GROUP_LABEL: Record<string, string> = {
  home: "Hungary (own forces)", non_nato_priority: "Non-NATO priority", neighbours: "Neighbour", extended_nato: "Extended NATO",
};

function Page2({ b, base }: { b: CommandBriefPayload; base: string }) {
  const p = b.page2;
  return (
    <PageFrame n={2} brief={b} title="Immediate & near-regional air picture"
               subtitle="Non-NATO priority · neighbours · extended NATO — material changes only">
      <table className="w-full table-fixed border-collapse text-[9.5px] leading-[1.28] text-slate-900">
        <colgroup>
          <col style={{ width: "10%" }} /><col style={{ width: "24%" }} /><col style={{ width: "22%" }} />
          <col style={{ width: "8%" }} /><col style={{ width: "7%" }} /><col style={{ width: "7%" }} />
          <col style={{ width: "16%" }} /><col style={{ width: "6%" }} />
        </colgroup>
        <thead>
          <tr className="bg-slate-800 text-left text-[9px] uppercase tracking-wide text-white">
            <th className="px-1.5 py-1">Country</th><th className="px-1.5 py-1">What changed</th>
            <th className="px-1.5 py-1">Capability / operational effect</th><th className="px-1.5 py-1">HU relevance</th>
            <th className="px-1.5 py-1">Signif.</th><th className="px-1.5 py-1">Conf.</th>
            <th className="px-1.5 py-1">Next observable</th><th className="px-1.5 py-1">Ref</th>
          </tr>
        </thead>
        <tbody>
          {p.rows.length === 0 && (
            <tr><td colSpan={8} className="px-2 py-3 text-center font-semibold text-slate-700">
              NO MATERIAL CHANGE IDENTIFIED in the immediate and near region
            </td></tr>
          )}
          {p.rows.map((r) => (
            <tr key={r.ref} className="border-b border-slate-200 align-top">
              <td className="px-1.5 py-1">
                <p className="font-bold" style={clampStyle(2)}>{r.country}</p>
                <p className="text-[8.5px] text-slate-500">{GROUP_LABEL[r.group] ?? r.group}</p>
              </td>
              <td className="px-1.5 py-1"><p style={clampStyle(4)}>{r.what_changed}</p></td>
              <td className="px-1.5 py-1"><p style={clampStyle(4)}>{r.effect}</p></td>
              <td className="px-1.5 py-1">
                <HuChip level={r.hu_relevance} />
                <p className="mt-0.5 text-[8px] leading-tight text-slate-600" style={clampStyle(3)}>{r.hu_why}</p>
              </td>
              <td className="px-1.5 py-1">{r.significance}/5<br /><span className="text-[8.5px] text-slate-500">{r.significance_label}</span></td>
              <td className="px-1.5 py-1">{r.confidence ?? "—"}<br /><span className="text-[8.5px] text-slate-500">{r.horizon}</span></td>
              <td className="px-1.5 py-1"><p style={clampStyle(3)}>{r.next_observable || "—"}</p></td>
              <td className="px-1.5 py-1"><Ref refs={[r.ref]} base={base}>{r.ref}</Ref></td>
            </tr>
          ))}
        </tbody>
      </table>
      {(p.overflow ?? 0) > 0 && (
        <p className="mt-0.5 text-[8.5px] text-slate-600">+{p.overflow} further regional item(s) in the detailed assessment.</p>
      )}
      <div className="mt-2 grid grid-cols-3 gap-2 text-[9.5px]">
        <div className="rounded border border-slate-300 p-1.5">
          <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">No material change identified</p>
          <p className="text-slate-800">
            {p.no_material_change.length
              ? p.no_material_change.map((x, i) => (
                  <span key={x.name}>{i ? " · " : ""}{x.name}<span className="text-[8px] text-slate-500"> ({x.coverage.toLowerCase()})</span></span>))
              : "—"}
          </p>
        </div>
        <div className="rounded border border-dashed border-red-500 p-1.5">
          <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-red-700">Collection gap</p>
          <p className="text-slate-800">{p.collection_gap.length ? p.collection_gap.join(" · ") : "—"}</p>
          <p className="mt-0.5 text-[8px] text-slate-500">No reporting reached the collection: quiet cannot be told from unobserved.</p>
        </div>
        <div className="rounded border border-slate-300 p-1.5">
          <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">Coverage (60 days)</p>
          <p className="flex flex-wrap gap-0.5">
            {(b.coverage_summary?.priority ?? []).map((c) => (
              <span key={c.name} className={`rounded border px-1 text-[8px] ${COV_CHIP[c.status] ?? ""}`}
                    title={c.official_source ? "official source collected" : "no official source collected"}>
                {c.name}{c.official_source ? "" : "*"}
              </span>
            ))}
          </p>
          <p className="mt-0.5 text-[8px] text-slate-500">* no official AF/MoD source in collection.</p>
        </div>
      </div>
      <p className="mt-1 text-[8px] leading-tight text-slate-500">{p.note}</p>
    </PageFrame>
  );
}

function ItemCard({ it, base, lines = 2 }: { it: BriefItem; base: string; lines?: number }) {
  return (
    <article className="rounded border border-slate-300 px-1.5 py-1">
      <p className="flex items-baseline justify-between gap-1 text-[9px] text-slate-600">
        <span className="truncate font-bold text-slate-900">{it.country}</span>
        <span className="shrink-0">{DOMAIN_SHORT[it.domain ?? ""] ?? it.domain}</span>
      </p>
      <p className="text-[9.5px] font-semibold leading-snug text-slate-900" style={clampStyle(2)}>{it.what_changed}</p>
      <p className="text-[9px] leading-[1.28] text-slate-800" style={clampStyle(lines)}>{it.assessment}</p>
      <p className="mt-0.5 flex flex-wrap items-center gap-1">
        <Meta>SIG {it.significance}/5</Meta><Meta>{it.confidence ?? "—"}</Meta><Meta>{it.horizon}</Meta>
        <HuChip level={it.hu_relevance} />
        <span className="ml-auto"><Ref refs={[it.ref]} base={base}>{it.ref}</Ref></span>
      </p>
      {it.hu_why && <p className="text-[8px] leading-tight text-slate-500" style={clampStyle(1)}>HU/NATO: {it.hu_why}</p>}
    </article>
  );
}

function Page3({ b, base }: { b: CommandBriefPayload; base: string }) {
  const ct = b.change_table;
  return (
    <PageFrame n={3} brief={b} title="Middle East · Africa · Wider NATO — and what changed since last week"
               subtitle="Material developments only (2–4 per region). Executive change table from the previous published report.">
      <div className="grid grid-cols-3 gap-2">
        {b.page3.sections.map((s) => (
          <div key={s.key} className="flex min-h-0 flex-col gap-1">
            <p className="flex items-center justify-between border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">
              {s.title}
              {s.coverage && <span className={`rounded border px-1 text-[8px] font-semibold normal-case ${COV_CHIP[s.coverage] ?? ""}`}>coverage {s.coverage.toLowerCase()}</span>}
            </p>
            {s.items.length === 0 && (
              <p className="py-2 text-center text-[9.5px] font-semibold text-slate-600">{s.empty}</p>
            )}
            {s.items.map((it) => <ItemCard key={it.ref} it={it} base={base} lines={s.items.length <= 2 ? 4 : 2} />)}
          </div>
        ))}
      </div>
      <div className="mt-2">
        <p className="mb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">
          Executive change table{ct.previous_week ? ` — against ${ct.previous_week} (published)` : ""}
        </p>
        <table className="w-full table-fixed border-collapse text-[9px] leading-[1.25] text-slate-900">
          <colgroup>
            <col style={{ width: "5%" }} /><col style={{ width: "11%" }} /><col style={{ width: "17%" }} />
            <col style={{ width: "15%" }} /><col style={{ width: "15%" }} /><col style={{ width: "21%" }} />
            <col style={{ width: "8%" }} /><col style={{ width: "8%" }} />
          </colgroup>
          <thead>
            <tr className="bg-slate-800 text-left text-[8.5px] uppercase tracking-wide text-white">
              <th className="px-1 py-0.5">Prio</th><th className="px-1 py-0.5">Country</th>
              <th className="px-1 py-0.5">Capability</th><th className="px-1 py-0.5">Previous state</th>
              <th className="px-1 py-0.5">Current state</th><th className="px-1 py-0.5">Delta</th>
              <th className="px-1 py-0.5">HU relevance</th><th className="px-1 py-0.5">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {ct.rows.length === 0 && (
              <tr><td colSpan={8} className="px-2 py-1.5 text-center text-slate-600">
                {ct.note || "No prior published report — the comparison begins next period."}
              </td></tr>
            )}
            {ct.rows.map((r) => (
              <tr key={`${r.priority}-${r.capability}`} className={`border-b border-slate-200 align-top ${r.moved ? "" : "text-slate-500"}`}>
                <td className="px-1 py-0.5 font-bold">{r.priority}</td>
                <td className="px-1 py-0.5"><p style={clampStyle(2)}>{r.country}</p></td>
                <td className="px-1 py-0.5">
                  <p style={clampStyle(2)}>{r.ref ? <Ref refs={[r.ref]} base={base}>{r.capability}</Ref> : r.capability}</p>
                </td>
                <td className="px-1 py-0.5"><p style={clampStyle(2)}>{r.previous}</p></td>
                <td className="px-1 py-0.5"><p style={clampStyle(2)}>{r.current}</p></td>
                <td className="px-1 py-0.5"><p style={clampStyle(2)}>{r.delta}</p></td>
                <td className="px-1 py-0.5"><HuChip level={r.hu_relevance} /></td>
                <td className="px-1 py-0.5">{r.confidence ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(ct.overflow ?? 0) > 0 && <p className="text-[8px] text-slate-500">+{ct.overflow} further programme row(s) in the detailed report (Since last week).</p>}
      </div>
    </PageFrame>
  );
}

function Page4({ b, base }: { b: CommandBriefPayload; base: string }) {
  const p = b.page4;
  return (
    <PageFrame n={4} brief={b} title="Global strategic picture · Watch · Gaps · Next 7–30 days"
               subtitle="China, Taiwan, Japan, South Korea, India, Australia, Indo-Pacific — and what to watch">
      <div className="grid h-full grid-cols-[55%_1fr] gap-3">
        <div className="flex min-h-0 flex-col gap-1.5">
          <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">Global strategic</p>
          {p.global.items.length === 0
            ? <p className="py-2 text-center text-[9.5px] font-semibold text-slate-600">{p.global.empty}</p>
            : <div className="grid grid-cols-2 gap-1.5">
                {p.global.items.map((it) => <ItemCard key={it.ref} it={it} base={base} lines={3} />)}
              </div>}
          <div>
            <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">Global hotspots</p>
            <div className="overflow-hidden rounded border border-slate-300"><GlobalMap map={b.map_global} /></div>
            <p className="mt-0.5 flex items-center gap-1 text-[8.5px] text-slate-600">
              Significance {[1, 2, 3, 4, 5].map((s) => (
                <span key={s} className="inline-flex items-center gap-0.5">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: SIG_FILL[s] }} />{s}
                </span>))}
              <span className="ml-1 text-slate-500">— {b.map_global.legend}</span>
            </p>
          </div>
        </div>
        <div className="flex min-h-0 flex-col gap-2 text-[9.5px] leading-[1.28] text-slate-900">
          <div>
            <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide">Priority intelligence watch</p>
            {p.priority_watch.length === 0 && <p className="text-slate-600">No priority watch item this period.</p>}
            <ol className="mt-0.5 space-y-1">
              {p.priority_watch.map((w, i) => (
                <li key={i} className="border-l-2 border-slate-400 pl-1.5">
                  <p className="font-bold" style={clampStyle(1)}>{i + 1}. {w.question}</p>
                  <p style={clampStyle(1)}><b>Why:</b> {w.why}</p>
                  <p style={clampStyle(1)}><b>Next observable:</b> {w.next_observable}</p>
                  <p className="flex gap-1 text-[8.5px] text-slate-600">
                    <span>horizon {w.horizon ?? "—"}</span><span>· impact {w.impact ?? "—"}</span>
                    {w.hu_relevance && <HuChip level={w.hu_relevance} />}
                  </p>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide">Intelligence gaps</p>
            <ul className="mt-0.5 space-y-0.5">
              {p.intelligence_gaps.map((g, i) => (
                <li key={i} style={clampStyle(2)}>• {g.text}
                  {g.origin === "coverage_audit" && <span className="text-[8px] text-slate-500"> (coverage audit)</span>}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide">Next 7–30 days</p>
            {p.next_30_days.length === 0
              ? <p className="mt-0.5 text-slate-600">{p.next_30_days_empty}</p>
              : <ul className="mt-0.5 space-y-0.5">
                  {p.next_30_days.slice(0, 4).map((x, i) => (
                    <li key={i} style={clampStyle(2)}>• <b>{x.what}</b> <span className="text-slate-600">— {x.why} ({x.horizon})</span></li>
                  ))}
                </ul>}
          </div>
          <p className="mt-auto text-[8px] leading-tight text-slate-500">
            {b.traceability?.executive_synthesis_items?.length
              ? `Executive synthesis items (${b.traceability.executive_synthesis_items.join(", ")}) are higher-level readings traced to the cited D-xx developments. `
              : ""}
            {b.traceability?.withheld_judgements_excluded?.length
              ? `Withheld by QA and excluded: ${b.traceability.withheld_judgements_excluded.join(", ")}.`
              : ""}
          </p>
        </div>
      </div>
    </PageFrame>
  );
}

export function CommandBrief({ brief, detailBase = "" }: { brief: CommandBriefPayload; detailBase?: string }) {
  return (
    <div className="cb" data-command-brief={brief.week_label}>
      <Page1 b={brief} base={detailBase} />
      <Page2 b={brief} base={detailBase} />
      <Page3 b={brief} base={detailBase} />
      <Page4 b={brief} base={detailBase} />
    </div>
  );
}
