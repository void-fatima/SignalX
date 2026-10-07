import type { Analysis, LeadDetail } from "./api";

export function decisionLabel(analysis: Analysis) {
  return analysis.decision ? analysis.decision[0].toUpperCase() + analysis.decision.slice(1) : analysis.status === "failed" ? "Failed" : "Not analyzed";
}
export function textDirection(text: string): "rtl" | "ltr" {
  return /[\u0600-\u06ff]/u.test(text) ? "rtl" : "ltr";
}
/** Never highlight evidence from another conversation or a quote absent from its source. */
export function groundedEvidence(detail: LeadDetail) {
  const messages = [detail.message, ...detail.context];
  return detail.analysis.evidence.flatMap((evidence, index) => {
    const source = messages.find(message => message.id === evidence.message_id && message.batch_id === detail.message.batch_id && message.conversation_id === detail.message.conversation_id);
    return source && evidence.quote && source.content.includes(evidence.quote) ? [{ ...evidence, number: index + 1, source }] : [];
  });
}
export function signalDescription(analysis: Analysis) {
  if (analysis.status === "failed") return "Analysis unavailable";
  if (!analysis.signals) return "No qualified signals";
  return analysis.signals.product_fit >= .75 ? "Strong product fit" : analysis.signals.product_fit >= .5 ? "Potential product fit" : "Limited product fit";
}
export function filterLeads(items: Analysis[], decision: string, minScore: string, query: string, details: Record<string, LeadDetail>) {
  return items.filter(item => (!decision || item.decision === decision) && (!minScore || (item.lead_score !== null && item.lead_score >= Number(minScore))) && (!query.trim() || [item.reason, details[item.id]?.message.author, details[item.id]?.message.content, details[item.id]?.message.conversation_id].filter(Boolean).join(" ").toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
}
