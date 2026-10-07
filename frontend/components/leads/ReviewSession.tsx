"use client";
import { createContext, useContext, useState, type Dispatch, type SetStateAction } from "react";
import type { ReviewDraft } from "./ReplyComposer";
export type FeedbackChoice = "useful" | "needs_context" | "off_topic";
export type ReviewFeedback = { choice: FeedbackChoice | null; comment: string; saved: { choice: FeedbackChoice | null; comment: string } | null };
type Session = { drafts: Record<string, ReviewDraft>; setDrafts: Dispatch<SetStateAction<Record<string, ReviewDraft>>>; feedback: Record<string, ReviewFeedback>; setFeedback: Dispatch<SetStateAction<Record<string, ReviewFeedback>>> };
const ReviewContext = createContext<Session | null>(null);
/** Clear reviews on account changes without remounting pages or restarting their workflows. */
export function ReviewSessionProvider({ children, scope }: { children: React.ReactNode; scope: string }) {
  const [activeScope, setActiveScope] = useState(scope);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({}), [feedback, setFeedback] = useState<Record<string, ReviewFeedback>>({});
  // React retries this component before rendering children, so a different
  // account cannot see the previous account's drafts, even for one render.
  if (activeScope !== scope) { setActiveScope(scope); setDrafts({}); setFeedback({}); }
  return <ReviewContext.Provider value={{ drafts, setDrafts, feedback, setFeedback }}>{children}</ReviewContext.Provider>;
}
export function useReviewSession() {
  const value = useContext(ReviewContext);
  if (!value) throw new Error("Review session is required.");
  return value;
}
