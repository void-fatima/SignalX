import type { TelegramLead } from "@/lib/telegram";
export default function TelegramUsage({ lead }: { lead: TelegramLead }) {
  if (!lead.analysis.usage?.length) return null;
  return <aside className="telegram-usage" aria-label="Provider usage"><h3>Provider usage</h3>{(lead.analysis.usage || []).map((usage, index) => <p key={index}><span className="badge">{usage.provider_mode === "mock" ? "MOCK" : "REAL PROVIDER"}</span> {usage.stage} · Attempt {usage.attempt_no} · {usage.outcome}<br/>{usage.cost_status === "mock" ? "Mock cost: $0" : usage.cost_status === "known" && usage.estimated_cost !== null ? `Estimated cost: $${usage.estimated_cost}` : "Cost unavailable"}</p>)}</aside>;
}
