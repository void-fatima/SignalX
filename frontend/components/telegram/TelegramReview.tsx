"use client";
import Link from "next/link";
import Icon from "@/components/Icon";
import { useTelegramReview } from "./useTelegramReview";
import TelegramComposer from "./TelegramComposer";
import TelegramBadge from "./TelegramBadge";
import TelegramSource, { TelegramDestination } from "./TelegramSource";
import "@/app/inbox.css";
import "@/app/workflow.css";
import "@/app/dialog.css";
import "@/app/leads/[id]/review.css";
import "./telegram.css";

export default function TelegramReview({ id }: { id: string }) {
  const review = useTelegramReview(id), { lead, error, loading, refresh } = review;
  return <div className="review-page telegram-review"><Link className="back-to-inbox" href="/leads?source=telegram"><Icon name="arrow" size={18}/>Back to inbox</Link><header className="review-title"><div><h1>Review Telegram lead</h1><TelegramBadge/></div><p>Check the evidence, refine your reply, then approve.</p></header>{loading && <p role="status">Loading Telegram opportunity…</p>}{error && <div className="workflow-error" role="alert"><p>{error}</p><button disabled={loading || review.busy !== null} onClick={() => void refresh()}>Refresh lead</button> <Link href="/login">Sign in</Link></div>}{lead?.id === id && <div className="review-grid"><TelegramSource key={id} lead={lead}/><div className="review-editor-column"><TelegramComposer review={review}/><TelegramDestination lead={lead}/></div></div>}</div>;
}
