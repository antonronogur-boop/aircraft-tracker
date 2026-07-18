// Data layer — reads Supabase (ac_ tables) via REST with the public anon
// key. Server-side only (called from server components / route handlers).

const SUPA_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

const PAGE = 1000;
const MAX_PAGES = 20;

export async function fetchTable<T>(table: string, query = ""): Promise<T[]> {
  if (!SUPA_URL || !ANON_KEY) return [];
  const rows: T[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const sep = query ? "&" : "";
    const url = `${SUPA_URL}/rest/v1/${table}?${query}${sep}limit=${PAGE}&offset=${page * PAGE}`;
    const res = await fetch(url, {
      headers: { apikey: ANON_KEY, Authorization: `Bearer ${ANON_KEY}` },
      next: { revalidate: 120 },
    });
    if (!res.ok) break;
    const batch = (await res.json()) as T[];
    rows.push(...batch);
    if (batch.length < PAGE) break;
  }
  return rows;
}

// ---------------------------------------------------------------- types --

export interface AircraftType {
  type_id: string;
  name: string;
  designation: string | null;
  category: string;
  manufacturer: string | null;
  origin_country: string | null;
  role: string | null;
  first_flight_year: number | null;
  production_status: string | null;
  notes: string | null;
}

export interface Country {
  country_id: string;
  name: string;
  region: string | null;
}

export interface Fleet {
  fleet_id: number;
  country_id: string;
  type_id: string;
  fleet_status: string;
  quantity: number | null;
  variant: string | null;
  as_of: string | null;
  source_note: string | null;
}

export interface Article {
  article_id: string;
  source_id: string | null;
  title: string | null;
  url: string | null;
  publish_date: string | null;
  collected_date: string | null;
}

export interface FleetEvent {
  event_id: number;
  article_id: string | null;
  event_type: string;
  country_id: string | null;
  type_id: string | null;
  counterparty_country_id: string | null;
  quantity: number | null;
  value_usd_m: number | null;
  event_date: string | null;
  summary: string;
  confidence: number | null;
  review_status: string;
  unresolved_type_name: string | null;
  unresolved_country_name: string | null;
  created_at: string;
}

// ------------------------------------------------------------- loaders --

export interface Bundle {
  types: AircraftType[];
  countries: Country[];
  fleets: Fleet[];
  events: FleetEvent[];
  articles: Article[];
}

export async function loadBundle(): Promise<Bundle> {
  const [types, countries, fleets, events, articles] = await Promise.all([
    fetchTable<AircraftType>("ac_aircraft_types", "select=*"),
    fetchTable<Country>("ac_countries", "select=country_id,name,region"),
    fetchTable<Fleet>("ac_fleets", "select=*"),
    fetchTable<FleetEvent>("ac_events", "select=*&order=created_at.desc"),
    fetchTable<Article>("ac_articles",
      "select=article_id,source_id,title,url,publish_date,collected_date"),
  ]);
  return { types, countries, fleets, events, articles };
}

export function indexBy<T, K extends keyof T>(rows: T[], key: K): Map<T[K], T> {
  return new Map(rows.map((r) => [r[key], r]));
}

/** Approved events only — what the public pages show. */
export function approvedEvents(b: Bundle): FleetEvent[] {
  return b.events.filter((e) => e.review_status === "approved");
}

/** Approved + pending — used on the dashboard "latest signals" feed so new
 * extractions are visible immediately, marked with a pending badge. */
export function visibleEvents(b: Bundle): FleetEvent[] {
  return b.events.filter((e) => e.review_status !== "rejected");
}
