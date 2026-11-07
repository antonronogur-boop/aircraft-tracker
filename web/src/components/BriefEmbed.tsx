import { CommandBrief } from "@/components/CommandBrief";
import type { ReportPayload } from "@/components/WeeklyReportView";

/* A teljes heti jelentes ELSO 4 OLDALA: a Command Brief, utana valaszto, majd
 * a reszletes jelentes (Part II). Nyomtatasban: 4 fekvo oldal, aztan a
 * reszletes jelentes allo oldalakon. A hivatkozasok ugyanazon az oldalon
 * levo horgonyokra mutatnak (#D-03, #KJ-01). */
export function BriefEmbed({ payload }: { payload: ReportPayload }) {
  if (!payload?.command_brief) return null;
  return (
    <>
      <CommandBrief brief={payload.command_brief} detailBase="" />
      <div className="mb-6 mt-2 border-t border-slate-700 pt-3 print:mt-0 print:border-0 print:pt-0">
        <p className="text-center text-[11px] font-semibold uppercase tracking-[0.25em] text-slate-500">
          Part II — Detailed assessment
        </p>
        <p className="text-center text-[11px] text-slate-600">
          The reference product. Every Command Brief item above cites a development (D-xx) or key judgement (KJ-xx) below.
        </p>
      </div>
    </>
  );
}
