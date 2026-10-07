"use client";
import { useState } from "react";
import Icon from "@/components/Icon";
import { textDirection } from "@/lib/lead-presentation";
export type ReviewDraft = { text: string; status: "draft" | "approved" | "rejected" };
export default function ReplyComposer({ draft, onChange, demo }: { draft: ReviewDraft; onChange: (draft: ReviewDraft) => void; demo: boolean }) {
  const [editing, setEditing] = useState(!draft.text);
  const [notice, setNotice] = useState("");
  async function copy() {
    try { await navigator.clipboard.writeText(draft.text); setNotice("Draft copied."); }
    catch { setNotice("Clipboard unavailable. Use Edit to select and copy the text."); setEditing(true); }
  }
  return <section className="reply-panel" aria-labelledby="reply-heading"><div className="reply-heading"><h2 id="reply-heading">Suggested reply</h2><span className="badge">{draft.status.toUpperCase()}</span><span className="reply-language">{textDirection(draft.text) === "rtl" ? "فارسی" : "English"}</span></div><p className="muted small">Review the wording before approving. {demo ? "Mock draft." : "Write a draft to review."} Local review only; changes are not saved to the server.</p>
    <textarea aria-label="Reply draft" className="reply-text" dir={textDirection(draft.text)} value={draft.text} readOnly={!editing} placeholder="Write a reply for human review…" onChange={event => { onChange({ text: event.target.value, status: "draft" }); setNotice(""); }}/>
    <div className="reply-actions"><button type="button" className="secondary-button" onClick={() => setEditing(!editing)}><Icon name={editing ? "check" : "edit"}/>{editing ? "Done editing" : "Edit"}</button><button type="button" className="secondary-button" disabled={!draft.text.trim()} onClick={copy}><Icon name="copy"/>Copy</button><div className="reply-review"><button type="button" className="reject-button" disabled={!draft.text.trim() || draft.status === "rejected"} onClick={() => { onChange({ ...draft, status: "rejected" }); setNotice("Draft rejected locally."); }}>Reject</button><button type="button" disabled={!draft.text.trim() || draft.status === "approved"} onClick={() => { onChange({ ...draft, status: "approved" }); setEditing(false); setNotice("Draft approved locally for your review."); }}><Icon name="check"/>Approve draft</button></div></div><p className="reply-notice" role="status">{notice || "Nothing is sent automatically."}</p>
  </section>;
}
