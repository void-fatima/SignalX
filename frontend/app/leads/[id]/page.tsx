"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import TelegramReview from "@/components/telegram/TelegramReview";
import { useMessageDirection } from "@/components/PreferencesProvider";
import Icon from "@/components/Icon";
import Avatar from "@/components/leads/Avatar";
import EvidenceText from "@/components/leads/EvidenceText";
import SignalCard from "@/components/leads/SignalCard";
import SignalAnalysisDialog from "@/components/leads/SignalAnalysisDialog";
import ReplyComposer from "@/components/leads/ReplyComposer";
import ReplyFeedback from "@/components/leads/ReplyFeedback";
import { useLeadReview } from "@/components/leads/useLeadReview";
import { useReviewSession } from "@/components/leads/ReviewSession";
import { useWorkspaceProducts } from "@/components/useWorkspaceProducts";
import { demoMetadata } from "@/lib/demo-inbox";
import { readRunContext, type RunContext } from "@/lib/run-context";
import "@/app/inbox.css";
import "@/app/workflow.css";
import "./review.css";

export default function ReviewReply({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params), search = useSearchParams();
  return search.get("source") === "telegram" ? <TelegramReview key={id} id={id}/> : <CsvReview id={id}/>;
}
function CsvReview({ id }: { id: string }) {
  const direction = useMessageDirection();
  const { demo } = useWorkspaceProducts();
  const { detail, run, loading, error, runError, retry } = useLeadReview(id, demo);
  const { drafts, setDrafts } = useReviewSession();
  const [analysisOpen, setAnalysisOpen] = useState(false), [context, setContext] = useState<RunContext | null>(null);
  useEffect(() => { setAnalysisOpen(false); setContext(detail ? readRunContext(detail.analysis.run_id) : null); }, [detail]);
  const draft = drafts[id] || { text: demo ? demoMetadata[id]?.reply || "" : "", status: "draft" as const };
  const inbox = demo ? `/leads?demo=1&lead_id=${id}` : detail ? `/leads?run_id=${detail.analysis.run_id}&lead_id=${id}` : "/leads";
  return <div className="review-page"><Link className="back-to-inbox" href={inbox}><Icon name="arrow" size={18}/>Back to inbox</Link>
    <header className="review-title"><div><h1>Review suggested reply</h1>{detail && <span className="badge">{detail.analysis.provider_mode === "mock" ? "MOCK DATA" : "REAL PROVIDER"}</span>}</div><p>Keep the conversation in view while refining your response.</p></header>
    {loading && <p className="loading-state" role="status">Loading conversation and evidence…</p>}
    {error && <div className="workflow-error" role="alert"><p>{error}</p><button onClick={retry}>Retry opportunity</button> <Link href="/login">Sign in</Link></div>}
    {detail && <div className="review-grid"><section className="review-source" aria-label="Source conversation"><div className="review-identity"><Avatar name={detail.message.author}/><div><h2><bdi>{detail.message.author}</bdi></h2><p>{demo ? demoMetadata[id]?.community : context?.community || detail.message.conversation_id} · Message {detail.message.external_id}</p></div></div>
      <section className="review-original"><h3>Original message</h3><EvidenceText detail={detail}/></section>
      <section className="review-context"><h3>Conversation context</h3><p><Icon name="chat" size={24}/><span dir="auto">{demo && id === "demo-lead-1" ? "A request for practical, project-based backend learning." : detail.analysis.reason}</span></p>{detail.context.filter(m => m.batch_id === detail.message.batch_id && m.conversation_id === detail.message.conversation_id).map(m => <div className="context-message" key={m.id}><strong><bdi>{m.author}</bdi></strong><p dir={direction(m.content)}>{m.content}</p></div>)}</section>
      <SignalCard detail={detail} onOpen={() => setAnalysisOpen(true)}/>
      <footer className="review-source-footer"><Icon name="file" size={27}/><div><small>Source</small><strong>{demo ? demoMetadata[id]?.filename : context?.filename || `Batch ${detail.message.batch_id.slice(0, 8)}`} · Run {demo ? "024" : detail.analysis.run_id.slice(0, 8)}</strong></div><span className={`workflow-status ${run?.status === "partial" ? "amber" : ""}`}>{run?.status || "Status unavailable"}</span></footer>{runError && <p className="run-warning">Run status unavailable: {runError}</p>}
    </section><div className="review-editor-column"><ReplyComposer key={id} expanded demo={demo} draft={draft} onChange={value => setDrafts(previous => ({ ...previous, [id]: value }))} onGenerate={language => setDrafts(previous => ({ ...previous, [id]: { text: language === "fa" ? demoMetadata[id]?.reply || "" : `Hi ${detail.message.author}, how much backend experience do you have so far?\nWhat kind of project would you like to work on?`, status: "draft" } }))}/><ReplyFeedback key={id} id={id} demo={demo}/></div></div>}
    {detail && <SignalAnalysisDialog detail={detail} demo={demo} open={analysisOpen} onDismiss={() => setAnalysisOpen(false)}/>}
  </div>;
}
