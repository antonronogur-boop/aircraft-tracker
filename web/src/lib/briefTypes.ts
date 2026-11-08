// A Command Brief v2 KANONIKUS adatmodellje (scripts/ac_command_brief.py).
// A web nezet, a PDF (bongeszo-nyomtatas) es a Word (.docx) export
// kizarolag ebbol renderel — igy a tartalom a harom formatumban azonos.

export interface HuView {
  level: string; score: number;
  factors: { label: string; points: number }[];
  rationale?: string;
}

export interface PrimaryKJ {
  id: string; origin: "report_key_judgement" | "executive_synthesis";
  statement: string; what_changed: string; assessment: string;
  why_hungary: string; why_hungary_origin?: string;
  next_observable: string; alternative_explanation: string;
  alternative_origin?: string;
  hu_relevance: HuView; significance: number; significance_label: string;
  confidence?: string; horizon?: string;
  sources: string[]; refs: string[]; countries?: string[];
  primary_reason?: string; headline?: string; edited_fields?: string[];
}

export interface SecondaryItem {
  id: string; line: string; countries: string[]; significance: number;
  hu_level?: string; confidence?: string; horizon?: string;
  sources: string[]; refs: string[];
}

export interface RegionalRow {
  ref: string; group: string; country: string;
  what_changed: string; effect: string;
  hu_relevance?: string; hu_why?: string; significance: number;
  significance_label?: string; confidence?: string; horizon?: string;
  next_observable?: string; coverage?: string; sources: string[];
}

export interface CollectionRequirement {
  country: string; status: string; gap: string; question: string; observable: string;
}

export interface BriefItem {
  ref: string; country: string; domain?: string; what_changed: string;
  assessment?: string; significance: number; significance_label?: string;
  confidence?: string; horizon?: string; hu_relevance?: string;
  sources: string[];
}

export interface SourceEntry {
  id: string; title: string; url: string; source_name: string;
  source_type: string; tier: string; language: string;
  publication_date?: string | null; event_date?: string | null;
  country: string; lineage: string; state_controlled: boolean;
  used_by: string[];
}

export interface CeeMapData {
  hotspots: { country_id: string; name: string; level: string; score: number;
              significance: number; refs: string[] }[];
  collection_gaps: string[]; home: string; caption?: string;
}

export interface GlobalMapData {
  hotspots: { country_id: string; name: string; significance: number; refs: string[] }[];
  caption?: string;
}

export interface CommandBriefV2 {
  schema: "command_brief_v2";
  week_label: string; title: string; classification: string; status_line: string;
  meta: {
    week_label: string; period_start?: string; period_end?: string;
    timezone?: string; window_label?: string; generated_utc?: string;
    methodology_version?: string; hu_model_version?: string;
    brief_version?: string; report_status?: string;
    revision?: { number: number; reason?: string; restated_utc?: string } | null;
  };
  micro_legend: string;
  page1: {
    bottom_line: { origin: string; note?: string;
                   sentences: { text: string; items: string[]; sources: string[] }[] };
    primary: PrimaryKJ[]; primary_empty?: string | null;
    secondary_watch: SecondaryItem[];
    map_cee: CeeMapData;
  };
  page2: {
    rows: RegionalRow[];
    no_material_change: { name: string; coverage: string }[];
    collection_gap: string[];
    collection_requirements: CollectionRequirement[];
    note?: string;
  };
  page3: {
    sections: { key: string; title: string; items: BriefItem[];
                coverage?: string | null; empty?: string | null }[];
    maturity: { columns: string[]; caption?: string;
                rows: { ref: string; label: string; country: string; stage: string;
                        column: string | null; withdrawal: boolean;
                        hu_relevance?: string; horizon?: string }[] };
    change_table: {
      previous_week?: string | null; note?: string; overflow?: number;
      rows: { priority: number; country: string; capability: string; previous?: string;
              current?: string; delta?: string; moved?: boolean; hu_relevance?: string;
              confidence?: string | null }[];
    };
  };
  page4: {
    global: { items: BriefItem[]; empty?: string | null };
    priority_watch: { question: string; why?: string; next_observable?: string;
                      horizon?: string; impact?: string; hu_relevance?: string }[];
    intelligence_gaps: { text: string; origin: string }[];
    outlook: { subject: string; country: string; expected_observable: string;
               hu_relevance?: string; sources: string[] }[];
    outlook_note?: string;
    map_global: GlobalMapData;
  };
  page5: {
    sources: SourceEntry[]; source_note?: string;
    legend: { title: string; items: [string, string][] }[];
    principles: string[];
  };
  coverage_summary?: {
    priority: { name: string; status: string; events_window: number; official_source: boolean }[];
    note?: string;
  };
  traceability?: {
    executive_synthesis_items: string[]; withheld_judgements_excluded: string[];
    sources_used?: string[];
  };
}

export const HORIZON_LABEL = (h?: string) =>
  !h || h === "unknown" ? "horizon unknown" : h;
