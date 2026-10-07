"use client";
import { useEffect, useState } from "react";
import { api, type Analysis, type LeadDetail } from "@/lib/api";
import { demoAnalyses, demoDetails } from "@/lib/demo-inbox";
export function useRunResults(id: string, batchId: string | undefined, processed: number, demo: boolean, refresh: number) {
  const [items, setItems] = useState<Analysis[]>([]), [details, setDetails] = useState<Record<string, LeadDetail>>({});
  const [total, setTotal] = useState(0), [error, setError] = useState(""), [loading, setLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setItems([]); setDetails({}); setTotal(0); setError("");
    if (!batchId || !processed) { setLoading(false); return; }
    if (demo) { setItems([demoAnalyses[0], demoAnalyses[1], demoAnalyses[4]]); setDetails(demoDetails); setTotal(9); setLoading(false); return; }
    setLoading(true);
    async function load() {
      try {
        const page = await api.leads(id, "", 0, "");
        if (cancelled) return;
        if (page.items.some(item => item.run_id !== id)) throw new Error("Results do not match this run. Retry loading results.");
        setItems(page.items.slice(0, 3)); setTotal(page.total);
        const sources = await Promise.allSettled(page.items.slice(0, 3).map(item => api.lead(item.id)));
        if (cancelled) return;
        const resolved: Record<string, LeadDetail> = {};
        let missing = false;
        sources.forEach((source, i) => {
          const expected = page.items[i];
          if (source.status === "fulfilled" && source.value.analysis.id === expected.id && source.value.analysis.run_id === id && source.value.message.id === expected.message_id && source.value.message.batch_id === batchId) resolved[expected.id] = source.value;
          else missing = true;
        });
        setDetails(resolved); if (missing) setError("Some source messages could not be loaded. Retry results to load them.");
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load results."); }
      finally { if (!cancelled) setLoading(false); }
    }
    void load(); return () => { cancelled = true; };
  }, [id, batchId, processed, demo, refresh]);
  return { items, details, total, error, loading };
}
