"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Run } from "@/lib/api";
import { clearIntent, intentSlot, readIntent, saveIntent, type RecoveryIntent } from "@/lib/recovery-intent";
import { useWorkspace } from "@/components/WorkspaceContext";

export default function RunRecovery({ run, onRecovered }: { run: Run; onRecovered: () => void }) {
  const { user, demo } = useWorkspace();
  const slot = intentSlot("analysis", user?.id || "guest", run.id);
  const [intent, setIntent] = useState<RecoveryIntent | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const locked = useRef(false), active = useRef(true);
  useEffect(() => { active.current = true; setIntent(readIntent(slot)); return () => { active.current = false; }; }, [slot]);
  const eligible = ["failed", "partial", "interrupted"].includes(run.status) && (run.failed_count > 0 || run.processed_count < run.total_count);
  async function retry() {
    if (locked.current || !eligible || demo || !user) return;
    locked.current = true; setBusy(true); setError("");
    try {
      const next = intent || { key: crypto.randomUUID() };
      saveIntent(slot, next); setIntent(next);
      const value = await api.retryRun(run.id, next.key);
      if (value.id !== run.id) throw new Error("Retry response does not match this run.");
      clearIntent(slot);
      if (active.current) { setIntent(null); onRecovered(); }
    } catch (reason) {
      // Transport errors and server errors may follow a committed enqueue.
      // Keep the same key until an authoritative acknowledgement arrives.
      if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500 && reason.status !== 409) { clearIntent(slot); if (active.current) setIntent(null); }
      if (active.current) setError(reason instanceof Error ? reason.message : "Analysis retry could not be confirmed.");
    } finally { locked.current = false; if (active.current) setBusy(false); }
  }
  return <section className="run-recovery" aria-label="Analysis recovery"><p>Attempt {run.attempt_no ?? "unavailable on this backend"}. Successful results and the original product snapshot are preserved.</p>
    {eligible && <><button disabled={demo || busy || !user} onClick={() => void retry()}>{busy ? "Requesting retry…" : intent ? "Check retry request" : "Retry failed analyses"}</button><p>{demo ? "Demo snapshot: recovery is not submitted." : intent ? "The previous retry is unconfirmed. Checking repeats its Idempotency-Key; it cannot enqueue a second attempt." : "Retries only failed or unfinished messages. Nothing is retried automatically."}</p></>}
    {(error || intent) && !demo && <button className="secondary-button" disabled={busy} onClick={onRecovered}>Reload run status</button>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
