"use client";
import { useEffect, useState } from "react";
import { api, type Analysis, type LeadDetail, type Page, type Run } from "@/lib/api";
import { demoAnalyses, demoDetails, demoRun } from "@/lib/demo-inbox";

export default function useInbox({ runId, demo, decision, minScore, offset, status = "" }: { runId: string; demo: boolean; decision: string; minScore: string; offset: number; status?: string }) {
  const [page, setPage] = useState<Page<Analysis> | null>(null);
  const [details, setDetails] = useState<Record<string, LeadDetail>>({});
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [runError, setRunError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setPage(null); setDetails({}); setRun(null); setError(null); setDetailErrors({}); setRunError(null);
    if (demo) {
      const items = demoAnalyses.filter(item => (status === "failed" ? item.status === "failed" : !decision || item.decision === decision) && (!minScore || (item.lead_score ?? -1) >= Number(minScore)));
      setPage({ items: items.slice(offset, offset + 20), total: items.length, offset, limit: 20 }); setDetails(demoDetails); setRun(demoRun); setLoading(false);
      return () => { cancelled = true; };
    }
    if (!runId) { setLoading(false); return; }
    setLoading(true);
    api.run(runId).then(value => { if (!cancelled) setRun(value); }).catch((cause: Error) => { if (!cancelled) setRunError(cause.message); });
    api.leads(runId, decision, offset, minScore, status).then(async value => {
      if (cancelled) return;
      setPage(value);
      const result = await Promise.allSettled(value.items.map(item => api.lead(item.id)));
      if (cancelled) return;
      const resolved: Record<string, LeadDetail> = {}, failures: Record<string, string> = {};
      result.forEach((item, index) => {
        const expected = value.items[index];
        if (item.status === "fulfilled" && item.value.analysis.id === expected.id && item.value.analysis.run_id === runId && item.value.analysis.message_id === item.value.message.id) resolved[expected.id] = item.value;
        else failures[expected.id] = item.status === "rejected" ? String(item.reason instanceof Error ? item.reason.message : item.reason) : "Source details do not match this opportunity.";
      });
      setDetails(resolved); setDetailErrors(failures);
    }).catch((cause: Error) => { if (!cancelled) setError(cause); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [runId, demo, decision, minScore, offset, status, refresh]);
  return { page, details, run, error, detailErrors, runError, loading, retry: () => setRefresh(value => value + 1) };
}
