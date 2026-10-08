"use client";
import { useEffect, useRef, useState } from "react";
import { useWorkspace } from "@/components/WorkspaceContext";
import { useWorkspaceProducts } from "@/components/useWorkspaceProducts";
import { useReviewSession } from "@/components/leads/ReviewSession";
import { ApiError } from "@/lib/api";
import { clearIntent, intentSlot, readIntent, saveIntent, type RecoveryIntent } from "@/lib/recovery-intent";
import { telegramApi, verifyTelegramLead, type TelegramLead } from "@/lib/telegram";

export function useTelegramReview(id: string) {
  const { user, demo } = useWorkspace(), scope = demo ? "demo" : user?.id || "guest";
  const { products, setSelectedProductId } = useWorkspaceProducts();
  const { telegramDrafts, setTelegramDrafts } = useReviewSession();
  const [snapshot, setSnapshot] = useState<{ lead: TelegramLead; scope: string } | null>(null), [error, setError] = useState("");
  const lead = snapshot?.scope === scope && snapshot.lead.id === id ? snapshot.lead : null;
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState<"generate" | "send" | null>(null), [actionError, setActionError] = useState("");
  const [intent, setIntent] = useState<RecoveryIntent | null>(null), [legacyBlocked, setLegacyBlocked] = useState(false), [now, setNow] = useState(Date.now());
  const slot = intentSlot("telegram", scope, id), legacySlot = `telegram-send:${scope}:${id}`;
  const identity = useRef({ id, scope }); identity.current = { id, scope };
  const alive = useRef(false), lock = useRef(false), loadVersion = useRef(0);
  function current() { return alive.current && identity.current.id === id && identity.current.scope === scope; }
  function setLead(value: TelegramLead) {
    setSnapshot({ lead: value, scope });
    if (value.delivery.status === "sent") { clearIntent(slot); setIntent(null); setLegacyBlocked(false); try { sessionStorage.removeItem(legacySlot); } catch { /* Sent is authoritative. */ } }
  }
  const draft = telegramDrafts[id] || { text: lead?.delivery.approved_text ?? lead?.analysis.suggested_reply ?? "", editingText: null };
  useEffect(() => { if (lead && products.some(product => product.id === lead.product_id)) setSelectedProductId(lead.product_id); }, [lead, products, setSelectedProductId]);
  async function refresh() {
    if (demo) { setError("Telegram actions require a connected workspace. Exit demo and sign in."); return; }
    const version = ++loadVersion.current;
    setLoading(true); setError("");
    try { const value = verifyTelegramLead(await telegramApi.lead(id), id); if (current() && version === loadVersion.current) setLead(value); }
    catch (reason) { if (current() && version === loadVersion.current) setError(reason instanceof Error ? reason.message : "Telegram source unavailable."); }
    finally { if (current() && version === loadVersion.current) setLoading(false); }
  }
  useEffect(() => {
    alive.current = true; setSnapshot(null); setBusy(null); setActionError(""); lock.current = false; setIntent(readIntent(slot));
    try { setLegacyBlocked(sessionStorage.getItem(legacySlot) === "blocked"); } catch { setLegacyBlocked(false); }
    if (demo) { setLoading(false); setError("Telegram actions require a connected workspace. Exit demo and sign in."); } else void refresh();
    return () => { alive.current = false; loadVersion.current++; };
  }, [id, scope, demo]);
  useEffect(() => {
    if (!lead || busy || (lead.delivery.status !== "sending" && !lead.delivery.draft_busy) || error) return;
    const timer = setTimeout(() => void refresh(), 3000); return () => clearTimeout(timer);
  }, [lead, busy, error]);
  const retryAt = lead?.delivery.retry_after_at;
  const cooldown = !!retryAt && (!Number.isFinite(Date.parse(retryAt)) || Date.parse(retryAt) > now);
  useEffect(() => { if (!cooldown) return; const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [cooldown]);
  function edit(text: string | null) { setTelegramDrafts(previous => ({ ...previous, [id]: { ...draft, editingText: text } })); }
  function save() { if (draft.editingText?.trim() && Array.from(draft.editingText).length <= 4000) setTelegramDrafts(previous => ({ ...previous, [id]: { text: draft.editingText!, editingText: null } })); }
  const definiteFailure = lead?.delivery.status === "failed" && lead.delivery.delivery_uncertain === false && ("failure_http_status" in lead.delivery || "approved_text" in lead.delivery);
  const blocked = demo || !user || !lead || !!error || loading || busy !== null || !!lead.delivery.draft_busy || lead.delivery.status === "sent" || lead.delivery.status === "sending" || !!lead.delivery.delivery_uncertain || legacyBlocked;
  const unavailable = blocked || !!intent || cooldown || (lead?.delivery.status === "failed" && !definiteFailure);
  const canCheck = !blocked && !!intent && typeof intent.text === "string" && (lead?.delivery.status === "not_sent" || definiteFailure);
  async function send(check = false) {
    if (lock.current || (check ? !canCheck : unavailable) || (!check && draft.editingText !== null)) return;
    const next = check ? intent! : { key: crypto.randomUUID(), text: draft.text };
    if (!next.text?.trim() || Array.from(next.text).length > 4000) return;
    lock.current = true; setBusy("send"); setActionError(""); ++loadVersion.current;
    try {
      // Persist approved bytes before dispatch; ambiguous outcomes reuse this key.
      saveIntent(slot, next); setIntent(next);
      const value = verifyTelegramLead(await telegramApi.reply(id, next.text, next.key), id);
      if (!current()) return;
      setLead(value); clearIntent(slot); setIntent(null);
      if (value.delivery.status !== "sent") await refresh();
    } catch (reason) {
      if (current()) { setActionError(reason instanceof Error ? reason.message : "Delivery could not be confirmed."); await refresh(); }
    } finally { if (current()) { setBusy(null); lock.current = false; } }
  }
  async function generate(regenerate: boolean) {
    if (lock.current || unavailable || draft.editingText !== null || !lead?.analysis.qualification || !lead.analysis.scoring || lead.analysis.scoring.decision === "IGNORE") return;
    lock.current = true; setBusy("generate"); setActionError(""); ++loadVersion.current;
    try {
      const value = verifyTelegramLead(await telegramApi.suggest(id, regenerate), id);
      if (!current()) return;
      setLead(value); setTelegramDrafts(previous => ({ ...previous, [id]: { text: value.analysis.suggested_reply || "", editingText: null } }));
      if (!value.analysis.suggested_reply?.trim()) setActionError("The provider returned no draft. Nothing was sent.");
    } catch (reason) {
      if (current()) { setActionError(reason instanceof Error ? reason.message : "Suggested reply generation failed. Nothing was sent."); if (!(reason instanceof ApiError) || reason.status >= 500 || reason.status === 409) await refresh(); }
    } finally { if (current()) { setBusy(null); lock.current = false; } }
  }
  const deliveryUnverified = legacyBlocked || (!!intent && !definiteFailure && lead?.delivery.status !== "sent");
  return { lead, draft, error, loading, busy, actionError, refresh, edit, save, generate, approve: () => send(), checkSend: () => send(true), unavailable, deliveryUnverified, definiteFailure, cooldown, canCheck, intent };
}
