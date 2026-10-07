import type { LeadDetail } from "@/lib/api";
import { signalDescription } from "@/lib/lead-presentation";
import Icon from "@/components/Icon";
import DecisionBadge from "./DecisionBadge";
export default function SignalCard({ detail, onOpen }: { detail: LeadDetail; onOpen?: () => void }) {
  const content = <><span className="signal-card-title"><Icon name="review" size={27}/><strong>Signal analysis</strong><Icon name="expand" size={17}/></span><span className="signal-card-score"><span><b>{detail.analysis.lead_score ?? "—"}</b><span>/100</span></span><DecisionBadge analysis={detail.analysis}/></span><span className="signal-card-bottom"><span>{signalDescription(detail.analysis)}</span><span className="evidence-link">View evidence <Icon name="chevron" size={14}/></span></span></>;
  return onOpen ? <button type="button" className="signal-card" onClick={onOpen} aria-haspopup="dialog" aria-label={`Open signal analysis for ${detail.message.author}`}>{content}</button> : <a className="signal-card" href="#selected-evidence">{content}</a>;
}
