"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, type LeadDetail } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";
export default function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params), [data, setData] = useState<LeadDetail | null>(null), [error, setError] = useState<Error | null>(null);
  useEffect(() => { let cancelled = false; api.lead(id).then(d => { if (!cancelled) setData(d); }).catch(e => { if (!cancelled) setError(e); }); return () => { cancelled = true; }; }, [id]);
  if (!data) return <><h1>Result detail</h1><ErrorMessage error={error}/>{!error && <p>Loading…</p>}</>;
  const { analysis: a, message: m } = data;
  return <><Link href={`/leads?run_id=${a.run_id}`}>← Results</Link><h1 className="mt-4">{a.decision || a.status} · {a.lead_score ?? "Not analyzed"}</h1><div className="card"><span className="badge">MOCK · {a.scoring_version}</span><h2 className="mt-4">Original message</h2><p className="text-sm">{m.author} · {new Date(m.timestamp).toLocaleString()}</p><p dir="auto">{m.content}</p><p>{a.reason}</p><p>Screening: {a.screening_reason} · Decision: {a.decision_reason || "screening only"}</p><h2>Evidence</h2>{a.evidence.length ? a.evidence.map((e, i) => <blockquote dir="auto" className="border-l-4 pl-4 my-3" key={i}>{e.quote}</blockquote>) : <p>No qualification evidence; this message was screened out.</p>}{a.signals && <><h2>Signals</h2><div className="grid grid-cols-2 gap-2 mb-4">{Object.entries(a.signals).map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")}: {value}</p>)}</div></>}<h2>Limitations</h2>{a.limitations.map((l, i) => <p key={i}>{l}</p>)}</div><div className="card"><h2>Conversation context</h2><p>Offline analysis: context may include later messages. Only the same batch and conversation are included.</p>{data.context.length ? data.context.map(c => <div className="border-t pt-3" key={c.id}><p className="text-sm">{c.author} · {new Date(c.timestamp).toLocaleString()}</p><p dir="auto">{c.content}</p></div>) : <p>No context messages.</p>}</div><div className="card"><h2>Product snapshot</h2><pre dir="auto">{JSON.stringify(data.product_snapshot, null, 2)}</pre></div></>;
}
