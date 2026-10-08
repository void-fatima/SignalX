import Link from "next/link";
import type { Analysis, Run } from "@/lib/api";
import Icon from "@/components/Icon";
export default function RunSummary({ run, items, total, demo }: { run: Run | null; items: Analysis[]; total: number; demo: boolean }) {
  const mock = demo || (items.length > 0 && items.every(item => item.provider_mode === "mock"));
  return <section className="run-summary" aria-label="Current analysis run">
    <div className="inbox-heading"><div className="title-line"><h1>Opportunity inbox</h1><span className="count-pill">{String(total).padStart(2, "0")}</span></div>
      <p>{total} opportunities{demo ? " from your synthetic import." : " matching your run filters."}</p>
      <div className="run-meta"><Icon name="file"/><span title={run?.id}>RUN {demo ? "024" : run?.id.slice(0, 8) || "—"}</span><span className="meta-divider"/><span className="run-status"><span className="status-dot"/>{run?.status || "No run selected"}</span>{mock && <span className="badge">MOCK DATA</span>}{!mock && items.some(item => item.provider_mode === "real") && <span className="badge">REAL PROVIDER</span>}</div>
    </div>
    <div className="run-overview"><div className="run-actions"><span className="cost"><strong>{mock ? "$0.00" : "N/A"}</strong> {mock ? "mock cost" : "cost unavailable"}</span><Link className="button" href={demo ? "/imports?demo=1" : "/imports"}><Icon name="plus"/>New analysis</Link></div>
      <div className="run-metrics"><div><strong>{run?.processed_count ?? "—"}</strong><Icon name="chat"/><span>Messages analyzed</span></div><div><strong>{items.filter(item => item.decision === "respond").length}</strong><Icon name="respond"/><span>Ready to respond{demo ? "" : " · this page"}</span></div><div><strong>{items.filter(item => item.decision === "review").length}</strong><Icon name="review"/><span>Need review{demo ? "" : " · this page"}</span></div><span className="metric-rings" aria-hidden="true"/></div>
    </div>
  </section>;
}
