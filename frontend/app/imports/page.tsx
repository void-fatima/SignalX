"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, type Product, type ImportResult } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";
export default function Imports() {
  const router = useRouter(), key = useRef<string | null>(null);
  const [products, setProducts] = useState<Product[]>([]), [product, setProduct] = useState(""), [result, setResult] = useState<ImportResult | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<Error | null>(null), [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    (async () => {
      const page = await api.products();
      const saved = localStorage.getItem("product_id");
      let current = page.items.find(item => item.id === saved);
      // The selected profile may be outside this first page; verify it with the owned detail endpoint.
      if (saved && !current) {
        try { current = await api.product(saved); page.items.push(current); }
        catch (error) {
          if (error instanceof ApiError && [404, 422].includes(error.status)) localStorage.removeItem("product_id");
          else throw error;
        }
      }
      if (!active) return;
      const id = current?.id || page.items[0]?.id || "";
      setProducts(page.items); setProduct(id);
      if (id) localStorage.setItem("product_id", id);
    })().catch(error => { if (active) setError(error as Error); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function upload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setBusy(true); setError(null); setResult(null); key.current = null;
    try { setResult(await api.importCSV(new FormData(e.currentTarget))); } catch (e) { setError(e as Error); } finally { setBusy(false); }
  }
  async function start() {
    if (!result || !product) return;
    setBusy(true); setError(null); key.current ||= crypto.randomUUID();
    try { const run = await api.startRun(product, result.batch.id, key.current); localStorage.setItem("run_id", run.id); router.push(`/runs/${run.id}`); } catch (e) { setError(e as Error); setBusy(false); }
  }
  return <><h1>Import messages</h1><ErrorMessage error={error}/><div className="card"><label htmlFor="product">Product</label><select id="product" value={product} disabled={busy || loading} onChange={e => { setProduct(e.target.value); if (e.target.value) localStorage.setItem("product_id", e.target.value); else localStorage.removeItem("product_id"); key.current = null; }}><option value="">Select a product</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>{!loading && products.length === 0 && <p>Create a product first.</p>}<form onSubmit={upload}><label htmlFor="community">Community</label><input id="community" name="community_name" required maxLength={200} defaultValue="Synthetic developer community"/><label htmlFor="file">UTF-8 CSV (up to 5 MB / 500 messages)</label><input id="file" type="file" name="file" accept=".csv,text/csv" required/><p className="text-sm mt-3">Required headers: external_id, conversation_id, author, content, timestamp. Timestamps require a timezone. Use data/demo_messages.csv from the repository.</p><button disabled={busy || !product}>{busy ? "Working…" : "Import CSV"}</button></form></div>{result && <div className="card"><h2>{result.duplicate ? "Existing import reused" : "Import complete"}</h2><p>{result.count} messages · {result.batch.community_name}</p>{result.warnings.map((w, i) => <p key={i} className="text-amber-800">{JSON.stringify(w)}</p>)}<button onClick={start} disabled={busy || !product}>Start Mock analysis</button></div>}</>;
}
