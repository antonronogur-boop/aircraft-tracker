"use client";

/* Command Brief exportok. A PDF a bongeszo nyomtatasabol keszul (a nyomtatasi
 * CSS pontosan a 4 vezetoi oldalt + a Sources & Legend oldalt adja; a
 * dialogusban "Mentes PDF-kent"). A Word-fajl a szerverrol jon, ugyanabbol
 * az adatmodellbol. */
export function DownloadButtons({ week }: { week: string }) {
  return (
    <div className="flex items-center gap-2 print:hidden">
      <button
        onClick={() => window.print()}
        className="rounded border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-slate-100 hover:border-slate-400"
        title="Opens the print dialog — choose 'Save as PDF'. Produces the 4 executive pages + Sources & Legend, A4 landscape."
      >
        Download PDF
      </button>
      <a
        href={`/api/command-brief/${encodeURIComponent(week)}/docx`}
        className="rounded border border-sky-700 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 hover:border-sky-400"
        title="Editable Microsoft Word export generated from the same Command Brief data"
      >
        Download Word (.docx)
      </a>
    </div>
  );
}
