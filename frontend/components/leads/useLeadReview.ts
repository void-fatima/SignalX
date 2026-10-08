"use client";
import { useEffect, useState } from "react";
import { api, type LeadDetail, type Run } from "@/lib/api";
import { demoDetails, demoRun } from "@/lib/demo-inbox";
export function useLeadReview(id: string, demo: boolean) {
  const [detail, setDetail] = useState<LeadDetail | null>(null), [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true), [error, setError] = useState(""), [runError, setRunError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setRunError(""); setDetail(null); setRun(null);
    if (demo) { const fixture = demoDetails[id]; setDetail(fixture || null); setRun(fixture ? demoRun : null); if (!fixture) setError("This demo opportunity does not exist."); setLoading(false); return; }
    async function load() {
      try {
        const value = await api.lead(id);
        if (cancelled) return;
        if (value.analysis.id !== id || value.analysis.message_id !== value.message.id) throw new Error("Source details do not match this opportunity.");
        setDetail(value); setLoading(false);
        try {
          const status = await api.run(value.analysis.run_id);
          if (!cancelled) {
            if (status.id !== value.analysis.run_id || status.batch_id !== value.message.batch_id) setRunError("Run metadata does not match this source.");
            else setRun(status);
          }
        } catch (reason) { if (!cancelled) setRunError(reason instanceof Error ? reason.message : "Run status unavailable."); }
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load this opportunity."); }
      finally { if (!cancelled) setLoading(false); }
    }
    void load(); return () => { cancelled = true; };
  }, [id, demo, reload]);
  return { detail, run, loading, error, runError, retry: () => setReload(value => value + 1) };
}
