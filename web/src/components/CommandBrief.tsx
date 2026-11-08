/* COMMAND AIR INTELLIGENCE BRIEF v2 — 4 vezetoi oldal + Sources & Legend.
 *
 * Onallo termek: a reszletes heti jelentes nelkul is ertheto. Minden vezetoi
 * tetel az EREDETI forrasra hivatkozik (S-xx -> kattinthato cikk, page 5).
 * A tartalom kizarolag a payload.command_brief-bol jon (scripts/
 * ac_command_brief.py) — ugyanabbol, amibol a Word-export keszul.
 *
 * Papirszeru megjelenes kepernyon is: ami itt latszik, az kerul a PDF-be.
 * Az 1–4. oldal fix A4 fekvo meretu; a vezetoi szoveg NINCS sorkorlattal
 * vagva (a modell rovid, egesz mondatokat ad). Az 5. oldal (forrasjegyzek)
 * szukseg eseten tobb oldalra folyhat.
 */
import type { CommandBriefV2, BriefItem } from "@/lib/briefTypes";
import { HORIZON_LABEL } from "@/lib/briefTypes";
import { ceeMapSvg, globalMapSvg, HU_FILL, SIG_FILL } from "@/lib/briefMaps";

const HU_CHIP: Record<string, string> = {
  HIGH: "bg-red-700 text-white", MEDIUM: "bg-orange-600 text-white",
  LOW: "bg-yellow-500 text-slate-900", MINIMAL: "bg-slate-300 text-slate-800",
};
const COV_CHIP: Record<string, string> = {
  ADEQUATE: "border-emerald-600 text-emerald-800",
  PARTIAL: "border-amber-600 text-amber-800",
  GAP: "border-red-600 text-red-700",
};
const GROUP_LABEL: Record<string, string> = {
  home: "Hungary (own forces)", non_nato_priority: "Non-NATO priority",
  neighbours: "Neighbour", extended_nato: "Extended regional NATO",
};

type SrcIndex = Map<string, { url: string; title: string; tier_rank: number }>;

function HuChip({ level }: { level?: string }) {
  if (!level) return null;
  return <span className={`rounded px-1 py-px text-[9px] font-bold tracking-wide ${HU_CHIP[level] ?? HU_CHIP.MINIMAL}`}>HU {level}</span>;
}

function Meta({ children }: { children: React.ReactNode }) {
  return <span className="rounded border border-slate-300 px-1 py-px text-[9px] text-slate-700">{children}</span>;
}

function Sources({ ids, idx, label = true }: { ids: string[]; idx: SrcIndex; label?: boolean }) {
  if (!ids?.length) return null;
  return (
    <span className="cb-src text-[8.5px] text-slate-600">
      {label && "Sources: "}
      {ids.map((id, i) => {
        const s = idx.get(id);
        return (
          <span key={id}>
            {i > 0 && " · "}
            {s ? (
              <a href={s.url} target="_blank" rel="noopener noreferrer" title={s.title}
                 className="cb-ref font-mono text-sky-800 hover:underline">{id}</a>
            ) : <span className="font-mono">{id}</span>}
            {s && s.tier_rank === 1 && <span className="text-[7.5px] text-slate-500"> (official)</span>}
          </span>
        );
      })}
    </span>
  );
}

/* Ha egy tetelnek nincs KOZVETLEN forrasa, azt kimondjuk — a kontextus-
 * cikk nem bizonyitek. */
function NoDirect({ ctx, idx }: { ctx?: string[]; idx: SrcIndex }) {
  if (!ctx?.length) return null;
  return (
    <span className="text-[8px] text-amber-800">
      No direct source — claim appears only in the body of <Sources ids={ctx} idx={idx} label={false} /> (context, not evidence)
    </span>
  );
}

function PageFrame({ n, brief, title, subtitle, flow = false, children }: {
  n: number | string; brief: CommandBriefV2; title: string; subtitle?: string;
  flow?: boolean; children: React.ReactNode;
}) {
  const m = brief.meta;
  return (
    <section className={`cb-page ${flow ? "cb-flow" : ""}`} data-cb-page={n} aria-label={`Command brief page ${n}`}>
      <header className="cb-head">
        <div className="min-w-0">
          <p className="text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Command Air Intelligence Brief · Hungary
          </p>
          <h2 className="text-[15px] font-bold leading-tight text-slate-900">{title}</h2>
          {subtitle && <p className="text-[9.5px] text-slate-600">{subtitle}</p>}
        </div>
        <div className="shrink-0 text-right text-[9px] leading-snug text-slate-600">
          <p className="font-bold text-slate-900">
            {brief.week_label}
            {m.revision && (
              <span className="ml-1 rounded border border-slate-400 px-1 text-[8px] font-normal text-slate-600"
                    title={m.revision.reason}>rev. {m.revision.number}</span>
            )}
          </p>
          <p>{m.period_start} → {m.period_end} · {m.timezone ?? "Europe/Budapest"}</p>
          <p className="font-semibold tracking-wide text-slate-800">{brief.classification}</p>
        </div>
      </header>
      <div className="cb-body">{children}</div>
      {/* div, nem <footer>: a globalis print-szabaly a footer elemeket elrejti */}
      <div className="cb-foot">
        <span className="cb-micro">{brief.micro_legend}</span>
        <span className="shrink-0">p. {n} · {m.generated_utc} · method {m.methodology_version ?? "—"} · HU model {m.hu_model_version ?? "—"}</span>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ pages --
function Page1({ b, idx }: { b: CommandBriefV2; idx: SrcIndex }) {
  const p = b.page1;
  const bl = p.bottom_line;
  return (
    <PageFrame n={1} brief={b} title="Hungary Air Intelligence Bottom Line"
               subtitle="What changed → why it matters → what it means for Hungary / MH / NATO → what to watch">
      <div className="grid h-full grid-cols-[37%_1fr] gap-3">
        <div className="flex min-h-0 flex-col gap-2">
          <div className="rounded border-l-4 border-slate-900 bg-slate-50 px-2.5 py-2">
            <p className="mb-1 flex items-center justify-between text-[9px] font-bold uppercase tracking-wide text-slate-700">
              <span>Bottom line</span>
              <span className={`rounded px-1 py-px text-[8.5px] font-semibold normal-case ${
                bl.origin === "executive_synthesis" ? "bg-violet-700 text-white" : "bg-slate-200 text-slate-700"}`}>
                {bl.origin === "executive_synthesis" ? "Executive synthesis" : "Built from assessed judgements"}
              </span>
            </p>
            <p className="text-[10.5px] leading-[1.4] text-slate-900">
              {bl.sentences.map((s, i) => (
                <span key={i}>
                  {s.text}
                  {s.sources.length > 0 && <> <Sources ids={s.sources} idx={idx} label={false} /></>}{" "}
                </span>
              ))}
            </p>
          </div>
          <div className="min-h-0">
            <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">Regional air picture</p>
            <div className="cb-map overflow-hidden rounded border border-slate-300"
                 dangerouslySetInnerHTML={{ __html: ceeMapSvg(p.map_cee) }} />
            <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[8.5px] text-slate-600">
              {(["HIGH", "MEDIUM", "LOW"] as const).map((l) => (
                <span key={l} className="inline-flex items-center gap-0.5">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: HU_FILL[l] }} />HU {l}
                </span>
              ))}
              <span className="inline-flex items-center gap-0.5">
                <span className="inline-block h-2 w-3 rounded-sm border border-dashed border-red-600" />collection gap
              </span>
              <span className="inline-flex items-center gap-0.5">
                <span className="inline-block h-2 w-3 rounded-sm border border-amber-800 bg-amber-100" />Hungary
              </span>
            </p>
            <p className="text-[8px] leading-tight text-slate-500">{p.map_cee.caption}</p>
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-1.5">
          <p className="text-[9px] font-bold uppercase tracking-wide text-slate-700">
            Primary key judgements — ranked by Hungary relevance → significance → confidence → immediacy
          </p>
          {p.primary.length === 0 && <p className="text-[10px] text-slate-700">{p.primary_empty}</p>}
          {p.primary.map((k) => (
            <article key={k.id} className={`rounded border px-2 py-1.5 ${
              k.origin === "executive_synthesis" ? "border-violet-400 bg-violet-50/40" : "border-slate-300"}`}>
              <p className="text-[10.5px] font-bold leading-snug text-slate-900">
                <span className="font-mono">{k.id}</span> — {k.statement}
              </p>
              <p className="mt-0.5 flex flex-wrap items-center gap-1">
                <HuChip level={k.hu_relevance.level} />
                <Meta>SIG {k.significance}/5</Meta>
                <Meta>CONF {(k.confidence ?? "—").toUpperCase()}</Meta>
                <Meta>{HORIZON_LABEL(k.horizon)}</Meta>
                {k.origin === "executive_synthesis" && (
                  <span className="rounded bg-violet-700 px-1 py-px text-[8.5px] text-white">Executive synthesis</span>
                )}
              </p>
              <div className="mt-0.5 grid grid-cols-2 gap-x-2.5 text-[9.5px] leading-[1.32] text-slate-800">
                <div>
                  <p><b>What changed:</b> {k.what_changed}</p>
                  <p><b>Assessment:</b> {k.assessment}</p>
                </div>
                <div>
                  <p><b>Why Hungary should care:</b> {k.why_hungary}</p>
                  <p><b>Next observable:</b> {k.next_observable}</p>
                  <p className="text-slate-600"><b>What would make this wrong:</b> {k.alternative_explanation}</p>
                </div>
              </div>
              <p className="mt-0.5 text-right"><Sources ids={k.sources} idx={idx} /></p>
            </article>
          ))}
          {p.secondary_watch.length > 0 && (
            <div className="rounded border border-dashed border-slate-300 px-2 py-1">
              <p className="text-[9px] font-bold uppercase tracking-wide text-slate-600">
                Secondary air power watch — globally significant, low direct relevance to Hungary
              </p>
              <ul className="mt-0.5 space-y-0.5 text-[9.5px] leading-snug text-slate-700">
                {p.secondary_watch.map((s) => (
                  <li key={s.id} className="flex items-baseline gap-1">
                    <span className="min-w-0 flex-1">{s.line}</span>
                    <span className="shrink-0 text-[8.5px] text-slate-500">SIG {s.significance}/5 · HU {s.hu_level}</span>
                    <span className="shrink-0"><Sources ids={s.sources} idx={idx} label={false} /></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </PageFrame>
  );
}

function Page2({ b, idx }: { b: CommandBriefV2; idx: SrcIndex }) {
  const p = b.page2;
  return (
    <PageFrame n={2} brief={b} title="Immediate & Near-Regional Air Picture"
               subtitle="Non-NATO priority · Hungary's neighbours · extended regional NATO — material changes only">
      <table className="w-full table-fixed border-collapse text-[9.3px] leading-[1.28] text-slate-900">
        <colgroup>
          <col style={{ width: "10%" }} /><col style={{ width: "25%" }} /><col style={{ width: "22%" }} />
          <col style={{ width: "13%" }} /><col style={{ width: "6%" }} /><col style={{ width: "7%" }} />
          <col style={{ width: "17%" }} />
        </colgroup>
        <thead>
          <tr className="bg-slate-800 text-left text-[8.5px] uppercase tracking-wide text-white">
            <th className="px-1.5 py-1">Country</th><th className="px-1.5 py-1">What changed</th>
            <th className="px-1.5 py-1">Capability / operational effect</th><th className="px-1.5 py-1">HU relevance</th>
            <th className="px-1.5 py-1">SIG</th><th className="px-1.5 py-1">CONF</th>
            <th className="px-1.5 py-1">Next observable · sources</th>
          </tr>
        </thead>
        <tbody>
          {p.rows.length === 0 && (
            <tr><td colSpan={7} className="px-2 py-3 text-center font-semibold text-slate-700">
              NO MATERIAL CHANGE IDENTIFIED in the immediate and near region
            </td></tr>
          )}
          {p.rows.map((r) => (
            <tr key={r.ref} className="border-b border-slate-200 align-top">
              <td className="px-1.5 py-1">
                <p className="font-bold">{r.country}</p>
                <p className="text-[8.5px] text-slate-500">{GROUP_LABEL[r.group] ?? r.group}</p>
              </td>
              <td className="px-1.5 py-1">{r.what_changed}</td>
              <td className="px-1.5 py-1">{r.effect}</td>
              <td className="px-1.5 py-1">
                <HuChip level={r.hu_relevance} />
                <p className="mt-0.5 text-[8px] leading-tight text-slate-600">{r.hu_why}</p>
              </td>
              <td className="px-1.5 py-1">{r.significance}/5</td>
              <td className="px-1.5 py-1">{r.confidence ?? "—"}<br /><span className="text-[8.5px] text-slate-500">{HORIZON_LABEL(r.horizon)}</span></td>
              <td className="px-1.5 py-1">
                <p>{r.next_observable || "—"}</p>
                <p className="mt-0.5">
                  {r.sources.length ? <Sources ids={r.sources} idx={idx} label={false} /> : <NoDirect ctx={r.context_sources} idx={idx} />}
                </p>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[9.3px]">
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
          <p className="mt-0.5 text-[8px] text-slate-500">Absence of reporting is not evidence of inactivity.</p>
        </div>
        <div className="rounded border border-slate-300 p-1.5">
          <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">Coverage (60 days)</p>
          <p className="flex flex-wrap gap-0.5">
            {(b.coverage_summary?.priority ?? []).map((c) => (
              <span key={c.name} className={`rounded border px-1 text-[8px] ${COV_CHIP[c.status] ?? ""}`}>
                {c.name}{c.official_source ? "" : "*"}
              </span>
            ))}
          </p>
          <p className="mt-0.5 text-[8px] text-slate-500">* no official air force / MoD source in collection.</p>
        </div>
      </div>
      {p.collection_requirements.length > 0 && (
        <div className="mt-2">
          <p className="mb-1 border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">
            Regional collection requirements — gap → intelligence question → desired observable
          </p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[9.3px] leading-[1.3] text-slate-800">
            {p.collection_requirements.map((q) => (
              <div key={q.country} className="border-l-2 border-slate-400 pl-1.5">
                <p className="font-bold text-slate-900">
                  {q.country} <span className={`ml-1 rounded border px-1 text-[8px] font-semibold ${COV_CHIP[q.status] ?? "border-slate-400"}`}>{q.status}</span>
                  <span className="ml-1 text-[8.5px] font-normal text-slate-500">{q.gap}</span>
                </p>
                <p><b>Question:</b> {q.question}</p>
                <p><b>Desired observable:</b> {q.observable}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      <p className="mt-1.5 text-[8px] leading-tight text-slate-500">{p.note}</p>
    </PageFrame>
  );
}

function ItemCard({ it, idx }: { it: BriefItem; idx: SrcIndex }) {
  return (
    <article className="rounded border border-slate-300 px-1.5 py-1">
      <p className="flex items-baseline justify-between gap-1 text-[8.5px] text-slate-600">
        <span className="font-bold text-slate-900">{it.country}</span>
        <span className="shrink-0">{it.domain}</span>
      </p>
      <p className="text-[9.5px] font-semibold leading-snug text-slate-900">{it.what_changed}</p>
      {it.assessment && <p className="text-[9px] leading-[1.28] text-slate-800">{it.assessment}</p>}
      <p className="mt-0.5 flex flex-wrap items-center gap-1">
        <Meta>SIG {it.significance}/5</Meta><Meta>CONF {(it.confidence ?? "—").toUpperCase()}</Meta>
        <Meta>{HORIZON_LABEL(it.horizon)}</Meta><HuChip level={it.hu_relevance} />
        <span className="ml-auto">{it.sources.length ? <Sources ids={it.sources} idx={idx} label={false} /> : <NoDirect ctx={it.context_sources} idx={idx} />}</span>
      </p>
    </article>
  );
}

function Page3({ b, idx }: { b: CommandBriefV2; idx: SrcIndex }) {
  const { sections, maturity, change_table: ct } = b.page3;
  return (
    <PageFrame n={3} brief={b} title="Extended Air Power Picture"
               subtitle="Middle East · Africa · Wider NATO (material only) · capability maturity · what changed since last week">
      <div className="grid grid-cols-3 gap-2">
        {sections.map((s) => (
          <div key={s.key} className="flex min-h-0 flex-col gap-1">
            <p className="flex items-center justify-between border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">
              {s.title}
              {s.coverage && <span className={`rounded border px-1 text-[8px] font-semibold normal-case ${COV_CHIP[s.coverage] ?? ""}`}>coverage {s.coverage.toLowerCase()}</span>}
            </p>
            {s.items.length === 0 && <p className="py-1 text-center text-[9px] font-semibold text-slate-600">{s.empty}</p>}
            {s.items.map((it) => <ItemCard key={it.ref} it={it} idx={idx} />)}
          </div>
        ))}
      </div>
      <div className="mt-2">
        <p className="mb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">Capability change / maturity matrix</p>
        <table className="w-full table-fixed border-collapse text-[9px] text-slate-900">
          <colgroup><col style={{ width: "28%" }} /><col style={{ width: "12%" }} />
            {maturity.columns.map((c) => <col key={c} style={{ width: `${60 / maturity.columns.length}%` }} />)}</colgroup>
          <thead>
            <tr className="bg-slate-800 text-left text-[8.5px] uppercase tracking-wide text-white">
              <th className="px-1 py-0.5">Development</th><th className="px-1 py-0.5">HU</th>
              {maturity.columns.map((c) => <th key={c} className="px-1 py-0.5 text-center">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {maturity.rows.map((r) => {
              const at = r.column ? maturity.columns.indexOf(r.column) : -1;
              return (
                <tr key={r.ref} className="border-b border-slate-200">
                  <td className="px-1 py-0.5">{r.label} <span className="text-[8px] text-slate-500">({r.country})</span></td>
                  <td className="px-1 py-0.5"><HuChip level={r.hu_relevance} /></td>
                  {r.withdrawal ? (
                    <td colSpan={maturity.columns.length} className="px-1 py-0.5 text-center text-[8.5px] italic text-rose-700">
                      withdrawal — {r.stage} (outside the introduction chain)
                    </td>
                  ) : maturity.columns.map((c, i) => (
                    <td key={c} className="px-0.5 py-0.5 text-center">
                      {i < at && <span className="block h-1 rounded bg-slate-300" title="implied, not observed" />}
                      {i === at && <span className="inline-block rounded bg-slate-900 px-1 text-[8px] font-bold text-white">{r.stage}</span>}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="text-[8px] leading-tight text-slate-500">{maturity.caption}</p>
      </div>
      <div className="mt-2">
        <p className="mb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">
          Executive change table{ct.previous_week ? ` — against ${ct.previous_week} (published)` : ""}
        </p>
        <table className="w-full table-fixed border-collapse text-[9px] leading-[1.25] text-slate-900">
          <colgroup>
            <col style={{ width: "5%" }} /><col style={{ width: "12%" }} /><col style={{ width: "19%" }} />
            <col style={{ width: "15%" }} /><col style={{ width: "15%" }} /><col style={{ width: "18%" }} />
            <col style={{ width: "8%" }} /><col style={{ width: "8%" }} />
          </colgroup>
          <thead>
            <tr className="bg-slate-800 text-left text-[8.5px] uppercase tracking-wide text-white">
              <th className="px-1 py-0.5">Prio</th><th className="px-1 py-0.5">Country</th>
              <th className="px-1 py-0.5">Capability</th><th className="px-1 py-0.5">Previous</th>
              <th className="px-1 py-0.5">Current</th><th className="px-1 py-0.5">Delta</th>
              <th className="px-1 py-0.5">HU</th><th className="px-1 py-0.5">CONF</th>
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
                <td className="px-1 py-0.5">{r.country}</td>
                <td className="px-1 py-0.5">{r.capability}</td>
                <td className="px-1 py-0.5">{r.previous}</td>
                <td className="px-1 py-0.5">{r.current}</td>
                <td className="px-1 py-0.5">{r.delta}</td>
                <td className="px-1 py-0.5"><HuChip level={r.hu_relevance} /></td>
                <td className="px-1 py-0.5">{r.confidence ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(ct.overflow ?? 0) > 0 && <p className="text-[8px] text-slate-500">+{ct.overflow} further programme row(s) in the detailed weekly report.</p>}
      </div>
    </PageFrame>
  );
}

function Page4({ b, idx }: { b: CommandBriefV2; idx: SrcIndex }) {
  const p = b.page4;
  return (
    <PageFrame n={4} brief={b} title="Global Strategic Air Power Watch"
               subtitle="Indo-Pacific and other strategic movers · priority watch · gaps · outlook">
      <div className="grid h-full grid-cols-[50%_1fr] gap-3">
        <div className="flex min-h-0 flex-col gap-1.5">
          <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">Global strategic</p>
          {p.global.items.length === 0
            ? <p className="py-1 text-center text-[9.5px] font-semibold text-slate-600">{p.global.empty}</p>
            : <div className="grid grid-cols-2 gap-1.5">{p.global.items.map((it) => <ItemCard key={it.ref} it={it} idx={idx} />)}</div>}
          <div>
            <p className="mb-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-700">Global hotspots</p>
            <div className="cb-map mx-auto w-[88%] overflow-hidden rounded border border-slate-300"
                 dangerouslySetInnerHTML={{ __html: globalMapSvg(p.map_global) }} />
            <p className="mt-0.5 flex flex-wrap items-center gap-1 text-[8.5px] text-slate-600">
              SIG {[1, 2, 3, 4, 5].map((s) => (
                <span key={s} className="inline-flex items-center gap-0.5">
                  <span className="inline-block h-2 w-3 rounded-sm" style={{ background: SIG_FILL[s] }} />{s}
                </span>))}
              <span className="text-[8px] text-slate-500">— {p.map_global.caption}</span>
            </p>
          </div>
          <div className="text-[9.2px] leading-[1.3] text-slate-900">
            <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide">Outlook &amp; expected observables — next 7–30 days</p>
            <ul className="mt-0.5 space-y-0.5">
              {p.outlook.map((o, i) => (
                <li key={i}>• <b>{o.subject}</b> <span className="text-[8.5px] text-slate-500">({o.country})</span> — {o.expected_observable} <Sources ids={o.sources} idx={idx} label={false} /></li>
              ))}
            </ul>
            <p className="mt-0.5 text-[8px] text-slate-500">{p.outlook_note}</p>
          </div>
        </div>
        <div className="flex min-h-0 flex-col gap-2 text-[9.2px] leading-[1.3] text-slate-900">
          <div>
            <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide">Priority intelligence watch</p>
            {p.priority_watch.length === 0 && <p className="text-slate-600">No priority watch item this week.</p>}
            <ol className="mt-0.5 space-y-1">
              {p.priority_watch.map((w, i) => (
                <li key={i} className="border-l-2 border-slate-400 pl-1.5">
                  <p className="font-bold">{i + 1}. {w.question} {w.hu_relevance && <HuChip level={w.hu_relevance} />}</p>
                  <p><b>Why:</b> {w.why}</p>
                  <p><b>Next observable:</b> {w.next_observable} <span className="text-[8.5px] text-slate-500">({w.horizon ?? "—"} · impact {w.impact ?? "—"})</span></p>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <p className="border-b-2 border-slate-800 pb-0.5 text-[10px] font-bold uppercase tracking-wide">Intelligence gaps</p>
            <ul className="mt-0.5 space-y-0.5">
              {p.intelligence_gaps.map((g, i) => (
                <li key={i}>• {g.text}{g.origin === "coverage_audit" && <span className="text-[8px] text-slate-500"> (coverage audit)</span>}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </PageFrame>
  );
}

function Page5({ b }: { b: CommandBriefV2 }) {
  const p = b.page5;
  const m = b.meta;
  return (
    <PageFrame n={5} brief={b} title="Sources & Legend" flow
               subtitle="Evidence behind each judgement (official first, specialist media as corroboration) · permanent legend · document metadata">
      <p className="mb-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-900">{p.register_title ?? "Source register"}</p>
      <table className="w-full table-fixed border-collapse text-[8.6px] leading-[1.25] text-slate-900">
        <colgroup>
          <col style={{ width: "5%" }} /><col style={{ width: "15%" }} /><col style={{ width: "33%" }} />
          <col style={{ width: "8%" }} /><col style={{ width: "12%" }} /><col style={{ width: "8%" }} />
          <col style={{ width: "4%" }} /><col style={{ width: "5%" }} /><col style={{ width: "10%" }} />
        </colgroup>
        <thead>
          <tr className="bg-slate-800 text-left text-[8.2px] uppercase tracking-wide text-white">
            <th className="px-1 py-0.5">ID</th><th className="px-1 py-0.5">Source · tier</th><th className="px-1 py-0.5">Title (original language)</th>
            <th className="px-1 py-0.5">Published</th><th className="px-1 py-0.5">Role</th><th className="px-1 py-0.5">Country</th>
            <th className="px-1 py-0.5">Lang</th><th className="px-1 py-0.5">Lineage</th><th className="px-1 py-0.5">Used by</th>
          </tr>
        </thead>
        <tbody>
          {p.sources.map((s) => (
            <tr key={s.id} id={s.id} className={`border-b border-slate-200 align-top ${s.role.startsWith("Context") ? "text-slate-500" : ""}`}>
              <td className="px-1 py-0.5 font-mono font-bold">{s.id}</td>
              <td className="px-1 py-0.5">{s.source_name}<br /><span className="text-[7.8px] text-slate-500">{s.tier} · {s.source_type}</span></td>
              <td className="px-1 py-0.5">
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="cb-ref text-sky-800 hover:underline">{s.title}</a>
                {s.note && <span className="block text-[7.8px] text-slate-500">{s.note}</span>}
              </td>
              <td className="px-1 py-0.5">{s.published ?? "not recorded"}{s.published_basis && s.published_basis !== "feed" && <span className="block text-[7.5px] text-slate-500">({s.published_basis})</span>}</td>
              <td className="px-1 py-0.5">{s.role}</td>
              <td className="px-1 py-0.5">{s.country}</td>
              <td className="px-1 py-0.5">{s.language}</td>
              <td className="px-1 py-0.5 font-mono">{s.lineage}</td>
              <td className="px-1 py-0.5 text-[8px]">{s.used_by.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-0.5 text-[8px] leading-tight text-slate-500">{p.source_note}</p>
      <div className="mt-2 grid grid-cols-3 gap-x-3 gap-y-1.5 text-[8.6px] leading-[1.25] text-slate-800">
        {p.legend.map((sec) => (
          <div key={sec.title} className="cb-keep">
            <p className="border-b border-slate-400 text-[9px] font-bold uppercase tracking-wide text-slate-900">{sec.title}</p>
            {sec.items.map(([term, text]) => (
              <p key={term}><b>{term}</b> — {text}</p>
            ))}
          </div>
        ))}
      </div>
      <div className="cb-keep mt-1.5 grid grid-cols-[1fr_auto] gap-3 text-[8.6px] text-slate-800">
        <div>
          <p className="text-[9px] font-bold uppercase tracking-wide text-slate-900">Analytical discipline</p>
          {p.principles.map((x) => <p key={x}>• {x}</p>)}
        </div>
        <div className="text-[8.3px] text-slate-600">
          <p className="font-bold uppercase tracking-wide text-slate-900">Document</p>
          <p>Report week {m.week_label} · window {m.window_label}</p>
          <p>Generated {m.generated_utc} · methodology {m.methodology_version} · HU model {m.hu_model_version} · brief {m.brief_version}</p>
          {m.revision && <p>Revision {m.revision.number}: {m.revision.reason} ({m.revision.restated_utc})</p>}
        </div>
      </div>
    </PageFrame>
  );
}

export function sourceIndex(b: CommandBriefV2): SrcIndex {
  return new Map(b.page5.sources.map((s) => [s.id, { url: s.url, title: s.title, tier_rank: s.tier_rank }]));
}

export function CommandBrief({ brief }: { brief: CommandBriefV2 }) {
  const idx = sourceIndex(brief);
  return (
    <div className="cb" data-command-brief={brief.week_label}>
      <Page1 b={brief} idx={idx} />
      <Page2 b={brief} idx={idx} />
      <Page3 b={brief} idx={idx} />
      <Page4 b={brief} idx={idx} />
      <Page5 b={brief} />
    </div>
  );
}
