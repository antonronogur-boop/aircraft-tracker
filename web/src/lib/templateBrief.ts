// A Word TEMPLATE (.dotx) "ures" briefje: a presentation schema minden
// helyere kitoltesi utmutato kerul (mezonkent a hossz-szaballyal), a lista-
// blokkok a schema max_items szamu helyet kapjak. Ugyanaz a renderer
// (commandBriefDocx.ts) rajzolja, mint a heti exportot — igy a template es
// az export szerkezete (stilusok, sorrend, content-control cimkek) azonos.
import type { CommandBriefV2 } from "@/lib/briefTypes";
import { PRESENTATION, TEMPLATE_VERSION, block, type SchemaField } from "@/lib/presentation";

function ph(f: SchemaField | undefined, label?: string): string {
  if (!f) return `[${label ?? "text"}]`;
  const sent = f.max_sentences ? (f.max_sentences === 1 ? "1 sentence" : `1–${f.max_sentences} sentences`) : "";
  const chars = f.max_chars ? `max ${f.max_chars} characters` : "";
  return `[${label ?? f.label}${sent || chars ? " — " : ""}${[sent, chars].filter(Boolean).join(", ")}]`;
}

const field = (b: string, k: string) => block(b)?.fields?.find((f) => f.key === k);
const n = (b: string) => block(b)?.max_items ?? 1;
const range = (k: number) => Array.from({ length: k }, (_, i) => i);
const LEVEL = "[HIGH / MEDIUM / LOW / MINIMAL]";

export function templateBrief(): CommandBriefV2 {
  const doc = PRESENTATION.document;
  return {
    schema: "command_brief_v2",
    week_label: "[YYYY-Www]", title: doc.title, classification: doc.classification,
    status_line: doc.status_line,
    meta: {
      week_label: "[YYYY-Www]", period_start: "[Wed YYYY-MM-DD]", period_end: "[Tue YYYY-MM-DD]",
      timezone: "Europe/Budapest", window_label: "[Wednesday 00:00 → Tuesday 23:59:59, Europe/Budapest]",
      generated_utc: "[YYYY-MM-DD HH:MM UTC]", methodology_version: "[v3.x]", hu_model_version: "[hu-1.x]",
      brief_version: "v2", template_version: TEMPLATE_VERSION, report_status: "[status]", revision: null,
    },
    micro_legend: PRESENTATION.micro_legend,
    page1: {
      bottom_line: { origin: "template", sentences: range(n("bottom_line")).map((i) => ({
        text: ph(field("bottom_line", "text"), `Bottom line sentence ${i + 1}`), items: [], sources: ["[S-xx]"] })) },
      primary: range(n("primary")).map((i) => ({
        id: `[KJ-xx]`, origin: "report_key_judgement" as const,
        statement: ph(field("primary", "statement"), `Key judgement ${i + 1} — title`),
        what_changed: ph(field("primary", "what_changed")),
        assessment: ph(field("primary", "assessment")),
        why_hungary: ph(field("primary", "why_hungary")),
        next_observable: ph(field("primary", "next_observable"), "Next observable — ONE concrete indicator"),
        alternative_explanation: ph(field("primary", "alternative_explanation")),
        hu_relevance: { level: LEVEL, score: 0, factors: [] },
        significance: "[1–5]" as unknown as number, significance_label: "",
        confidence: "[low / moderate / high]", horizon: "[immediate / <12 months / 1–3 years / >3 years]",
        sources: ["[S-xx, official first — mandatory]"], refs: [],
      })),
      primary_empty: null,
      secondary_watch: range(n("secondary_watch")).map(() => ({
        id: "[ref]", line: ph(field("secondary_watch", "line")), countries: [],
        significance: "[1–5]" as unknown as number, hu_level: "[LOW / MINIMAL]", sources: ["[S-xx]"], refs: [],
      })),
      map_cee: { hotspots: [], collection_gaps: [], home: "hun", caption: ph(field("map_cee", "caption"), "Map caption") },
    },
    page2: {
      rows: range(n("regional_rows")).map(() => ({
        ref: "[D-xx]", group: "", country: "[Country]",
        what_changed: ph(field("regional_rows", "what_changed")), effect: ph(field("regional_rows", "effect")),
        hu_relevance: LEVEL, hu_why: ph(field("regional_rows", "hu_why"), "Why Hungary should care"),
        significance: "[1–5]" as unknown as number, confidence: "[conf]", horizon: "[horizon]",
        next_observable: ph(field("regional_rows", "next_observable")), coverage: "", sources: ["[S-xx]"],
      })),
      no_material_change: [{ name: "[countries with at least PARTIAL collection and nothing material]", coverage: "PARTIAL" }],
      collection_gap: ["[countries with no reporting in 60 days — a gap is NOT inactivity]"],
      collection_requirements: range(n("collection_requirements")).map(() => ({
        country: "[Country]", status: "[GAP / PARTIAL]", gap: "[what collection did not answer]",
        question: ph(field("collection_requirements", "question")), observable: ph(field("collection_requirements", "observable")),
      })),
      note: "Geography sets collection priority, not inclusion.",
    },
    page3: {
      sections: [
        { key: "extended", title: "[Region]", coverage: null, empty: null,
          items: range(n("p3_items")).map(() => ({
            ref: "[D-xx]", country: "[Country]", domain: "[domain]",
            what_changed: ph(field("p3_items", "what_changed")), assessment: ph(field("p3_items", "assessment")),
            significance: "[1–5]" as unknown as number, confidence: "[conf]", horizon: "[horizon]",
            hu_relevance: LEVEL, sources: ["[S-xx]"], context_sources: [],
          })) },
      ],
      maturity: { columns: PRESENTATION.maturity_columns, caption: ph(field("maturity_caption", "caption"), "Caption"),
                  rows: range(n("maturity")).map(() => ({ ref: "", label: ph(field("maturity", "label"), "Capability"),
                    country: "[Country]", stage: "[stage]", column: null, withdrawal: false, hu_relevance: "[HU]" })) },
      change_table: { previous_week: "[previous week]", note: "",
        rows: range(n("change_table")).map((i) => ({ priority: i + 1, country: "[Country]",
          capability: ph(field("change_table", "capability"), "Capability"), previous: "[previous]", current: "[current]",
          delta: ph(field("change_table", "delta"), "Change"), hu_relevance: "[HU]", confidence: "[conf]" })) },
    },
    page4: {
      global: { items: range(n("global_items")).map(() => ({
        ref: "[D-xx]", country: "[Country]", domain: "[domain]",
        what_changed: ph(field("global_items", "what_changed")), assessment: ph(field("global_items", "assessment")),
        significance: "[1–5]" as unknown as number, confidence: "[conf]", horizon: "[horizon]",
        hu_relevance: "[HU]", sources: ["[S-xx]"], context_sources: [] })) },
      priority_watch: range(n("priority_watch")).map(() => ({
        question: ph(field("priority_watch", "question"), "Watch item"), why: ph(field("priority_watch", "why")),
        next_observable: ph(field("priority_watch", "next_observable")), horizon: "[horizon]", impact: "[impact]", hu_relevance: LEVEL })),
      intelligence_gaps: range(n("intelligence_gaps")).map(() => ({ text: ph(field("intelligence_gaps", "text")), origin: "template" })),
      outlook: range(n("outlook")).map(() => ({ subject: ph(field("outlook", "subject"), "Subject"), country: "[Country]",
        expected_observable: ph(field("outlook", "expected_observable")), hu_relevance: "[HU]", sources: ["[S-xx]"] })),
      outlook_note: "Expected observables for the next 7–30 days.",
      map_global: { hotspots: [], caption: ph(field("map_global", "caption"), "Map caption") },
    },
    page5: {
      sources: range(10).map((i) => ({
        id: `S-${String(i + 1).padStart(2, "0")}`, title: "[Title in original language — insert as hyperlink to the publication]",
        url: "", source_name: "[Publisher]", source_type: "[type]", tier: "[Tier 1–3]", tier_rank: 9, language: "[lang]",
        published: "[publication date — never the event date]", published_basis: null, country: "[Country]",
        state_controlled: false, lineage: "[L-xx]", role: "[Primary (official) / Corroborating / Context only]",
        evidence_role: "EVIDENCE" as const, used_by: ["[KJ-xx, p.2 Country]"], context_for: [], supports: {},
      })),
      register_title: PRESENTATION.register.title, source_note: PRESENTATION.register.note,
      legend: PRESENTATION.legend, principles: PRESENTATION.principles,
    },
  } as unknown as CommandBriefV2;
}
