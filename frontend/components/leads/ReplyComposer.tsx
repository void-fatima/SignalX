"use client";
import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import Link from "next/link";
import { textDirection } from "@/lib/lead-presentation";
export type ReviewDraft = { text: string; status: "draft" | "approved" | "rejected" };
export default function ReplyComposer({ draft, onChange, demo, expanded = false, onGenerate, reviewHref }: { draft: ReviewDraft; onChange: (draft: ReviewDraft) => void; demo: boolean; expanded?: boolean; onGenerate?: (language: "fa" | "en") => void; reviewHref?: string }) {
  const [editing, setEditing] = useState(!draft.text);
  const [notice, setNotice] = useState("");
  const [language, setLanguage] = useState<"fa" | "en">(textDirection(draft.text) === "rtl" ? "fa" : "en");
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (editing && expanded) textarea.current?.focus({ preventScroll: true }); }, [editing, expanded]);
  async function copy() {
    try { await navigator.clipboard.writeText(draft.text); setNotice("Draft copied."); }
    catch { setNotice("Clipboard unavailable. Use Edit to select and copy the text."); setEditing(true); }
  }
  return <section className={`reply-panel ${expanded ? "reply-expanded" : ""}`} aria-labelledby="reply-heading"><div className="reply-heading"><h2 id="reply-heading">Suggested reply</h2><span className="badge">{draft.status.toUpperCase()}</span>{expanded ? <select className="reply-language" aria-label="Reply language" value={language} onChange={e => { setLanguage(e.target.value as "fa" | "en"); setNotice("Language selected. Edit the text or restore a mock sample."); }}><option value="fa">فارسی</option><option value="en">English</option></select> : <span className="reply-language">{textDirection(draft.text) === "rtl" ? "فارسی" : "English"}</span>}{expanded && <button className="generate-reply" type="button" disabled={!demo || !onGenerate} title={demo ? "Restore a synthetic sample. No provider is called." : "Reply generation is not connected on this UI base."} onClick={() => { onGenerate?.(language); setEditing(false); setNotice("Mock sample restored locally. No provider was called."); }}><Icon name="refresh"/>Generate again</button>}</div><p className="muted small">Review the wording before approving. {demo ? "Mock draft." : "Write a draft to review."} Local review only; changes are not saved to the server.</p>
    <textarea ref={textarea} aria-label="Reply draft" className="reply-text" dir={expanded ? language === "fa" ? "rtl" : "ltr" : textDirection(draft.text)} value={draft.text} readOnly={!editing} placeholder="Write a reply for human review…" onChange={event => { onChange({ text: event.target.value, status: "draft" }); setNotice(""); }}/>
    {reviewHref && <Link className="reply-expand-link" href={reviewHref}><Icon name="expand" size={15}/>Open full reply review</Link>}
    <div className="reply-actions"><button type="button" className="secondary-button" onClick={() => setEditing(!editing)}><Icon name={editing ? "check" : "edit"}/>{editing ? "Done editing" : "Edit"}</button><button type="button" className="secondary-button" disabled={!draft.text.trim()} onClick={copy}><Icon name="copy"/>Copy</button><div className="reply-review"><button type="button" className="reject-button" disabled={!draft.text.trim() || draft.status === "rejected"} onClick={() => { onChange({ ...draft, status: "rejected" }); setNotice("Draft rejected locally."); }}>Reject</button><button type="button" disabled={!draft.text.trim() || draft.status === "approved"} onClick={() => { onChange({ ...draft, status: "approved" }); setEditing(false); setNotice("Draft approved locally for your review."); }}><Icon name="check"/>Approve draft</button></div></div><p className="reply-notice" role="status">{notice || "Nothing is sent automatically."}</p>
  </section>;
}
