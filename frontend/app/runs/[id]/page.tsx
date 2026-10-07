"use client";
import { use, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import Icon from "@/components/Icon";
import { useWorkspaceProducts } from "@/components/useWorkspaceProducts";
import { useRunProgress, terminalStatuses } from "@/components/workflow/useRunProgress";
import { useRunResults } from "@/components/workflow/useRunResults";
import ArrivingResults from "@/components/workflow/ArrivingResults";
import { DemoNotice, PageHeading, Panel, WorkflowLink } from "@/components/workflow/WorkflowUI";
import { readRunContext, type RunContext } from "@/lib/run-context";
import "@/app/workflow.css";
import "./progress.css";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params), search = useSearchParams(), router = useRouter();
  const workspace = useWorkspaceProducts(), { demo } = workspace;
  const { run, error, loading, updated, retry } = useRunProgress(id, demo, search.get("state"));
  const [resultsRefresh, setResultsRefresh] = useState(0);
  const results = useRunResults(id, run?.batch_id, run?.processed_count || 0, demo, resultsRefresh);
  const [context, setContext] = useState<RunContext | null>(null), [issuesOpen, setIssuesOpen] = useState(false);
  useEffect(() => { setContext(readRunContext(id)); setIssuesOpen(false); }, [id, demo]);
  const completed = !!run && terminalStatuses.includes(run.status);
  const processed = run?.processed_count || 0, total = run?.total_count || 0, failed = run?.failed_count || 0;
  const ready = Math.max(0, processed - failed), remaining = Math.max(0, total - processed);
  const percent = total ? Math.min(100, Math.round(processed / total * 100)) : 0;
  const mock = run?.config_snapshot.provider_mode === "mock";
  const sourcePreview = demo && id === "demo-import";
  const label = demo && /^demo-run-\d+$/.test(id) ? `Run ${id.slice(-3)}` : sourcePreview ? "File preview" : `Run ${id.slice(0, 8)}`;
  const status = run?.status === "running" ? "Analyzing" : run?.status === "partial" ? "Partial completion" : run?.status === "completed" ? "Completed" : run?.status || "Loading";
  const title = sourcePreview ? "Analysis preview" : run?.status === "completed" ? "Analysis complete" : run?.status === "partial" ? "Analysis partially complete" : run?.status === "failed" || run?.status === "interrupted" ? "Analysis needs attention" : "Analysis in progress";
  const leadsHref = demo ? "/leads?demo=1" : `/leads?run_id=${id}`;
  return <div className="workflow-page analysis-page"><PageHeading title={title}><p>Following the conversations that matter.</p></PageHeading>
    {demo && <DemoNotice>{sourcePreview ? "Validated file preview · no import or AI job started. Counts remain static." : "Synthetic run snapshot · automatic updates are off. No AI job is running."}</DemoNotice>}
    {error && <div className="workflow-error" role="alert"><p>{error}</p><button onClick={retry} className="workflow-secondary">Retry connection</button> <Link href="/login">Sign in</Link></div>}
    {loading && <p role="status" className="workflow-empty">Loading run status…</p>}
    {run && <div className="analysis-grid"><Panel title={label} className="progress-panel" extra={<span className={`run-state ${completed ? "terminal" : ""}`}>{status}</span>}>
      <div className="progress-heading" aria-live="polite"><h2>{processed} of {total} messages processed</h2><strong>{percent}<small>%</small></strong></div>
      <div className="analysis-progress" role="progressbar" aria-label="Messages processed" aria-valuemin={0} aria-valuemax={total || 1} aria-valuenow={processed} aria-valuetext={`${processed} of ${total} messages processed`}><span style={{ width: `${percent}%` }}/></div>
      <div className="progress-markers" aria-hidden="true">{[0, 25, 50, 75, 100].map(p => <span key={p}>{p}%</span>)}</div>
      <ol className="analysis-stages" aria-label="Analysis stages"><li className="done"><span><Icon name="check" size={20}/></span><div><strong>{sourcePreview ? "File selected" : "Imported"}</strong><small>{total} messages</small></div></li><li className={completed ? "done" : run.status === "running" ? "current" : ""} aria-current={run.status === "running" ? "step" : undefined}><span>{completed ? <Icon name="check" size={17}/> : <i/>}</span><div><strong>Analyzing</strong><small>{demo ? "Static preview" : run.status === "queued" ? "Waiting for worker" : "Processing messages"}</small></div></li><li className={completed && ready ? "done" : ""} aria-current={completed ? "step" : undefined}><span>{completed && ready ? <Icon name="check" size={17}/> : null}</span><div><strong>Ready for review</strong><small>{completed ? "Available results below" : "Results will be available soon"}</small></div></li></ol>
      <div className="progress-counts"><div><Icon name="file" size={25}/><div><b>{ready}</b><span>results ready</span></div></div><div><Icon name="info" size={25}/><div><b>{failed}</b><span>failed</span></div></div><div><Icon name="review" size={25}/><div><b>{remaining}</b><span>remaining</span></div></div></div>
      {(failed > 0 || run.error) && <div className="workflow-warning"><Icon name="review" size={25}/><div><strong>{failed ? `${failed} messages could not be analyzed.` : "This run needs attention."}</strong><p>{completed ? "Successful results remain available for review." : "Other results remain available while the run continues."}</p></div><button className="text-action" onClick={() => setIssuesOpen(!issuesOpen)} aria-expanded={issuesOpen} aria-controls="run-issues">View issues <Icon name="chevron" size={16}/></button></div>}
      {issuesOpen && <div id="run-issues" className="run-issues" role="status"><strong>Run issues</strong><p>{run.error || (demo ? "Synthetic example: two messages failed qualification. This is a static UI state." : `${failed} message failures reported by the run. Individual failure details are not exposed by the current API.`)}</p>{["failed", "interrupted"].includes(run.status) && <Link href={`/imports${demo ? "?demo=1" : ""}`}>Open Imports to create a new run</Link>}</div>}
      {run.status === "queued" && !demo && <p className="workflow-empty">Waiting for the analysis worker to pick up this run.</p>}
      <div className="progress-footer"><span><i className="status-dot"/>{demo ? "Static demo · updates off" : error ? "Updates paused · retry connection" : completed ? "Final run status" : `Updates automatically${updated ? ` · checked ${new Date(updated).toLocaleTimeString("en-GB")}` : ""}`}</span>{ready ? <WorkflowLink href={leadsHref}>View available results <Icon name="chevron" size={17}/></WorkflowLink> : <span className="workflow-empty">No results available yet.</span>}</div>
    </Panel><Panel title="Run details" className="run-details"><dl>{[["Product", context?.product || workspace.products.find(p => p.id === run.product_id)?.name || (demo && !sourcePreview ? "Backend Academy" : `Product ${run.product_id.slice(0, 8)}`)], ["Community", context?.community || (demo && !sourcePreview ? "Developer community" : "Not available from run API")], ["Source", context?.filename || (demo && !sourcePreview ? "developer-community.csv" : `Batch ${run.batch_id.slice(0, 8)}`)], ["Messages", String(total)], ["Started", sourcePreview ? "Not started" : run.started_at ? new Date(run.started_at).toLocaleDateString("en-GB") : "Not started"], ["Mode", mock ? "Mock" : run.config_snapshot.provider_mode === "real" ? "Real" : "Unknown"], ["Cost", mock ? "$0.00" : "Unavailable"]].map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}</dl><p><Icon name="info" size={19}/>{mock ? "Mock run — no provider charges." : "Provider cost is not exposed by this API."}</p></Panel></div>}
    {run && <ArrivingResults {...results} demo={demo} community={context?.community || "Imported community"} href={leadsHref} retry={() => setResultsRefresh(value => value + 1)}/>}
    {demo && <details className="demo-state-controls"><summary>Demo status previews</summary><label htmlFor="demo-run-state">Demo run state</label><select id="demo-run-state" value={run?.status || "running"} disabled={sourcePreview} onChange={e => router.replace(`/runs/${id}?demo=1&state=${e.target.value}`)}>{["queued", "running", "partial", "completed", "failed", "interrupted"].map(s => <option key={s} value={s}>{s}</option>)}</select><p>Manual snapshots only. No progress is simulated automatically.</p></details>}
  </div>;
}
