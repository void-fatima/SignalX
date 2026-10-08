"use client";
import { useEffect, useRef, useState } from "react";
import { api, type FeedbackOut } from "@/lib/api";

export default function PersistedFeedback({ id, initial, eligible }: { id: string; initial?: FeedbackOut | null; eligible: boolean }) {
  const [relevant, setRelevant] = useState<boolean | null>(initial?.relevant ?? null), [comment, setComment] = useState(initial?.comment || "");
  const [saved, setSaved] = useState(initial), [busy, setBusy] = useState(false), [notice, setNotice] = useState(""), [error, setError] = useState("");
  const lock = useRef(false), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const unchanged = !!saved && saved.relevant === relevant && (saved.comment || "") === comment;
  async function save() {
    if (lock.current || relevant === null || !eligible || unchanged) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try {
      const value = await api.feedback(id, { relevant, comment: comment || null });
      if (value.analysis_id !== id) throw new Error("Feedback does not match this opportunity.");
      if (alive.current) { setSaved(value); setRelevant(value.relevant); setComment(value.comment || ""); setNotice("Feedback saved to the server."); }
    } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "Feedback could not be saved."); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  return <section className="reply-feedback" aria-labelledby="feedback-heading"><h2 id="feedback-heading">Your feedback <span>Optional</span></h2>
    <fieldset disabled={busy || !eligible}><legend>Is this opportunity relevant?</legend><div className="feedback-choices" role="group" aria-label="Opportunity relevance">{[true, false].map(value => <button type="button" key={String(value)} aria-pressed={relevant === value} onClick={() => { setRelevant(value); setNotice(""); }}>{value ? "Relevant" : "Not relevant"}</button>)}</div>
    <label htmlFor="feedback-comment">Comment <span>Optional</span></label><textarea id="feedback-comment" maxLength={2000} rows={3} value={comment} onChange={event => { setComment(event.target.value); setNotice(""); }}/>
    <div className="feedback-save"><p role="status">{notice || (unchanged ? "Saved server feedback." : "Choose relevance explicitly. Changes are saved only when you submit.")}</p><button className="secondary-button" type="button" disabled={relevant === null || unchanged} onClick={() => void save()}>{busy ? "Saving…" : "Save feedback"}</button></div></fieldset>
    {!eligible && <p>Feedback requires a completed review or respond analysis.</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
