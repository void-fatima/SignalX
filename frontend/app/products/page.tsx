"use client";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, type Product, type ProductInput } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";
export default function Products() {
  const [products, setProducts] = useState<Product[]>([]), [error, setError] = useState<Error | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [editing, setEditing] = useState<Product | null>(null);
  const load = () => api.products().then(p => setProducts(p.items)).catch(setError).finally(() => setLoading(false));
  useEffect(() => { void load(); }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null);
    const form = new FormData(event.currentTarget);
    const list = (key: string) => String(form.get(key) || "").split("\n").map(s => s.trim()).filter(Boolean);
    const body: ProductInput = { name: String(form.get("name")), description: String(form.get("description")), target_customer: String(form.get("target_customer")), problems_solved: list("problems_solved"), best_fit: list("best_fit"), not_fit: list("not_fit"), price: String(form.get("price") || "") || null, currency: String(form.get("currency")) };
    try { const product = await api.saveProduct(body, editing?.id); localStorage.setItem("product_id", product.id); setEditing(null); await load(); }
    catch (e) { setError(e as Error); } finally { setBusy(false); }
  }
  return <><h1>Product profiles</h1><ErrorMessage error={error} /><form key={editing?.id || "new"} onSubmit={save} className="card"><h2>{editing ? "Edit product" : "Create product"}</h2><label htmlFor="name">Name</label><input id="name" name="name" required maxLength={200} defaultValue={editing?.name || "Project-based Backend Course"}/><label htmlFor="description">Description</label><textarea id="description" name="description" required maxLength={4000} defaultValue={editing?.description || "A project-based backend course covering Python, FastAPI and databases."}/><label htmlFor="target">Target customer</label><input id="target" name="target_customer" required defaultValue={editing?.target_customer || "Developers learning backend development"}/>{(["problems_solved", "best_fit", "not_fit"] as const).map(key => <div key={key}><label htmlFor={key}>{key.replaceAll("_", " ")} (one per line)</label><textarea id={key} name={key} defaultValue={editing?.[key]?.join("\n") || (key === "problems_solved" ? "Learning backend through practical projects\nدوره بک‌اند پروژه‌محور" : "")}/></div>)}<div className="grid grid-cols-2 gap-4"><div><label htmlFor="price">Price (optional)</label><input id="price" name="price" type="number" min="0" step="0.01" defaultValue={editing?.price || ""}/></div><div><label htmlFor="currency">Currency</label><input id="currency" name="currency" required pattern="[A-Z]{3}" defaultValue={editing?.currency || "USD"}/></div></div><button className="mt-5" disabled={busy}>{busy ? "Saving…" : "Save product"}</button>{editing && <button type="button" className="ml-3" onClick={() => setEditing(null)}>Cancel edit</button>}</form><div className="card"><h2>Saved products</h2>{loading ? <p>Loading…</p> : products.length === 0 ? <p>No products yet.</p> : products.map(p => <div className="border-b py-3 flex gap-4 items-center" key={p.id}><span dir="auto" className="flex-1">{p.name}</span><button onClick={() => { setEditing(p); window.scrollTo(0, 0); }}>Edit</button><Link href="/imports" onClick={() => localStorage.setItem("product_id", p.id)}>Select & import →</Link></div>)}</div></>;
}
