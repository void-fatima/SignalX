import type { Analysis, LeadDetail } from "@/lib/api";
import { demoMetadata } from "@/lib/demo-inbox";
import { textDirection } from "@/lib/lead-presentation";
import Icon from "@/components/Icon";
import Avatar from "./Avatar";
import DecisionBadge from "./DecisionBadge";
export default function LeadQueue({ items, details, selected, onSelect, demo, loading }: { items: Analysis[]; details: Record<string, LeadDetail>; selected: string; onSelect: (id: string) => void; demo: boolean; loading: boolean }) {
  const groups = ["respond", "review", "ignore", null] as const;
  return <div className="queue-items" aria-busy={loading}>
    {groups.map(decision => {
      const group = items.filter(item => item.decision === decision);
      if (!group.length) return null;
      return <section key={decision || "other"} aria-label={decision || "Unqualified results"}><div className="queue-group-title"><span>{decision === "respond" ? "Ready to respond" : decision === "review" ? "Needs review" : decision === "ignore" ? "Screened out" : "Other results"}</span><i/></div>
        {group.map(item => {
          const detail = details[item.id], author = detail?.message.author || "Source unavailable";
          const preview = detail?.message.content || item.reason;
          return <button type="button" key={item.id} className={`queue-row ${selected === item.id ? "is-selected" : ""}`} aria-pressed={selected === item.id} onClick={() => onSelect(item.id)}>
            <Avatar name={author} index={demo ? Number(item.id.split("-").at(-1)) - 1 : items.indexOf(item)}/>
            <span className="queue-row-content"><span className="queue-row-top"><strong><bdi>{author}</bdi></strong><b>{item.lead_score ?? "—"}</b><DecisionBadge analysis={item} compact/></span>
              <span className="queue-community">{demo ? demoMetadata[item.id]?.community : detail?.message.conversation_id || "Loading source…"}</span>
              <span className="queue-preview" dir={textDirection(preview)}>{preview}</span></span><Icon name="chevron" size={15}/>
          </button>;
        })}
      </section>;
    })}
    {!items.length && !loading && <p className="empty-inline">No opportunities match these filters.</p>}
  </div>;
}
