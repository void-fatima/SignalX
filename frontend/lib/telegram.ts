import { request, type Page } from "./api";

import type { components } from "./generated/failure-api";
export type TelegramLead = components["schemas"]["TelegramLeadOut"];
export type TelegramMessage = components["schemas"]["TelegramMessage"];
export type TelegramEvidence = components["schemas"]["Evidence"];
// Use the same cookie-authenticated backend origin as products and sessions.
export const telegramApi = {
  leads: (offset = 0) => request<Page<TelegramLead>>(`/integrations/telegram/leads?limit=20&offset=${offset}`),
  lead: (id: string) => request<TelegramLead>(`/leads/${encodeURIComponent(id)}/telegram`),
  suggest: (id: string, regenerate: boolean) => request<TelegramLead>(`/leads/${encodeURIComponent(id)}/telegram/suggested-reply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ regenerate }) }),
  reply: (id: string, text: string, key: string) => request<TelegramLead>(`/leads/${encodeURIComponent(id)}/telegram/reply`, { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify({ text }) }),
};
export function verifyTelegramLead(value: TelegramLead, id: string): TelegramLead {
  if (value?.id !== id || value.source !== "telegram" || value.original_message?.source !== "telegram") throw new Error("Telegram source does not match this opportunity.");
  const delivery = value.delivery;
  if (!delivery || !["not_sent", "sending", "sent", "failed"].includes(delivery.status)
    || typeof delivery.delivery_uncertain !== "boolean" || typeof delivery.draft_busy !== "boolean"
    || (delivery.status === "sent" && delivery.delivery_uncertain)
    || (delivery.approved_text != null && typeof delivery.approved_text !== "string")) {
    throw new Error("Telegram delivery state could not be verified. Refresh status before any further send.");
  }
  return value;
}
