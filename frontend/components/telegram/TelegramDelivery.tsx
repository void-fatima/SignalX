import Link from "next/link";
import Icon from "@/components/Icon";
import type { useTelegramReview } from "./useTelegramReview";

export function deliveryLabel(review: ReturnType<typeof useTelegramReview>) {
  const delivery = review.lead?.delivery;
  if (review.busy === "send") return "Sending";
  if (delivery?.status === "sent") return "Sent";
  if (delivery?.delivery_uncertain || (review.deliveryUnverified && delivery?.status !== "sending")) return "Delivery uncertain";
  if (delivery?.status === "failed") return "Failed";
  if (delivery?.status === "sending") return "Sending";
  return "Not sent";
}
export default function TelegramDelivery({ review }: { review: ReturnType<typeof useTelegramReview> }) {
  const { lead, busy, loading, refresh, error, deliveryUnverified } = review;
  if (!lead) return null;
  const delivery = lead.delivery;
  const uncertain = delivery.delivery_uncertain || (deliveryUnverified && delivery.status !== "sent" && busy !== "send");
  return <div className={`telegram-delivery ${uncertain || delivery.status === "failed" ? "telegram-delivery-warning" : ""}`} aria-live="polite">
    {delivery.status === "sent" ? <p><Icon name="check"/>Sent{delivery.telegram_message_id !== null && <> · Delivered Telegram message {delivery.telegram_message_id}</>}. Original message {lead.original_message.message_id}.</p>
      : uncertain ? <p>Delivery could not be safely confirmed. Check the original Telegram thread and ask the backend operator to reconcile delivery before any further send. Sending is blocked.</p>
      : delivery.status === "sending" || busy === "send" ? <p>Delivery is in progress. Duplicate sending is blocked. Refresh to check the persisted status.</p>
      : delivery.status === "failed" ? <p>Delivery failed. {review.definiteFailure ? "The backend confirmed failure. Review the reply before an explicit retry." : "Check the original Telegram thread and contact the backend operator before another send."}</p>
      : <p>Not sent. Generating a draft or a Respond decision does not approve delivery.</p>}
    {review.cooldown && <p>Telegram rate limit: wait until {delivery.retry_after_at ? new Date(delivery.retry_after_at).toLocaleString() : "the cooldown ends"}. Nothing is resent automatically.</p>}
    {delivery.failure_category && <p>Failure category: <bdi>{delivery.failure_category}</bdi></p>}
    {delivery.draft_busy && <p>A draft operation is already active. Refresh its status; a stuck operation needs backend reconciliation.</p>}
    {error && <p>Authoritative delivery state is unavailable. Sending remains blocked.</p>}
    <button className="text-action" disabled={loading || busy !== null} onClick={() => void refresh()}><Icon name="refresh" size={16}/>{loading ? "Refreshing…" : "Refresh delivery status"}</button>
    {error && <Link href="/login">Sign in</Link>}
  </div>;
}
