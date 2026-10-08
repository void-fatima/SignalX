import Link from "next/link";
import type { Analysis, LeadDetail } from "@/lib/api";
import { demoMetadata } from "@/lib/demo-inbox";
import Avatar from "@/components/leads/Avatar";
import Icon from "@/components/Icon";
import { Panel, TableScroll } from "./WorkflowUI";
const exampleMessages: Record<string, string> = { "demo-lead-1": "Project-based backend course", "demo-lead-2": "Looking for hands-on learning", "demo-lead-5": "Is this suitable for beginners?" };
export default function ArrivingResults({ items, details, total, demo, community, href, loading, error, retry }: {
  items: Analysis[]; details: Record<string, LeadDetail>; total: number; demo: boolean; community: string; href: string;
  loading: boolean; error: string; retry: () => void;
}) {
  return <Panel title="Results arriving" extra={<Link href={href}>View all <Icon name="chevron" size={15}/></Link>} className="arriving-results">
    {error && <div className="workflow-error" role="alert"><p>{error}</p><button className="workflow-secondary" onClick={retry}>Retry results</button></div>}
    {loading && <p className="workflow-empty" role="status">Loading available opportunities…</p>}
    <TableScroll label="Results arriving"><table><thead><tr>{["User", "Message", "Score", "Status", "Open"].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead><tbody>{items.map((item, i) => {
      const detail = details[item.id], author = detail?.message.author || "Source unavailable";
      const rowHref = demo ? `/leads?demo=1&lead_id=${item.id}` : `/leads/${item.id}`;
      return <tr key={item.id}><td><div className="workflow-person"><Avatar name={author} index={i === 2 ? 4 : i}/><div><strong>{author}</strong><small>{demo ? demoMetadata[item.id]?.community : community}</small></div></div></td><td className="arriving-message" dir="auto">{demo ? exampleMessages[item.id] : detail?.message.content || "Message details unavailable"}</td><td><b>{item.lead_score ?? "—"}</b></td><td><Link className={`result-decision ${item.decision === "respond" ? "respond" : "review"}`} href={rowHref}><Icon name={item.decision === "respond" ? "respond" : "review"} size={24}/>{item.decision === "respond" ? "Respond" : item.decision === "review" ? "Review" : "Inspect"}</Link></td><td><Link href={rowHref} aria-label={`Review ${author}'s result`}><Icon name="chevron" size={17}/></Link></td></tr>;
    })}</tbody></table></TableScroll>{!items.length && !loading && <p className="workflow-empty">No respond or review opportunities available yet.</p>}<p className="results-note">{demo ? "Synthetic examples · " : ""}Showing {items.length} of {total} opportunities. All drafts require human review.</p>
  </Panel>;
}
