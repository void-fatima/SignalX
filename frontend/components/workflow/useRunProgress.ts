"use client";
import { useEffect, useState } from "react";
import { api, type Run } from "@/lib/api";
import { demoRun } from "@/lib/demo-inbox";
import { readRunContext } from "@/lib/run-context";
export const terminalStatuses = ["completed", "partial", "failed", "interrupted"];
export function useRunProgress(id: string, demo: boolean, preview: string | null) {
  const [run, setRun] = useState<Run | null>(null), [error, setError] = useState("");
  const [loading, setLoading] = useState(true), [refresh, setRefresh] = useState(0), [updated, setUpdated] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false, timer: ReturnType<typeof setTimeout> | undefined;
    setRun(null); setError(""); setLoading(true); setUpdated(null);
    if (demo) {
      const stored = readRunContext(id);
      const status: Run["status"] = ["queued", "running", ...terminalStatuses].includes(preview || "") ? preview as Run["status"] : id === "demo-import" ? "queued" : id === "demo-run-023" ? "partial" : id === "demo-run-022" ? "completed" : "running";
      const total = id === "demo-import" ? stored?.total || 0 : id === "demo-run-022" ? 12 : 20;
      const processed = status === "queued" ? 0 : status === "running" ? Math.floor(total * .7) : status === "completed" || status === "partial" ? total : Math.floor(total * .7);
      setRun({ ...demoRun, id, status, total_count: total, processed_count: processed, failed_count: ["running", "partial", "failed", "interrupted"].includes(status) ? Math.min(2, processed) : 0, started_at: status === "queued" ? null : demoRun.created_at, error: ["failed", "interrupted"].includes(status) ? "Example worker interruption. Successful results remain available." : null });
      setLoading(false); return;
    }
    async function poll() {
      try {
        const value = await api.run(id);
        if (cancelled) return;
        if (value.id !== id) throw new Error("The server returned a different run. Retry loading this run.");
        setRun(value); setError(""); setUpdated(new Date().toISOString());
        if (!terminalStatuses.includes(value.status)) timer = setTimeout(poll, 2000);
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load this run."); }
      finally { if (!cancelled) setLoading(false); }
    }
    void poll(); return () => { cancelled = true; clearTimeout(timer); };
  }, [id, demo, preview, refresh]);
  return { run, error, loading, updated, retry: () => setRefresh(value => value + 1) };
}
