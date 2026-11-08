import { editorPayload } from "@/lib/editorData";
import { BriefEditorPage } from "@/components/BriefEditorPage";

export const dynamic = "force-dynamic";

/* /weekly/command-brief/edit — a legfrissebb het szerkesztoje. */
export default async function EditLatestCommandBrief() {
  return <BriefEditorPage data={await editorPayload("latest")} week="latest" />;
}
