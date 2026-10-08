"use client";
import { useEffect, useRef, useState } from "react";
import { useWorkspace } from "@/components/WorkspaceContext";
import { useReviewSession } from "@/components/leads/ReviewSession";
import { telegramApi, verifyTelegramLead, type TelegramLead } from "@/lib/telegram";

export function useTelegramReview(id: string) {
  const { user, demo } = useWorkspace(), scope = demo ? "demo" : user?.id || "guest";
  const { telegramDrafts, setTelegramDrafts } = useReviewSession();
  const [lead, setLead] = useState<TelegramLead | null>(null), [error, setError] = useState("");
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState<"generate" | "send" | null>(null);
  const [actionError, setActionError] = useState("");
  const identity = useRef({ id, scope }); identity.current = { id, scope };
  const alive = useRef(false), lock = useRef(false), loadVersion = useRef(0);
  function current() { return alive.current && identity.current.id === id && identity.current.scope === scope; }
  const draft = telegramDrafts[id] || { text: lead?.analysis.suggested_reply || "", editingText: null };
  async function refresh() {
    const version = ++loadVersion.current;
    setLoading(true); setError("");
    try {
      const value = verifyTelegramLead(await telegramApi.lead(id), id);
      if (current() && version === loadVersion.current) setLead(value);
    } catch (reason) { if (current() && version === loadVersion.current) setError(reason instanceof Error ? reason.message : "Telegram source unavailable."); }
    finally { if (current() && version === loadVersion.current) setLoading(false); }
  }
  useEffect(() => {
    alive.current = true; setLead(null); setBusy(null); setActionError(""); lock.current = false;
    if (demo) { setLoading(false); setError("Telegram actions require a connected workspace. Exit demo and sign in."); }
    else void refresh();
    return () => { alive.current = false; loadVersion.current++; };
    // Scope changes invalidate outstanding responses without crossing accounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, scope, demo]);
  function edit(text: string | null) { setTelegramDrafts(previous => ({ ...previous, [id]: { ...draft, editingText: text } })); }
  function save() {
    if (!draft.editingText?.trim() || draft.editingText.length > 4000) return;
    setTelegramDrafts(previous => ({ ...previous, [id]: { ...draft, text: draft.editingText!, editingText: null } }));
  }
  const unavailable = demo || !lead || !!error || loading || busy !== null || lead.delivery.draft_busy || lead.delivery.status === "sending" || lead.delivery.status === "sent" || lead.delivery.delivery_uncertain || !!draft.sendBlocked;
  async function approve() {
    if (lock.current || unavailable || draft.editingText !== null || !draft.text.trim() || draft.text.length > 4000) return;
    const text = draft.text;
    lock.current = true; setBusy("send"); setActionError(""); ++loadVersion.current;
    setTelegramDrafts(previous => ({ ...previous, [id]: { ...draft, sendBlocked: true } }));
    try {
      const value = verifyTelegramLead(await telegramApi.reply(id, text), id);
      if (current()) setLead(value);
    } catch (reason) {
      if (current()) setActionError(reason instanceof Error ? reason.message : "Delivery could not be confirmed. Check the original Telegram thread.");
    } finally { if (current()) { setBusy(null); lock.current = false; } }
  }
  async function generate(regenerate: boolean) {
    if (lock.current || unavailable || draft.editingText !== null || !lead?.analysis.qualification || !lead.analysis.scoring || lead.analysis.scoring.decision === "IGNORE") return;
    lock.current = true; setBusy("generate"); setActionError(""); ++loadVersion.current;
    try {
      const value = verifyTelegramLead(await telegramApi.suggest(id, regenerate), id);
      if (!current()) return;
      setLead(value);
      setTelegramDrafts(previous => ({ ...previous, [id]: { text: value.analysis.suggested_reply || "", editingText: null } }));
      if (!value.analysis.suggested_reply?.trim()) setActionError("The provider returned no draft. Nothing was sent.");
    } catch (reason) {
      if (current()) { setActionError(reason instanceof Error ? reason.message : "Suggested reply generation failed. Nothing was sent."); await refresh(); }
    } finally { if (current()) { setBusy(null); lock.current = false; } }
  }
  return { lead, draft, error, loading, busy, actionError, refresh, edit, save, generate, approve, unavailable };
}
