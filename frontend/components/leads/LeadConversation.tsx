import Link from "next/link";
import type { LeadDetail } from "@/lib/api";
import { demoMetadata } from "@/lib/demo-inbox";
import { groundedEvidence, textDirection } from "@/lib/lead-presentation";
import Icon from "@/components/Icon";
import Avatar from "./Avatar";
import EvidenceText from "./EvidenceText";
import SignalCard from "./SignalCard";
export default function LeadConversation({ detail, demo, previous, next, onAnalysis }: { detail: LeadDetail; demo: boolean; previous?: () => void; next?: () => void; onAnalysis?: () => void }) {
  const { analysis, message } = detail;
  const metadata = demo ? demoMetadata[analysis.id] : undefined;
  const evidence = groundedEvidence(detail);
  return <section className="conversation-panel" aria-label={`Selected opportunity from ${message.author}`}>
    <div className="conversation-top"><div className="conversation-main-header"><span className="eyebrow">Selected opportunity</span><div className="source-author"><Avatar name={message.author}/><div><h2><bdi>{message.author}</bdi></h2><span>{metadata?.community || message.conversation_id} <span className="meta-dot">·</span> Message {message.external_id}</span></div><div className="source-controls">{!demo && <Link href={`/leads/${analysis.id}`}>View source ↗</Link>}<button className="icon-button" type="button" disabled={!previous} aria-label="Previous opportunity" onClick={previous}><Icon name="chevron" style={{ transform: "rotate(180deg)" }}/></button><button className="icon-button" type="button" disabled={!next} aria-label="Next opportunity" onClick={next}><Icon name="chevron"/></button></div></div></div><SignalCard detail={detail} onOpen={onAnalysis}/></div>
    <div className="source-section"><div className="source-label"><span className="eyebrow">Source message</span><span className="badge">{analysis.provider_mode === "mock" ? "MOCK DATA" : "REAL PROVIDER"}</span></div><EvidenceText detail={detail}/>
      <span className="muted small">{demo ? "Translated intent" : "Analysis explanation"}</span><p dir="auto">{demo && analysis.id === "demo-lead-1" ? "Looking for a practical, project-based way to learn backend development." : analysis.reason}</p><div className="intent-tags">{analysis.intent && <span>{analysis.intent}</span>}{analysis.need && <span>{analysis.need}</span>}</div>
    </div>
    <div className="context-section"><span className="eyebrow">Conversation context</span><details><summary><Icon name="chat"/><span>{detail.context.length ? `${detail.context.length} source messages in this conversation` : "No additional context messages."}</span><span className="context-link">Open full conversation ↗</span></summary><p className="muted small">{detail.offline_context ? "Offline analysis: context may include later messages." : "Live conversation context."} Only this batch and conversation are shown.</p>{detail.context.filter(item => item.batch_id === message.batch_id && item.conversation_id === message.conversation_id).map(item => <div className="context-message" key={item.id}><strong><bdi>{item.author}</bdi></strong><time dateTime={item.timestamp}>{new Date(item.timestamp).toLocaleString()}</time><p dir={textDirection(item.content)}>{item.content}</p></div>)}</details></div>
    <details id="selected-evidence" className="source-diagnostics"><summary>Evidence, limitations & product snapshot</summary><div className="diagnostics-content"><h2>Evidence</h2>{evidence.length ? evidence.map(item => <p key={item.number} dir={textDirection(item.quote)}><bdi>{String(item.number).padStart(2, "0")}</bdi> · {item.quote}</p>) : <p>No grounded qualification evidence available.</p>}<p>Screening: {analysis.screening_reason}</p><p>Decision: {analysis.decision_reason || "Screening only"}</p><p>Scoring version: {analysis.scoring_version || "Not available"}</p><p>Cost: {analysis.provider_mode === "mock" ? "$0.00 · mock" : "Not available in the current data contract"}</p>{analysis.limitations.map((item, index) => <p key={index} dir="auto">{item}</p>)}<h2>Product snapshot</h2><pre dir="auto">{JSON.stringify(detail.product_snapshot, null, 2)}</pre></div></details>
  </section>;
}
