import type { Analysis } from "@/lib/api";
import { decisionLabel } from "@/lib/lead-presentation";
import Icon from "@/components/Icon";
export default function DecisionBadge({ analysis, compact = false }: { analysis: Analysis; compact?: boolean }) {
  return <span className={`decision decision-${analysis.decision || "unknown"} ${compact ? "decision-compact" : ""}`}>
    {analysis.decision === "respond" || analysis.decision === "review" ? <Icon name={analysis.decision} size={compact ? 14 : 25}/> : <span className="status-dot"/>}{decisionLabel(analysis)}
  </span>;
}
