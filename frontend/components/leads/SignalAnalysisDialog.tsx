"use client";
import "@/app/dialog.css";
import type { LeadDetail } from "@/lib/api";
import { demoMetadata } from "@/lib/demo-inbox";
import { groundedEvidence, signalDescription } from "@/lib/lead-presentation";
import Dialog from "@/components/Dialog";
import { useMessageDirection } from "@/components/PreferencesProvider";
import Icon from "@/components/Icon";
import Avatar from "./Avatar";
import AnalysisFailure from "./AnalysisFailure";
import DecisionBadge from "./DecisionBadge";
import ProductSnapshot from "./ProductSnapshot";

export default function SignalAnalysisDialog({ detail, demo, open, onDismiss }: { detail: LeadDetail; demo: boolean; open: boolean; onDismiss: () => void }) {
  const direction = useMessageDirection();
  const { analysis, message } = detail;
  const metadata = demo ? demoMetadata[analysis.id] : undefined;
  const evidence = groundedEvidence(detail);
  const rows = [
    ["purchase_intent", "Purchase intent"], ["product_fit", "Product fit"], ["need_strength", "Need strength"],
    ["urgency", "Urgency"], ["confidence", "Confidence"], ["response_opportunity", "Response opportunity"],
  ] as const;
  if (analysis.status === "failed") return <Dialog open={open} onDismiss={onDismiss} title="Analysis failed" labelId="signal-dialog-title"><AnalysisFailure analysis={analysis}/><p dir="auto">{message.author}: {message.content}</p></Dialog>;
  const reference = demo && analysis.id === "demo-lead-1";
  return <Dialog open={open} onDismiss={onDismiss} title="Signal analysis" labelId="signal-dialog-title" footer={<footer className="dialog-footer"><Icon name="file" size={28}/><div className="dialog-footer-info"><strong>{metadata?.filename || `Batch ${message.batch_id.slice(0, 8)}`}</strong><span>Run {demo ? "024" : analysis.run_id.slice(0, 8)} · {analysis.provider_mode === "mock" ? "Mock data" : "Real provider"}</span></div><button type="button" className="button" onClick={onDismiss}><Icon name="arrow"/>Back to conversation</button></footer>}>
    <div className="dialog-meta"><Avatar name={message.author} small/><div className="dialog-source-meta"><strong><bdi>{message.author}</bdi></strong><span>·</span><span>{metadata?.community || message.conversation_id}</span><span>·</span><span>Message {message.external_id}</span><span className="badge">{analysis.provider_mode === "mock" ? "MOCK DATA" : "REAL PROVIDER"}</span></div></div>
    <div className="signal-overview"><div className="dialog-score"><span className="eyebrow">Signal score</span><div className="dialog-score-value"><strong>{analysis.lead_score ?? "—"}</strong><span>/100</span></div><div className="score-meter" aria-hidden="true">{Array.from({ length: 15 }, (_, index) => <span key={index}><i style={{ width: `${Math.max(0, Math.min(1, (analysis.lead_score ?? 0) / 100 * 15 - index)) * 100}%` }}/></span>)}</div></div>
      <div className="signal-reason"><div className={`dialog-decision ${analysis.decision === "review" ? "review" : ""}`}>{(analysis.decision === "respond" || analysis.decision === "review") && <Icon name={analysis.decision} size={46}/>}<DecisionBadge analysis={analysis}/></div><h3>{signalDescription(analysis)}</h3><p dir="auto">{analysis.reason}</p></div>
    </div>
    <section className="dialog-section" aria-labelledby="why-surfaced"><h3 id="why-surfaced">Why this surfaced</h3>{evidence.length ? <ol className="dialog-evidence">{evidence.map((item, index) => <li key={`${item.message_id}-${item.number}`}><span className="dialog-evidence-number">{String(item.number).padStart(2, "0")}</span><div><strong>{reference ? index === 0 ? "Explicit learning intent" : "Matches the product format" : `Evidence from message ${item.source.external_id}`}</strong><p>{reference ? index === 0 ? "Directly asks for a backend course." : "Prefers learning through real projects." : `Quoted from ${item.source.author} in this conversation.`}</p></div><blockquote dir={direction(item.quote)}><span>{item.quote}</span></blockquote></li>)}</ol> : <p className="muted">No grounded qualification evidence available for this message.</p>}
      {evidence.length < analysis.evidence.length && <p className="muted small">Some evidence could not be verified against the available source messages.</p>}
    </section>
    <section className="dialog-section" aria-labelledby="signal-breakdown"><h3 id="signal-breakdown">Signal breakdown</h3>{analysis.signals ? <div className="signal-breakdown">{rows.map(([key, label]) => {
      const value = analysis.signals![key];
      const valid = Number.isFinite(value) && value >= 0 && value <= 1;
      return <div className="breakdown-row" key={key}><span>{label}</span><div className="signal-track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={1} aria-valuenow={valid ? value : undefined} aria-valuetext={valid ? `${value} out of 1` : "Unavailable"}><span style={{ width: `${valid ? value * 100 : 0}%` }}/></div><span className="signal-value">{valid ? `${value.toFixed(2)} / 1` : "N/A"}</span></div>;
    })}</div> : <p className="muted">Signals are unavailable for this analysis.</p>}<p className="breakdown-caption">Normalized provider signals, shown without changing the deterministic score or decision. Based on the {detail.offline_context ? "imported" : "selected"} conversation.{analysis.provider_mode === "mock" ? " Synthetic mock output." : ""}</p></section>
    <section className="dialog-section"><ProductSnapshot snapshot={detail.product_snapshot}/></section>
  </Dialog>;
}
