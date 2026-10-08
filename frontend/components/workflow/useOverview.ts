"use client";
import { useEffect, useState } from "react";
import { api, type AnalyticsOverview, type LeadDetail, type Run } from "@/lib/api";
import { demoDetails, demoRun } from "@/lib/demo-inbox";
export function useOverview(demo: boolean) {
  const [run, setRun] = useState<Run | null>(null), [review, setReview] = useState<LeadDetail[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null), [analyticsError, setAnalyticsError] = useState("");
  const [counts, setCounts] = useState<number[] | null>(null), [error, setError] = useState("");
  const [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setRun(null); setReview([]); setCounts(null); setAnalytics(null); setAnalyticsError("");
    if (demo) {
      setRun(demoRun); setCounts([4, 5, 11]); setReview([demoDetails["demo-lead-5"], demoDetails["demo-lead-6"]]); setLoading(false);
      return;
    }
    const id = localStorage.getItem("run_id");
    if (!id) { setLoading(false); return; }
    async function load() {
      try {
        const latest = await api.run(id!);
        if (cancelled) return;
        if (latest.id !== id) throw new Error("Summary does not match the selected run.");
        setRun(latest);
        void api.analytics(id!).then(value => {
          if (value.run_id !== id || value.provider_mode !== latest.config_snapshot.provider_mode) throw new Error("Analytics do not match this run.");
          if (!cancelled) setAnalytics(value);
        }).catch(reason => { if (!cancelled) setAnalyticsError(reason instanceof Error ? reason.message : "Analytics unavailable."); });
        const pages = await Promise.all(["respond", "review", "ignore"].map(decision => api.leads(id!, decision, 0, "")));
        if (cancelled) return;
        setCounts(pages.map(p => p.total));
        const details = await Promise.all(pages[1].items.slice(0, 2).map(item => api.lead(item.id)));
        if (!cancelled) setReview(details);
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load workspace summary."); }
      finally { if (!cancelled) setLoading(false); }
    }
    void load(); return () => { cancelled = true; };
  }, [demo, reload]);
  return { run, analytics, analyticsError, review, counts, error, loading, retry: () => setReload(value => value + 1) };
}
