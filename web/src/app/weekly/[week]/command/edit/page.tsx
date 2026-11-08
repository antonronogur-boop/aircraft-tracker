import { editorPayload } from "@/lib/editorData";
import { BriefEditorPage } from "@/components/BriefEditorPage";

export const dynamic = "force-dynamic";

/* /weekly/2026-W46/command/edit — strukturalt Command Brief szerkeszto. */
export default async function EditWeekCommandBrief({ params }: { params: { week: string } }) {
  return <BriefEditorPage data={await editorPayload(params.week)} week={params.week} />;
}
