"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Run } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";

export default function RunRecovery({ id, onUpdate }: { id: string; onUpdate?: (run: Run) => void }) {
  const [run, setRun] = useState<Run | null>(null), [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  const retryKey = useRef<string | null>(null), inFlight = useRef(false), update = useRef(onUpdate);
  useEffect(() => { update.current = onUpdate; }, [onUpdate]);
  useEffect(() => {
    let cancelled = false, timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api.run(id);
        if (cancelled) return;
        setRun(current); setError(null); update.current?.(current);
        if (["queued", "running"].includes(current.status)) timer = setTimeout(poll, 2000);
      } catch (e) {
        if (cancelled) return;
        setError(e as Error);
        // Authentication/ownership errors need user action, not repeated polling.
        if (!(e instanceof ApiError) || ![401, 403, 404].includes(e.status)) timer = setTimeout(poll, 4000);
      }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [id, refresh]);
  async function retry() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    retryKey.current ??= crypto.randomUUID();
    try {
      const current = await api.retryRun(id, retryKey.current);
      retryKey.current = null; setRun(current); update.current?.(current); setRefresh(n => n + 1);
    } catch (e) {
      setError(e as Error);
      if (e instanceof ApiError && e.status > 0) retryKey.current = null;
      // Unknown network outcomes reuse the same key on an explicit retry.
    } finally { inFlight.current = false; setBusy(false); }
  }
  const active = run && ["queued", "running"].includes(run.status);
  const retryable = run && ["partial", "failed", "interrupted"].includes(run.status);
  return <div aria-live="polite"><ErrorMessage error={error}/>{!run && !error && <p>Loading analysis status…</p>}{run && <>
    <p>{active ? (run.status === "queued" ? "Analysis pending" : "Analysis processing") : run.status === "completed" ? (run.attempt_no > 1 ? "Analysis recovered successfully" : "Analysis completed") : "Analysis needs attention"} · Attempt {run.attempt_no}</p>
    <p>{run.processed_count} / {run.total_count} processed · {run.failed_count} failed</p>
    <progress className="w-full" value={run.processed_count} max={run.total_count || 1}/>
    {run.error && <p role="alert">{run.error}</p>}
    {retryable && <button type="button" disabled={busy} onClick={() => void retry()}>{busy ? "Requesting retry…" : "Retry failed analyses"}</button>}
    {retryable && <p className="text-sm">Completed results are preserved. Retry uses the original business snapshot.</p>}
  </>}</div>;
}
