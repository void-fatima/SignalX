import type { Analysis, LeadDetail, Run } from "./api";

/** Synthetic UI fixture only. Activated explicitly by ?demo=1, never on API failure. */
export const demoRun: Run = {
  id: "demo-run-024", product_id: "demo-product", batch_id: "demo-batch", status: "completed",
  total_count: 20, processed_count: 20, failed_count: 0, error: null, heartbeat_at: null,
  started_at: null, finished_at: null, created_at: "2026-10-07T08:00:00Z", config_snapshot: { provider_mode: "mock" },
};
const people = [
  ["Mina", "Developer community", "84", "respond", "دنبال یه دوره بک‌اند پروژه‌محور هستم.\nدوست دارم با ساختن یک پروژه واقعی یاد بگیرم."],
  ["Alex", "DevTalk", "79", "respond", "Looking for a hands-on backend course"],
  ["Leila", "CodeCafe", "76", "respond", "Want to build something real"],
  ["Amir", "Backend club", "71", "respond", "A course with practical projects?"],
  ["Navid", "Neshan Forum", "48", "review", "این دوره برای مبتدی‌ها مناسبه؟"],
  ["Hoda", "Programmers’ Guild", "43", "review", "هزینه دوره چقدر است؟"],
  ["Sara", "DevTalk", "46", "review", "Is there a sample lesson?"],
  ["Reza", "Backend club", "41", "review", "می‌خوام درباره دوره بیشتر بدونم."],
  ["Nika", "CodeCafe", "45", "review", "What experience do I need?"],
] as const;
export const demoMetadata: Record<string, { community: string; filename: string; reply: string }> = {};
export const demoDetails: Record<string, LeadDetail> = Object.fromEntries(people.map(([author, community, score, decision, content], index) => {
  const id = `demo-lead-${index + 1}`;
  const messageId = `demo-message-${index + 8}`;
  const analysis: Analysis = {
    id, run_id: demoRun.id, message_id: messageId, status: "completed", is_candidate: true,
    screening_reason: "Synthetic learning request", signals: index === 0 ? { purchase_intent: .9, product_fit: .9, need_strength: .8, urgency: .4, confidence: .9, response_opportunity: .9 } : { purchase_intent: decision === "respond" ? .8 : .4, product_fit: decision === "respond" ? .8 : .5, need_strength: .6, urgency: .3, confidence: .75, response_opportunity: .6 },
    intent: index === 0 ? "Project-based learning" : "Course inquiry", need: "Backend learning", budget_signal: null,
    lead_score: Number(score), decision, decision_reason: "Human review required before using a draft.",
    reason: index === 0 ? "A direct learning request that matches the course format." : "A synthetic course inquiry for demonstrating human review.",
    evidence: index === 0 ? [{ message_id: messageId, quote: "دوره بک‌اند" }, { message_id: messageId, quote: "پروژه واقعی" }] : [{ message_id: messageId, quote: content }],
    context_message_ids: [], limitations: ["Synthetic demonstration, not a measured AI result."], scoring_version: "demo_fixture", prompt_version: "demo_fixture", provider_mode: "mock",
  };
  demoMetadata[id] = { community, filename: "developer-community.csv", reply: index === 0 ? "سلام مینا! تا الان چقدر با بک‌اند کار کردی؟\nبیشتر دوست داری روی چه پروژه‌ای کار کنی؟" : `Hi ${author}, what would you like to build as you learn backend development?` };
  return [id, { analysis, message: { id: messageId, batch_id: demoRun.batch_id, external_id: String(index + 8).padStart(3, "0"), conversation_id: `demo-conversation-${index}`, author, content, timestamp: demoRun.created_at, reply_to_external_id: null }, context: [], product_snapshot: { name: "Backend Academy" }, offline_context: true } satisfies LeadDetail];
}));
export const demoAnalyses = Object.values(demoDetails).map(detail => detail.analysis);
