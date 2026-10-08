"use client";
import { useState } from "react";
import Icon, { type IconName } from "@/components/Icon";
import { useReviewSession, type FeedbackChoice, type ReviewFeedback } from "./ReviewSession";
const choices: { value: FeedbackChoice; label: string; icon: IconName }[] = [
  { value: "useful", label: "Useful", icon: "thumbs-up" }, { value: "needs_context", label: "Needs context", icon: "chat" }, { value: "off_topic", label: "Off-topic", icon: "ban" },
];
export default function ReplyFeedback({ id, demo }: { id: string; demo: boolean }) {
  const { feedback, setFeedback } = useReviewSession(), [notice, setNotice] = useState("");
  const value: ReviewFeedback = feedback[id] || { choice: demo ? "useful" : null, comment: demo ? "Keeps the reply relevant and asks a useful follow-up question." : "", saved: null };
  const saved = !!value.saved && value.saved.choice === value.choice && value.saved.comment === value.comment;
  function change(next: Partial<ReviewFeedback>) { setFeedback(previous => ({ ...previous, [id]: { ...value, ...next } })); setNotice(""); }
  function save() {
    if (!value.choice && !value.comment.trim()) { setNotice("Choose a feedback category or add a comment."); return; }
    change({ saved: { choice: value.choice, comment: value.comment } }); setNotice("Feedback saved for this session only. Not saved to the server.");
  }
  return <section className="reply-feedback" aria-labelledby="feedback-heading"><h2 id="feedback-heading">Your feedback <span>Optional</span></h2><div className="feedback-choices" role="group" aria-label="Feedback category">{choices.map(choice => <button type="button" aria-pressed={value.choice === choice.value} key={choice.value} onClick={() => change({ choice: value.choice === choice.value ? null : choice.value })}><Icon name={choice.icon} size={27}/>{choice.label}{value.choice === choice.value && <Icon name="check" size={18}/>}</button>)}</div><label htmlFor="feedback-comment">Comment <span>Optional</span></label><textarea id="feedback-comment" rows={3} maxLength={2000} value={value.comment} placeholder="Add context for your review…" onChange={e => change({ comment: e.target.value })}/><div className="feedback-save"><p role="status">{notice || (saved ? "Saved for this session only." : "Feedback stays in this session; it is not sent to the server.")}</p><button type="button" className="secondary-button" disabled={saved || (!value.choice && !value.comment.trim())} onClick={save}><Icon name="file"/>Save feedback</button></div></section>;
}
