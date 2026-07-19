import { fetchTable } from "@/lib/db";

interface PipelineRun {
  script_name: string;
  status: string;
  started_at: string;
  items_processed: number | null;
}

interface ComponentHealth {
  label: string;
  state: "ok" | "warn" | "error" | "unknown";
  detail: string;
}

const HOURS = 3600 * 1000;

function ageLabel(ms: number): string {
  const h = ms / HOURS;
  if (h < 1) return `${Math.round(h * 60)}m ago`;
  if (h < 48) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function assess(run: PipelineRun | undefined, warnH: number, errH: number, label: string): ComponentHealth {
  if (!run) return { label, state: "unknown", detail: "never ran" };
  const age = Date.now() - new Date(run.started_at).getTime();
  if (run.status === "error") return { label, state: "error", detail: `failed ${ageLabel(age)}` };
  if (run.status === "running" && age > 2 * HOURS)
    return { label, state: "warn", detail: `stuck since ${ageLabel(age)}` };
  if (age > errH * HOURS) return { label, state: "error", detail: `last run ${ageLabel(age)}` };
  if (age > warnH * HOURS) return { label, state: "warn", detail: `last run ${ageLabel(age)}` };
  const items = run.items_processed != null ? ` · ${run.items_processed} items` : "";
  return { label, state: "ok", detail: `${ageLabel(age)}${items}` };
}

const DOT: Record<ComponentHealth["state"], string> = {
  ok: "bg-emerald-400", warn: "bg-amber-400", error: "bg-rose-500", unknown: "bg-slate-600",
};

/** Compact pipeline-health strip. Reads the shared pipeline_runs log.
 * Thresholds: collection/processing run twice a day (warn >14h, error >36h);
 * the weekly report is Monday-only (warn >8d, error >15d). */
export async function SystemHealth() {
  const runs = await fetchTable<PipelineRun>(
    "pipeline_runs",
    "select=script_name,status,started_at,items_processed" +
    "&script_name=in.(ac_collect_rss,ac_process_articles,ac_weekly_report)" +
    "&order=started_at.desc&limit=30");

  const latest = (name: string) => runs.find((r) => r.script_name === name);
  const components = [
    assess(latest("ac_collect_rss"), 14, 36, "Collection"),
    assess(latest("ac_process_articles"), 14, 36, "AI processing"),
    assess(latest("ac_weekly_report"), 8 * 24, 15 * 24, "Weekly report"),
  ];
  const worst = components.some((c) => c.state === "error") ? "error"
    : components.some((c) => c.state === "warn" || c.state === "unknown") ? "warn" : "ok";

  return (
    <div className={`mb-6 flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-lg border px-4 py-2.5 text-xs ${
      worst === "ok" ? "border-slate-800 bg-slate-900/40"
        : worst === "warn" ? "border-amber-500/30 bg-amber-500/5"
        : "border-rose-500/40 bg-rose-500/5"}`}>
      <span className="font-semibold uppercase tracking-wide text-slate-500">System</span>
      {components.map((c) => (
        <span key={c.label} className="flex items-center gap-1.5">
          <span className={`inline-block h-2 w-2 rounded-full ${DOT[c.state]}`} />
          <span className="text-slate-300">{c.label}</span>
          <span className="text-slate-500">{c.detail}</span>
        </span>
      ))}
      {worst !== "ok" && (
        <span className="ml-auto text-slate-500">
          check GitHub → Actions if this persists
        </span>
      )}
    </div>
  );
}
