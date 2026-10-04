"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, type Run } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";
const terminal = ["completed", "partial", "failed", "interrupted"];
export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params), [run, setRun] = useState<Run | null>(null), [error, setError] = useState<Error | null>(null);
  useEffect(() => { let cancelled = false, timer: ReturnType<typeof setTimeout>;
    async function poll() { try { const r = await api.run(id); if (cancelled) return; setRun(r); setError(null); if (!terminal.includes(r.status)) timer = setTimeout(poll, 2000); } catch (e) { if (!cancelled) { setError(e as Error); timer = setTimeout(poll, 4000); } } }
    void poll(); return () => { cancelled = true; clearTimeout(timer); };
  }, [id]);
  return <><h1>Analysis progress</h1><ErrorMessage error={error}/>{!run ? <p>Loading run…</p> : <div className="card" aria-live="polite"><h2>{run.status}</h2><p>{run.processed_count} / {run.total_count} processed · {run.failed_count} failed</p><progress className="w-full" value={run.processed_count} max={run.total_count || 1}/><p className="mt-4">Mock provider · offline context includes following messages.</p>{run.status === "queued" && <p>Waiting for the separate worker. Start it with python -m app.worker.</p>}{run.status === "partial" && <p className="text-amber-800">Some messages failed. Successful results remain available.</p>}{run.error && <p role="alert">{run.error}</p>}<Link href={`/leads?run_id=${id}`} onClick={() => localStorage.setItem("run_id", id)}>View results →</Link></div>}</>;
}
