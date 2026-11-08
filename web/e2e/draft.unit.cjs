/* Command Brief DRAFT model — unit tests (no browser, no database).
 *   node e2e/draft.unit.cjs [rows.json] [week]
 * Uses the real TypeScript modules (lib/briefDraft.ts, lib/presentation.ts)
 * through jiti. Exit code 1 on any failure. */
const path = require("path");
const crypto = require("crypto");
const jiti = require("jiti")(__filename, { alias: { "@": path.join(__dirname, "..", "src") }, interopDefault: true });
const D = jiti("../src/lib/briefDraft.ts");
const P = jiti("../src/lib/presentation.ts");

const rowsPath = process.argv[2] || path.join(__dirname, "fixture_rows.json");
const week = process.argv[3] || "2026-W46";
const rows = require(path.resolve(rowsPath));
const row = rows.find((r) => r.week_label === week);
const brief = row.payload.command_brief;
const original = JSON.stringify(brief);
const H = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
const T0 = "2026-11-11T08:00:00Z";
const fails = [];
const ok = (label, cond, extra = "") => {
  console.log(`  ${cond ? "ok  " : "FAIL"} ${label}${extra ? "  — " + extra : ""}`);
  if (!cond) fails.push(label);
};
const throws = (fn, rx) => { try { fn(); return false; } catch (e) { return e instanceof D.DraftError && (!rx || rx.test(e.message)); } };

const kj = brief.page1.primary[0];
const st0 = D.draftState(null, brief, H, T0);
console.log(`Draft model on ${week} (${brief.page1.primary.length} primary KJ, ${brief.page5.sources.length} sources)`);
ok("no stored draft -> GENERATED, revision 0", st0.draft.status === "GENERATED" && st0.draft.revision === 0);
const v0 = D.applyDraft(brief, null);
ok("generated view carries status GENERATED, not canonical", v0.meta.draft.status === "GENERATED" && !v0.meta.draft.canonical);
ok("template version on the view", v0.meta.template_version === P.TEMPLATE_VERSION);

// --- publication copy edit ---
const newA = "Poland has shifted its first FA-50 tranche into operational air-defence alert duty.";
const d1 = D.applyOps(st0, brief, [{ type: "set", block: "primary", key: kj.id, field: "assessment", value: newA }], "Analyst A", T0, H);
ok("edit -> EDITING, revision 1", d1.status === "EDITING" && d1.revision === 1);
const a1 = d1.audit.find((a) => a.action === "edit");
ok("audit: actor, timestamp, field, previous, new value",
   a1 && a1.actor === "Analyst A" && a1.at === T0 && a1.field === `primary/${kj.id}/assessment` && a1.previous === kj.assessment && a1.next === newA);
ok("audit: first edit logged as status change GENERATED -> EDITING",
   d1.audit.some((a) => a.action === "status" && a.previous === "GENERATED" && a.next === "EDITING"));
const v1 = D.applyDraft(brief, d1);
ok("published view shows the edited copy", v1.page1.primary[0].assessment === newA);
ok("original generated assessment unchanged (analytical truth untouched)", JSON.stringify(brief) === original);
ok("controlled metadata identical after edit",
   JSON.stringify([v1.page1.primary[0].sources, v1.page1.primary[0].hu_relevance, v1.page1.primary[0].significance, v1.page1.primary[0].confidence])
   === JSON.stringify([kj.sources, kj.hu_relevance, kj.significance, kj.confidence]));

// --- protected fields ---
const st1 = D.draftState(d1, brief, H, T0);
for (const f of ["sources", "hu_relevance.level", "significance", "confidence", "horizon", "refs"]) {
  ok(`controlled field '${f}' cannot be edited`, throws(() => D.applyOps(st1, brief, [{ type: "set", block: "primary", key: kj.id, field: f, value: "HIGH" }], "A", T0, H), /controlled/));
}
ok("source register cannot be edited", throws(() => D.applyOps(st1, brief, [{ type: "set", block: "source_register", key: "S-01", field: "published", value: "2026-01-01" }], "A", T0, H), /controlled/));
ok("source register items cannot be hidden", throws(() => D.applyOps(st1, brief, [{ type: "hide", block: "source_register", key: "S-01" }], "A", T0, H)));
ok("ellipsis rejected", throws(() => D.applyOps(st1, brief, [{ type: "set", block: "primary", key: kj.id, field: "assessment", value: "Cut short…" }], "A", T0, H), /ellipsis/));
ok("over hard length limit rejected", throws(() => D.applyOps(st1, brief, [{ type: "set", block: "primary", key: kj.id, field: "assessment", value: "x".repeat(600) }], "A", T0, H), /hard limit/));
ok("empty text rejected (hide instead)", throws(() => D.applyOps(st1, brief, [{ type: "set", block: "primary", key: kj.id, field: "assessment", value: "  " }], "A", T0, H)));
ok("change without actor rejected", throws(() => D.applyOps(st1, brief, [{ type: "set", block: "primary", key: kj.id, field: "what_changed", value: "x." }], "", T0, H), /actor/));

// --- hide / reorder / revert ---
const keys = brief.page1.secondary_watch.map((s) => s.id);
const d2 = D.applyOps(st1, brief, [
  { type: "hide", block: "secondary_watch", key: keys[0] },
  { type: "order", block: "outlook", keys: brief.page4.outlook.map((o) => o.subject).reverse() },
], "Analyst A", T0, H);
const v2 = D.applyDraft(brief, d2);
ok("hidden item not published", v2.page1.secondary_watch.length === keys.length - 1 && !v2.page1.secondary_watch.some((s) => s.id === keys[0]));
ok("reorder applied", v2.page4.outlook[0].subject === brief.page4.outlook.at(-1).subject);
ok("one save = one revision", d2.revision === 2);
ok("invalid order rejected", throws(() => D.applyOps(D.draftState(d2, brief, H, T0), brief, [{ type: "order", block: "outlook", keys: ["x"] }], "A", T0, H)));
const sec = brief.page3.sections.find((s) => s.items.length);
if (sec) {
  const d2b = D.applyOps(D.draftState(d2, brief, H, T0), brief, [{ type: "hide", block: "p3_items", key: sec.items[0].ref }], "A", T0, H);
  ok("nested list (page 3 sections) hide", D.applyDraft(brief, d2b).page3.sections.find((s) => s.key === sec.key).items.length === sec.items.length - 1);
}
const d3 = D.applyOps(D.draftState(d2, brief, H, T0), brief, [{ type: "revert", block: "primary", key: kj.id, field: "assessment" }], "Analyst B", T0, H);
ok("revert restores generated text", D.applyDraft(brief, d3).page1.primary[0].assessment === kj.assessment && d3.audit.at(-1).action === "revert");
const d3b = D.applyOps(D.draftState(d3, brief, H, T0), brief, [{ type: "set", block: "primary", key: kj.id, field: "what_changed", value: kj.what_changed }], "A", T0, H);
ok("setting the generated text again stores no override", d3b.revision === d3.revision);

// --- workflow ---
let st = D.draftState(d1, brief, H, T0);
ok("EDITING -> APPROVED directly is not allowed", throws(() => D.applyOps(st, brief, [{ type: "status", to: "APPROVED" }], "A", T0, H)));
ok("release without approval not allowed", throws(() => D.applyOps(st, brief, [{ type: "release" }], "A", T0, H), /APPROVED/));
const d4 = D.applyOps(st, brief, [{ type: "status", to: "READY_FOR_APPROVAL" }], "Analyst A", T0, H);
const d5 = D.applyOps(D.draftState(d4, brief, H, T0), brief, [{ type: "status", to: "APPROVED" }], "Duty officer", "2026-11-11T09:00:00Z", H);
ok("approval records approver and time", d5.status === "APPROVED" && d5.approval.by === "Duty officer" && d5.approval.at === "2026-11-11T09:00:00Z");
ok("APPROVED view is canonical", D.applyDraft(brief, d5).meta.draft.canonical === true);
const d5e = D.applyOps(D.draftState(d5, brief, H, T0), brief, [{ type: "set", block: "primary", key: kj.id, field: "what_changed", value: "Changed after approval." }], "Analyst A", T0, H);
ok("edit after approval -> EDITING, approval void", d5e.status === "EDITING" && d5e.approval === null);
const d6 = D.applyOps(D.draftState(d5, brief, H, T0), brief, [{ type: "release" }], "Duty officer", "2026-11-11T09:05:00Z", H);
const rel = d6.releases[0];
ok("release R-1 recorded", d6.status === "RELEASED" && rel.release_no === 1 && rel.approved_by === "Duty officer");
ok("release snapshot holds the published copy", rel.brief.page1.primary[0].assessment === newA);
ok("release content hash verifies", rel.content_hash === H(D.stableStringify(rel.brief)));
ok("release records template / methodology / HU model versions",
   rel.template_version === P.TEMPLATE_VERSION && rel.methodology_version === brief.meta.methodology_version && rel.hu_model_version === brief.meta.hu_model_version);
const pv = D.publishedView(brief, d6);
ok("public view = latest release", pv.kind === "release" && pv.brief.meta.draft.release_no === 1 && pv.brief.meta.draft.canonical);
const d7 = D.applyOps(D.draftState(d6, brief, H, T0), brief, [{ type: "set", block: "bottom_line", key: "#0", field: "text", value: "A new bottom line sentence." }], "Analyst A", T0, H);
ok("edit after release -> EDITING, release history kept", d7.status === "EDITING" && d7.releases.length === 1);
ok("public view keeps the release and flags the newer draft", D.publishedView(brief, d7).kind === "release" && D.publishedView(brief, d7).newerDraft);
ok("released snapshot unchanged by later edits", d7.releases[0].content_hash === rel.content_hash);

// --- regenerated base (restatement) ---
const regen = JSON.parse(original);
regen.page1.primary[0].assessment = "Regenerated assessment text.";
const stR = D.draftState(d5, regen, H, T0);
ok("regenerated base: edited field flagged stale", stR.stale.includes(`primary/${kj.id}/assessment`));
ok("regenerated base: approval invalidated", stR.approval_invalidated);
ok("release blocked after base change", throws(() => D.applyOps(stR, regen, [{ type: "release" }], "A", T0, H), /re-approve/));

// --- old briefs: context source semantics (S-13) ---
const old = JSON.parse(original);
for (const s of old.page5.sources) { delete s.evidence_role; if (s.role.startsWith("Context")) { s.used_by = ["KJ-05", "p.2 Poland"]; delete s.context_for; s.lineage = "L-10"; } }
const nb = D.normalizeBrief(old);
const ctx = nb.page5.sources.filter((s) => s.evidence_role === "CONTEXT_ONLY");
ok("old brief: context source moved to 'Context for', no evidence use, no lineage",
   ctx.length > 0 && ctx.every((s) => s.used_by.length === 0 && s.context_for.length > 0 && s.lineage === null));

// --- schema-driven editability ---
const copyKeys = P.allBlocks().flatMap(({ block }) => P.copyFields(block).map((f) => f.key));
ok("no protected metadata among editable fields", !copyKeys.some((k) => ["sources", "significance", "confidence", "lineage", "published", "hu_relevance.level", "evidence_role"].includes(k)));

console.log(fails.length ? `\n${fails.length} draft check(s) FAILED` : "\nAll draft model checks passed.");
process.exit(fails.length ? 1 : 0);
