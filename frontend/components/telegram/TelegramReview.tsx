"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Icon from "@/components/Icon";
import { telegramApi, verifyTelegramLead, type TelegramLead } from "@/lib/telegram";
import TelegramBadge from "./TelegramBadge";
import TelegramSource, { TelegramDestination } from "./TelegramSource";
import "@/app/inbox.css";
import "@/app/workflow.css";
import "@/app/dialog.css";
import "@/app/leads/[id]/review.css";
import "./telegram.css";

export default function TelegramReview({ id }: { id: string }) {
  const [lead, setLead] = useState<TelegramLead | null>(null), [error, setError] = useState("");
  const [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLead(null); setError(""); setLoading(true);
    telegramApi.lead(id).then(value => { if (!cancelled) setLead(verifyTelegramLead(value, id)); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Telegram source unavailable."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, reload]);
  return <div className="review-page telegram-review"><Link className="back-to-inbox" href="/leads?source=telegram"><Icon name="arrow" size={18}/>Back to inbox</Link><header className="review-title"><div><h1>Review Telegram lead</h1><TelegramBadge/></div><p>Check the evidence, refine your reply, then approve.</p></header>{loading && <p role="status">Loading Telegram opportunity…</p>}{error && <div className="workflow-error" role="alert"><p>{error}</p><button onClick={() => setReload(value => value + 1)}>Refresh lead</button> <Link href="/login">Sign in</Link></div>}{lead?.id === id && <div className="review-grid"><TelegramSource key={id} lead={lead}/><div className="review-editor-column"><section className="telegram-reply"><h2>Suggested reply <span className="badge">DRAFT</span></h2><div className="telegram-reply-text" dir="auto">{lead.analysis.suggested_reply || "No suggested reply has been generated."}</div><p>Reply controls will be available with the draft workflow.</p></section><TelegramDestination lead={lead}/></div></div>}</div>;
}
