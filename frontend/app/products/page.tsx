"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, ApiError, type Product, type ProductInput } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";

const PAGE_SIZE = 20;

export default function Products() {
  const [products, setProducts] = useState<Product[]>([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0);
  const [error, setError] = useState<Error | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Product | null>(null), [viewing, setViewing] = useState<Product | null>(null), [selected, setSelected] = useState<Product | null>(null);
  const [formVersion, setFormVersion] = useState(0), [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { const page = await api.products(offset, PAGE_SIZE); setProducts(page.items); setTotal(page.total); }
    catch (error) { setError(error as Error); }
    finally { setLoading(false); }
  }, [offset]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const id = localStorage.getItem("product_id");
    if (!id) return;
    let active = true;
    api.product(id).then(product => { if (active) setSelected(product); }).catch(error => {
      if (!active) return;
      if (error instanceof ApiError && [404, 422].includes(error.status)) localStorage.removeItem("product_id");
      else setError(error as Error);
    });
    return () => { active = false; };
  }, []);
  function select(product: Product) { localStorage.setItem("product_id", product.id); setSelected(product); setNotice(`Selected ${product.name}.`); }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(null); setNotice("");
    const form = new FormData(event.currentTarget);
    const text = (key: string) => String(form.get(key) || "").trim();
    const list = (key: string) => text(key).split("\n").map(s => s.trim()).filter(Boolean);
    const body: ProductInput = { name: text("name"), description: text("description"), target_customer: text("target_customer"), problems_solved: list("problems_solved"), best_fit: list("best_fit"), not_fit: list("not_fit"), price: text("price") || null, currency: text("currency") };
    try {
      if (!body.name || !body.description || !body.target_customer) throw new Error("Name, description and target customer cannot be blank.");
      const product = await api.saveProduct(body, editing?.id);
      select(product); setViewing(product); setEditing(null); setFormVersion(value => value + 1);
      setNotice(`Saved ${product.name}. It is the current profile for analysis.`);
      await load();
    } catch (error) { setError(error as Error); }
    finally { setBusy(false); }
  }
  return <><h1>Business / product profiles</h1><p>Describe your business or product so messages are evaluated against its actual offering and customers.</p>
    <ErrorMessage error={error}/>{notice && <p role="status">{notice}</p>}
    <div className="card"><h2>Current profile</h2>{selected ? <><p dir="auto">{selected.name}</p><Link href="/imports">Analyze messages for this profile →</Link></> : <p>Create a profile or select one below before analyzing messages.</p>}</div>
    <form key={`${editing?.id || "new"}-${formVersion}`} onSubmit={save} className="card"><h2>{editing ? "Edit profile" : "Create profile"}</h2><fieldset disabled={busy}>
      <label htmlFor="name">Name</label><input id="name" name="name" dir="auto" required maxLength={200} defaultValue={editing?.name || ""}/>
      <label htmlFor="description">Description</label><textarea id="description" name="description" dir="auto" required maxLength={4000} defaultValue={editing?.description || ""}/>
      <label htmlFor="target">Target customer</label><textarea id="target" name="target_customer" dir="auto" required maxLength={2000} defaultValue={editing?.target_customer || ""}/>
      <details className="mt-4"><summary>Optional product details</summary>
        {(["problems_solved", "best_fit", "not_fit"] as const).map(key => <div key={key}><label htmlFor={key}>{key.replaceAll("_", " ")} (one per line)</label><textarea id={key} name={key} dir="auto" defaultValue={editing?.[key]?.join("\n") || ""}/></div>)}
        <div className="grid grid-cols-2 gap-4"><div><label htmlFor="price">Price (optional)</label><input id="price" name="price" type="number" min="0" step="0.01" defaultValue={editing?.price ?? ""}/></div><div><label htmlFor="currency">Currency</label><input id="currency" name="currency" required pattern="[A-Z]{3}" maxLength={3} defaultValue={editing?.currency || "USD"}/></div></div>
      </details>
      <button className="mt-5">{busy ? "Saving…" : "Save profile"}</button>{editing && <button type="button" className="ml-3" onClick={() => { setEditing(null); setError(null); }}>Cancel edit</button>}
    </fieldset></form>
    <div className="card"><h2>Your profiles</h2>{loading ? <p role="status">Loading…</p> : products.length === 0 ? <p>No profiles yet. Add your first business above.</p> : products.map(product => <div className="border-b py-3 flex flex-wrap gap-4 items-center" key={product.id}>
      <span dir="auto" className="flex-1">{product.name}{selected?.id === product.id && <span className="badge ml-3">Current</span>}</span>
      <button disabled={busy} onClick={() => setViewing(product)}>View</button>
      <button disabled={busy} onClick={() => { setEditing(product); setError(null); setNotice(""); window.scrollTo(0, 0); }}>Edit</button>
      <button disabled={busy || selected?.id === product.id} onClick={() => select(product)}>Select</button>
    </div>)}
      {total > PAGE_SIZE && <div className="flex flex-wrap gap-4 mt-4"><button disabled={loading || busy || offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Previous</button><span>{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span><button disabled={loading || busy || offset + PAGE_SIZE >= total} onClick={() => setOffset(value => value + PAGE_SIZE)}>Next</button></div>}
      {error && <button disabled={busy || loading} onClick={() => void load()}>Retry loading profiles</button>}
    </div>
    {viewing && <div className="card"><h2 dir="auto">{viewing.name}</h2><h3 className="font-semibold">Description</h3><p dir="auto" className="whitespace-pre-wrap">{viewing.description}</p><h3 className="font-semibold">Target customer</h3><p dir="auto" className="whitespace-pre-wrap">{viewing.target_customer}</p><button onClick={() => setViewing(null)}>Close details</button></div>}
  </>;
}
