"use client";
import "@/app/inbox.css";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import ErrorMessage from "@/components/ErrorMessage";
import Icon from "@/components/Icon";
import LeadQueue from "@/components/leads/LeadQueue";
import RunSummary from "@/components/leads/RunSummary";
import LeadConversation from "@/components/leads/LeadConversation";
import SignalAnalysisDialog from "@/components/leads/SignalAnalysisDialog";
import ReplyComposer, { type ReviewDraft } from "@/components/leads/ReplyComposer";
import useInbox from "@/components/leads/useInbox";
import { demoMetadata } from "@/lib/demo-inbox";
import { filterLeads } from "@/lib/lead-presentation";

function Inbox() {
  const search = useSearchParams(), demo = search.get("demo") === "1";
  const [runId, setRunId] = useState("");
  const [decision, setDecision] = useState(""), [minScore, setMinScore] = useState(""), [offset, setOffset] = useState(0);
  const [query, setQuery] = useState(""), [filtersOpen, setFiltersOpen] = useState(false), [selected, setSelected] = useState("");
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [analysisOpen, setAnalysisOpen] = useState(false);
  useEffect(() => { setRunId(search.get("run_id") || localStorage.getItem("run_id") || ""); setQuery(search.get("q") || ""); setOffset(0); setSelected(""); }, [search]);
  const { page, details, run, error, detailErrors, runError, loading, retry } = useInbox({ runId, demo, decision, minScore, offset });
  const items = filterLeads(page?.items || [], decision, minScore, query, details);
  const selectedId = items.some(item => item.id === selected) ? selected : items[0]?.id || "";
  const detail = details[selectedId];
  useEffect(() => { setAnalysisOpen(false); }, [selectedId, runId, demo, decision, minScore, offset]);
  const selectedIndex = items.findIndex(item => item.id === selectedId);
  const draft = drafts[selectedId] || { text: demo ? demoMetadata[selectedId]?.reply || "" : "", status: "draft" as const };
  return <>
    <RunSummary run={run} items={page?.items || []} total={page?.total || 0} demo={demo}/>
    {demo && <div className="demo-banner"><span className="badge">MOCK WORKSPACE</span> Synthetic UI demo · scores and replies are examples. <Link href={runId ? `/leads?run_id=${encodeURIComponent(runId)}` : "/leads"}>Exit demo</Link></div>}
    <ErrorMessage error={error}/>{error && <button className="retry-button" type="button" onClick={retry}>Retry loading run</button>}
    {runError && <p role="status" className="run-warning">Run summary unavailable: {runError}</p>}
    <div className="inbox-grid"><section className="queue-panel" aria-label="Opportunity queue"><div className="queue-title"><h2>Lead queue <span className="count-pill">{page?.total || 0}</span></h2><button className="icon-button" type="button" aria-label="Toggle run and score filters" aria-expanded={filtersOpen} aria-controls="queue-filters" onClick={() => setFiltersOpen(!filtersOpen)}><Icon name="filter"/></button></div>
      <div className="queue-search"><Icon name="search" size={17}/><input type="search" aria-label="Search conversations on this page" placeholder="Search conversations…" value={query} onChange={event => setQuery(event.target.value)}/></div>
      <div className="queue-tabs" aria-label="Filter decisions">{[["", "All"], ["respond", "Respond"], ["review", "Review"]].map(([value, label]) => <button key={label} type="button" aria-pressed={decision === value} onClick={() => { setDecision(value); setOffset(0); }}>{label}{(!decision || decision === value) && <span>{value ? (page?.items || []).filter(item => item.decision === value).length : page?.total || 0}</span>}</button>)}</div>
      {filtersOpen && <div id="queue-filters" className="queue-filters"><label htmlFor="run-filter">Run ID</label><input id="run-filter" value={runId} disabled={demo} onChange={event => { setRunId(event.target.value); setOffset(0); }}/><label htmlFor="decision-filter">Decision</label><select id="decision-filter" value={decision} onChange={event => { setDecision(event.target.value); setOffset(0); }}><option value="">Review + respond</option><option value="respond">Respond</option><option value="review">Review</option><option value="ignore">Ignore</option></select><label htmlFor="score-filter">Minimum score</label><input id="score-filter" type="number" min="0" max="100" value={minScore} onChange={event => { setMinScore(event.target.value); setOffset(0); }}/></div>}
      {loading ? <div className="loading-state" role="status">Loading opportunities and source messages…</div> : <LeadQueue items={items} details={details} selected={selectedId} onSelect={setSelected} demo={demo} loading={loading}/>}
      {!demo && !runId && <div className="queue-start"><p>Import messages to start an analysis.</p><Link href="/imports">Import CSV ↗</Link><Link href="/leads?demo=1">Explore the mock workspace ↗</Link></div>}
      {page && page.total > page.limit && <div className="queue-pagination"><button className="secondary-button" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - page.limit))}>Previous</button><span>{offset + 1}–{Math.min(offset + page.limit, page.total)} of {page.total}</span><button className="secondary-button" disabled={loading || offset + page.limit >= page.total} onClick={() => setOffset(offset + page.limit)}>Next</button></div>}
      <div className="queue-import"><Icon name="file" size={24}/><div><strong>{demo ? "developer-community.csv" : run?.batch_id ? `Batch ${run.batch_id.slice(0, 8)}` : "No import selected"}</strong><span>{run?.total_count ?? "—"} messages{run && ` · ${new Date(run.created_at).toLocaleDateString("en-GB")}`}</span></div>{run && <span className="status-dot"/>}</div>
    </section><div className="detail-column" aria-busy={loading}>
      {loading ? <div className="detail-placeholder" role="status"><Icon name="chat" size={35}/><h2>Gathering the conversation</h2><p>Loading source, context and evidence.</p></div> : detail ? <><LeadConversation detail={detail} demo={demo} onAnalysis={() => setAnalysisOpen(true)} previous={selectedIndex > 0 ? () => setSelected(items[selectedIndex - 1].id) : undefined} next={selectedIndex < items.length - 1 ? () => setSelected(items[selectedIndex + 1].id) : undefined}/><ReplyComposer key={selectedId} draft={draft} demo={demo} onChange={value => setDrafts(current => ({ ...current, [selectedId]: value }))}/></> : <div className="detail-placeholder"><Icon name="chat" size={35}/><h2>{detailErrors[selectedId] ? "Source could not be loaded" : "Your next opportunity starts here"}</h2><p>{detailErrors[selectedId] || (query || decision || minScore ? "Try another search or filter." : "Select an opportunity to review its conversation and signals.")}</p>{detailErrors[selectedId] && <button type="button" onClick={retry}>Retry source details</button>}</div>}
    </div></div>
    {detail && <SignalAnalysisDialog detail={detail} demo={demo} open={analysisOpen} onDismiss={() => setAnalysisOpen(false)}/>}
  </>;
}
export default function Leads() { return <Suspense fallback={<p className="loading-state" role="status">Loading workspace…</p>}><Inbox/></Suspense>; }
