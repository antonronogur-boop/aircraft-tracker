"use client";

export function PrintButton() {
  return (
    <button
      onClick={() => window.print()}
      className="rounded border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-slate-500 print:hidden"
      title="Print or save as PDF (choose 'Save as PDF' in the print dialog)"
    >
      🖨 Print / PDF
    </button>
  );
}
