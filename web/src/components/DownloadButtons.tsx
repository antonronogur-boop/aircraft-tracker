"use client";

/* Command Brief exportok. A PDF a bongeszo nyomtatasabol keszul (a nyomtatasi
 * CSS pontosan a 4 vezetoi oldalt + a Sources & Legend oldalt adja; a
 * dialogusban "Mentes PDF-kent"). Kanonikus PDF csak APPROVED / RELEASED
 * allapotbol; mas allapotban a nyomat minden oldalon "WORKING COPY — NOT
 * APPROVED" jelolest visel. A Word-fajl mindig munkapeldany. */
export function DownloadButtons({ week, canonical = true, query = "" }: {
  week: string; canonical?: boolean; query?: string;
}) {
  return (
    <div className="flex items-center gap-2 print:hidden">
      <button
        onClick={() => window.print()}
        data-canonical={canonical ? "1" : "0"}
        className={`rounded border px-3 py-1.5 text-xs ${canonical
          ? "border-slate-600 bg-slate-800 text-slate-100 hover:border-slate-400"
          : "border-amber-700 bg-amber-500/10 text-amber-200 hover:border-amber-500"}`}
        title={canonical
          ? "Opens the print dialog — choose 'Save as PDF'. Canonical product: 4 executive pages + Sources & Legend, A4 landscape."
          : "Not approved: the print is marked WORKING COPY on every page. Approve and release the draft for the canonical PDF."}
      >
        {canonical ? "Download PDF" : "Print working copy (not approved)"}
      </button>
      <a
        href={`/api/command-brief/${encodeURIComponent(week)}/docx${query}`}
        className="rounded border border-sky-700 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 hover:border-sky-400"
        title="Editable Microsoft Word working copy, generated from the same Command Brief data (not the canonical product)"
      >
        Download Word (.docx)
      </a>
    </div>
  );
}
