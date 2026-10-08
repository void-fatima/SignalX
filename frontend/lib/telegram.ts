import { request, type Page } from "./api";

// Additive contract from feat/telegram-integration. Shared Mock-only AnalysisOut
// intentionally does not represent the Telegram AgentOutput snapshot.
export type TelegramMessage = {
  source: "telegram"; update_id: number; chat_id: number; message_id: number;
  chat_type: "group" | "supergroup"; chat_title: string | null; sender_id: number;
  sender_username: string | null; sender_display_name: string; text: string;
  timestamp: string; reply_to_message_id: number | null; message_thread_id: number | null;
};
export type TelegramEvidence = { message_id: string; quote: string; reason: string };
export type TelegramLead = {
  id: string; run_id: string; product_id: string; message_id: string; source: "telegram";
  original_message: TelegramMessage;
  context: { id: string; content: string; author: string; timestamp: string }[];
  analysis: {
    screening: { is_candidate: boolean; reason: string };
    qualification: null | {
      intent: string; need: string; purchase_intent: number; product_fit: number;
      need_strength: number; urgency: number; confidence: number; response_opportunity: number;
      evidence: TelegramEvidence[]; limitations: string[];
    };
    scoring: { score: number; decision: "RESPOND" | "REVIEW" | "IGNORE" } | null;
    decision_reason: string | null; suggested_reply: string | null;
    prompt_version: string | null; scoring_version: string | null;
    usage: { stage: string; attempt_no: number; provider_mode: "mock" | "real";
      model: string | null; input_tokens: number | null; output_tokens: number | null;
      estimated_cost: string | number | null; cost_status: "known" | "unknown" | "mock";
      price_version: string | null; latency_ms: number | null; outcome: string }[];
  };
  delivery: { status: "not_sent" | "sending" | "sent" | "failed";
    telegram_message_id: number | null; failure_category: string | null;
    delivery_uncertain: boolean; draft_busy: boolean };
};
const endpoint = "/api/v1"; // HttpOnly session → Bearer bridge stays on the server.
export const telegramApi = {
  leads: (offset = 0) => request<Page<TelegramLead>>(`/integrations/telegram/leads?limit=20&offset=${offset}`, {}, endpoint),
  lead: (id: string) => request<TelegramLead>(`/leads/${encodeURIComponent(id)}/telegram`, {}, endpoint),
  suggest: (id: string, regenerate: boolean) => request<TelegramLead>(`/leads/${encodeURIComponent(id)}/telegram/suggested-reply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ regenerate }) }, endpoint),
  reply: (id: string, text: string) => request<TelegramLead>(`/leads/${encodeURIComponent(id)}/telegram/reply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }, endpoint),
};
export function verifyTelegramLead(value: TelegramLead, id: string): TelegramLead {
  if (value.id !== id || value.source !== "telegram" || value.original_message.source !== "telegram") throw new Error("Telegram source does not match this opportunity.");
  return value;
}
