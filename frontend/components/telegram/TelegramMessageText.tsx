import type { ReactNode } from "react";
import type { TelegramLead } from "@/lib/telegram";

/** Only mark an exact quote tied to this original internal message ID. */
export default function TelegramMessageText({ lead }: { lead: TelegramLead }) {
  const text = lead.original_message.text;
  const spans = (lead.analysis.qualification?.evidence || [])
    .filter(e => e.message_id === lead.message_id && e.quote && text.includes(e.quote))
    .map((e, index) => ({ start: text.indexOf(e.quote), end: text.indexOf(e.quote) + e.quote.length, index }))
    .sort((a, b) => a.start - b.start);
  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const span of spans) {
    if (span.start < cursor) continue;
    parts.push(text.slice(cursor, span.start));
    parts.push(<mark className="evidence-mark" key={span.index}>{text.slice(span.start, span.end)}</mark>);
    cursor = span.end;
  }
  parts.push(text.slice(cursor));
  return <>{parts}</>;
}
