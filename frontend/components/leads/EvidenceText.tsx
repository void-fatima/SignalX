"use client";
import type { LeadDetail } from "@/lib/api";
import { groundedEvidence } from "@/lib/lead-presentation";
import { useMessageDirection } from "@/components/PreferencesProvider";
export default function EvidenceText({ detail }: { detail: LeadDetail }) {
  const content = detail.message.content;
  const direction = useMessageDirection();
  const spans = groundedEvidence(detail).filter(e => e.message_id === detail.message.id).map(e => ({ ...e, start: content.indexOf(e.quote), end: content.indexOf(e.quote) + e.quote.length })).sort((a, b) => a.start - b.start);
  let cursor = 0;
  const parts: React.ReactNode[] = [];
  for (const span of spans) {
    if (span.start < cursor) continue;
    parts.push(content.slice(cursor, span.start));
    parts.push(<mark className="evidence-mark" key={span.number}><span className="evidence-number" aria-label={`Evidence ${span.number}`}>{String(span.number).padStart(2, "0")}</span>{span.quote}</mark>);
    cursor = span.end;
  }
  parts.push(content.slice(cursor));
  return <blockquote className="source-quote" dir={direction(content)}>{parts}</blockquote>;
}
