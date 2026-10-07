"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type TelegramLead } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";

export default function TelegramDelivery({ id }: { id: string }) {
  const [lead, setLead] = useState<TelegramLead | null>(null), [text, setText] = useState("");
  const [error, setError] = useState<Error | null>(null), [busy, setBusy] = useState(false), [now, setNow] = useState(Date.now());
  const [refresh, setRefresh] = useState(0);
  const sendKey = useRef<string | null>(null), sendingText = useRef<string | null>(null), inFlight = useRef(false);
  useEffect(() => {
    let cancelled = false, timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const value = await api.telegramLead(id);
        if (cancelled) return;
        setLead(value); setText(previous => previous || value.delivery.approved_text || value.analysis.suggested_reply || "");
        if (value.delivery.status === "sending" || value.delivery.draft_busy) timer = setTimeout(load, 3000);
      } catch (e) { if (!cancelled) setError(e as Error); }
    }
    void load(); const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => { cancelled = true; clearTimeout(timer); clearInterval(clock); };
  }, [id, refresh]);
  async function act(draft: boolean) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    if (!draft) { sendKey.current ??= crypto.randomUUID(); sendingText.current ??= text; }
    try {
      const value = draft ? await api.draftTelegramReply(id) : await api.sendTelegramReply(id, sendingText.current!, sendKey.current!);
      setLead(value);
      if (draft) setText(value.analysis.suggested_reply || text);
      else { sendKey.current = null; sendingText.current = null; }
    } catch (e) {
      setError(e as Error);
      if (e instanceof ApiError && e.status > 0) { sendKey.current = null; sendingText.current = null; }
      try { setLead(await api.telegramLead(id)); } catch { /* Preserve the initial safe error. */ }
    } finally { inFlight.current = false; setBusy(false); setRefresh(value => value + 1); }
  }
  const delivery = lead?.delivery, cooldown = delivery?.retry_after_at && new Date(delivery.retry_after_at).getTime() > now;
  const blocked = busy || !lead || delivery?.status === "sent" || delivery?.status === "sending" || delivery?.delivery_uncertain || delivery?.draft_busy;
  return <section className="card"><h2>Telegram reply</h2><ErrorMessage error={error}/>{delivery ? <>
    <p>Replying in {lead!.original_message.chat_title || lead!.original_message.chat_id} · message {lead!.original_message.message_id}{lead!.original_message.message_thread_id ? ` · topic ${lead!.original_message.message_thread_id}` : ""}</p>
    <p aria-live="polite">{({ not_sent: "Not sent", sending: "Sending / awaiting confirmation", sent: "Sent", failed: "Failed" })[delivery.status]}</p>
    {lead!.analysis.scoring?.decision === "REVIEW" && <p>This lead requires human review. A draft or score does not authorize sending.</p>}
    {delivery.failure_category && <p role="alert">Delivery failed: {delivery.failure_category}{delivery.failure_http_status ? ` (HTTP ${delivery.failure_http_status})` : ""}. Approved text is saved.</p>}
    {(delivery.delivery_uncertain || delivery.status === "sending") && <p>Delivery may already have happened. Verify in Telegram and contact support for reconciliation; resending is blocked.</p>}
    {cooldown && <p>Telegram rate limit: wait until {new Date(delivery.retry_after_at!).toLocaleTimeString()} before retrying.</p>}
    <label htmlFor="approved-reply">Review and approve reply text</label>
    <textarea id="approved-reply" dir="auto" rows={5} maxLength={4000} value={text} disabled={!!blocked || sendKey.current !== null} onChange={e => setText(e.target.value)}/>
    <p className="text-sm">Nothing is sent automatically. Send only after reviewing the recipient, context and text.</p>
    <div className="flex gap-3"><button type="button" disabled={!!blocked || sendKey.current !== null || lead?.analysis.scoring?.decision === "IGNORE"} onClick={() => void act(true)}>Generate draft</button>
    <button type="button" disabled={!!blocked || !!cooldown || !text.trim()} onClick={() => void act(false)}>{busy ? "Working…" : sendKey.current ? "Check / retry same request" : delivery.status === "failed" ? "Approve and retry send" : "Approve and send"}</button></div>
  </> : <p>Loading delivery status…</p>}</section>;
}
