// A Command Brief ket terkepe SVG-STRINGKENT. Ugyanez a fuggveny rajzolja a
// webes/PDF nezetet (inline SVG) es a Word-export kepet (resvg -> PNG), igy a
// terkep a harom formatumban azonos. Nincs terkeptile, nincs futasideju
// terkepkonyvtar: az orszaghatarok elore vetitett Natural Earth utvonalak.
import { CEE, CEE_VIEWBOX } from "@/lib/geo/cee";
import { WORLD, WORLD_VIEWBOX } from "@/lib/geo/world";
import type { CeeMapData, GlobalMapData } from "@/lib/briefTypes";

export const HU_FILL: Record<string, string> = {
  HIGH: "#b91c1c", MEDIUM: "#ea580c", LOW: "#ca8a04", MINIMAL: "#94a3b8",
};
export const SIG_FILL = ["#e2e8f0", "#cbd5e1", "#93c5fd", "#3b82f6", "#1d4ed8", "#1e3a8a"];
const FONT = "DejaVu Sans, Arial, Helvetica, sans-serif";

const ORIENT = new Set(["aut", "svk", "cze", "pol", "ukr", "rou", "srb", "hrv", "svn", "bih",
  "blr", "rus", "bgr", "mda", "ltu", "lva", "est", "deu", "ita", "grc", "tur", "mne", "mkd",
  "alb", "xkx"]);

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function ceeMapSvg(map: CeeMapData): string {
  const hot = new Map(map.hotspots.map((h) => [h.country_id, h]));
  const gaps = new Set(map.collection_gaps);
  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${CEE_VIEWBOX}" width="600" height="470" role="img" aria-label="Central and Eastern Europe — hotspots by Hungary relevance" font-family="${FONT}">`);
  parts.push(`<rect x="0" y="0" width="600" height="470" fill="#dbe7f0"/>`);
  for (const [id, g] of Object.entries(CEE)) {
    const h = hot.get(id);
    const fill = id === map.home ? "#fef3c7" : h ? HU_FILL[h.level] ?? "#cbd5e1" : "#f4f4f2";
    const stroke = gaps.has(id) ? "#dc2626" : id === map.home ? "#92400e" : "#64748b";
    const sw = id === map.home ? 1.6 : gaps.has(id) ? 1.1 : 0.7;
    parts.push(`<path d="${g.d}" fill="${fill}" fill-opacity="${h ? 0.85 : 1}" stroke="${stroke}" stroke-width="${sw}"${gaps.has(id) ? ' stroke-dasharray="3 2"' : ""}/>`);
  }
  for (const [id, g] of Object.entries(CEE)) {
    const h = hot.get(id);
    const [x, y] = g.c;
    if (!h && id !== map.home) {
      if (ORIENT.has(id)) {
        parts.push(`<text x="${x}" y="${y}" text-anchor="middle" font-size="8.5" fill="#64748b">${id.toUpperCase()}</text>`);
      }
      continue;
    }
    const strong = id !== map.home && h && h.level !== "MINIMAL";
    parts.push(`<text x="${x}" y="${y}" text-anchor="middle" font-size="${id === map.home ? 11 : 10}" font-weight="700" fill="${strong ? "#ffffff" : "#1e293b"}">${id.toUpperCase()}</text>`);
    if (h) {
      parts.push(`<text x="${x}" y="${y + 11}" text-anchor="middle" font-size="8.5" font-weight="600" fill="${strong ? "#ffffff" : "#0f172a"}">HU ${esc(h.level)}</text>`);
    }
  }
  parts.push("</svg>");
  return parts.join("");
}

export function globalMapSvg(map: GlobalMapData): string {
  const hot = new Map(map.hotspots.map((h) => [h.country_id, h]));
  // A kozep-kelet-europai hotspotok a page-1 terkepen vannak: itt csak a
  // kitoltes marad, a cimket egy "Europe → p. 1" jelolo valtja ki.
  const europe = map.hotspots.filter((h) => CEE[h.country_id] && h.country_id !== "rus" && h.country_id !== "tur");
  const parts: string[] = [];
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="${WORLD_VIEWBOX}" width="800" height="410" role="img" aria-label="Global hotspots by air-power significance" font-family="${FONT}">`);
  parts.push(`<rect x="0" y="0" width="800" height="410" fill="#eef4f8"/>`);
  for (const [id, g] of Object.entries(WORLD)) {
    const h = hot.get(id);
    parts.push(`<path d="${g.d}" fill="${h ? SIG_FILL[h.significance] : "#f8fafc"}" stroke="#94a3b8" stroke-width="0.4"/>`);
  }
  const eu = WORLD["deu"];
  if (europe.length && eu) {
    parts.push(`<circle cx="${eu.c[0] + 8}" cy="${eu.c[1]}" r="14" fill="none" stroke="#0f172a" stroke-width="1" stroke-dasharray="2 2"/>`);
    parts.push(`<text x="${eu.c[0] - 34}" y="${eu.c[1] - 18}" font-size="9" font-weight="700" fill="#0f172a">EUROPE (${europe.length}) → p. 1 map</text>`);
  }
  for (const h of map.hotspots) {
    const g = WORLD[h.country_id];
    if (!g || europe.includes(h)) continue;
    const [x, y] = g.c;
    parts.push(`<circle cx="${x}" cy="${y}" r="${3 + h.significance}" fill="none" stroke="#0f172a" stroke-width="1"/>`);
    parts.push(`<text x="${x + 6 + h.significance}" y="${y + 3}" font-size="9" font-weight="700" fill="#0f172a">${h.country_id.toUpperCase()} · SIG ${h.significance}</text>`);
  }
  parts.push("</svg>");
  return parts.join("");
}
