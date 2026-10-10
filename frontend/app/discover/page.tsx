"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { allProducts, ApiError, type Product } from "@/lib/api";
import { discoveryApi, discoveryLink, type SearchInput, type SearchOut, type Prospect, type SourceStatus } from "@/lib/discovery-api";
import { useWorkspace } from "@/components/WorkspaceContext";
import "./discovery.css";

type Intent = { key: string; input: SearchInput };
const labels = { brave: "Web search · Brave", greenhouse: "Jobs · Greenhouse", lever: "Jobs · Lever", places: "Local businesses · Google Places IDs" };
export default function Discover() {
  const { user, demo } = useWorkspace();
  const [products, setProducts] = useState<Product[]>([]), [sources, setSources] = useState<SourceStatus[]>([]);
  const [productId, setProductId] = useState(""), [source, setSource] = useState<SearchInput["source"]>("brave");
  const [keywords, setKeywords] = useState(""), [industry, setIndustry] = useState(""), [location, setLocation] = useState(""), [country, setCountry] = useState(""), [board, setBoard] = useState(""), [limit, setLimit] = useState(10);
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [active, setActive] = useState<SearchOut | null>(null), [history, setHistory] = useState<SearchOut[]>([]), [saved, setSaved] = useState<Prospect[]>([]), [selected, setSelected] = useState<string[]>([]), [intent, setIntent] = useState<Intent | null>(null);
  const alive = useRef(true), lock = useRef(false);
  const storageKey = `signalx:discovery-pending:${user?.id || "guest"}`;
  const jobs = source === "greenhouse" || source === "lever";
  const configured = sources.find(item => item.source === source);
  useEffect(() => {
    alive.current = true;
    if (demo || !user) { setLoading(false); return; }
    Promise.all([allProducts(), discoveryApi.sources(), discoveryApi.history(), discoveryApi.prospects()]).then(([profiles, availability, searches, prospects]) => {
      if (!alive.current) return;
      setProducts(profiles.items); setSources(availability.items); setHistory(searches); setSaved(prospects); setProductId(profiles.items[0]?.id || "");
      try {
        const pending: Intent = JSON.parse(sessionStorage.getItem(storageKey) || "null");
        if (pending && typeof pending.key === "string" && pending.input && profiles.items.some(p => p.id === pending.input.product_id)) setIntent(pending);
      } catch { /* Invalid local pending data cannot trigger a request. */ }
    }).catch(reason => { if (alive.current) setError(reason instanceof Error ? reason.message : "Discovery could not be loaded."); }).finally(() => { if (alive.current) setLoading(false); });
    return () => { alive.current = false; };
  }, [user?.id, demo, storageKey]);
  function remember(value: Intent | null) {
    setIntent(value);
    try { if (value) sessionStorage.setItem(storageKey, JSON.stringify(value)); else sessionStorage.removeItem(storageKey); }
    catch { setNotice("Pending request cannot survive reload in this browser. Keep this page open to check it safely."); }
  }
  async function search(checkPrevious = false) {
    if (lock.current || !user || demo) return;
    if (!checkPrevious && !keywords.trim()) { setError("Keywords must contain non-whitespace text."); return; }
    const pending = checkPrevious ? intent : { key: crypto.randomUUID(), input: { product_id: productId, source, keywords: keywords.trim(), industry: jobs ? "" : industry.trim(), country: jobs ? "" : country.trim().toUpperCase(), location: location.trim(), board_slug: jobs ? board.trim() : "", limit } };
    if (!pending) return;
    lock.current = true; setBusy(true); setError(""); setNotice(""); remember(pending);
    try {
      const value = await discoveryApi.search(pending.input, pending.key);
      if (!alive.current) return;
      if (value.product_id !== pending.input.product_id || value.source !== pending.input.source) throw new Error("Search response does not match your selected profile and source.");
      setActive(value); setSelected([]); setHistory(previous => [value, ...previous.filter(item => item.id !== value.id)].slice(0, 20));
      if (value.status === "pending") { setNotice("Search is still pending. Check explicitly; no request is retried automatically."); }
      else { remember(null); if (value.status === "failed") setError(value.error || "Discovery source failed."); else setNotice(`${value.results.length} results. ${value.request_count} source request(s) this operation; estimated cost unknown. No AI was called.`); }
    } catch (reason) {
      if (alive.current) {
        const definitive = reason instanceof ApiError && [400, 401, 403, 404, 409, 422, 429, 503].includes(reason.status);
        if (definitive) remember(null);
        setError(`${reason instanceof Error ? reason.message : "Search could not be confirmed."}${definitive ? "" : " Use Check previous search to reuse its key; no automatic retry occurs."}`);
      }
    }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  async function save() {
    if (!active || !selected.length || lock.current) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    try { const rows = await discoveryApi.save(active.id, selected); if (alive.current) { setSaved(previous => [...rows, ...previous.filter(item => !rows.some(row => row.id === item.id))]); setSelected([]); setNotice(`${rows.length} prospects saved. No analysis or message sending occurred.`); } }
    catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "Prospects could not be saved."); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  if (demo) return <section className="card"><h1>Discover Leads</h1><p>Discovery uses configured public sources in your signed-in workspace. Demo mode does not search or fabricate results.</p><Link href="/discover">Use your connected workspace</Link></section>;
  return <div className="discovery-page"><header><span className="eyebrow">Public-source discovery</span><h1>Discover Leads</h1><p>Find prospects without CSV. Preview the source before deciding whether to save or evaluate it.</p></header>
    {loading && <p role="status">Loading profiles and discovery sources…</p>}{error && <p className="discovery-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!loading && !products.length && <p>Create a <Link href="/products">product profile</Link> first.</p>}
    {intent && <section className="card"><h2>Unconfirmed search</h2><p>Check the previous operation with its existing key. This never automatically creates a second source request.</p><button disabled={busy} onClick={() => void search(true)}>Check previous search</button></section>}
    <form className="discovery-form card" onSubmit={event => { event.preventDefault(); void search(); }} aria-busy={busy}>
      <fieldset disabled={loading || busy || !!intent || !products.length}><div className="discovery-fields">
        <div><label htmlFor="discovery-product">Product</label><select id="discovery-product" value={productId} onChange={e => { setProductId(e.target.value); setActive(null); setSelected([]); }}>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
        <div><label htmlFor="discovery-source">Search source</label><select id="discovery-source" value={source} onChange={e => { setSource(e.target.value as SearchInput["source"]); setActive(null); setSelected([]); }}>{Object.entries(labels).map(([key, text]) => <option value={key} key={key}>{text}</option>)}</select></div>
        <div className="discovery-wide"><label htmlFor="discovery-keywords">Keywords</label><input id="discovery-keywords" required minLength={1} maxLength={200} value={keywords} onChange={e => setKeywords(e.target.value)} placeholder="e.g. finance operations"/></div>
        {jobs ? <div className="discovery-wide"><label htmlFor="discovery-board">Company board slug</label><input id="discovery-board" required maxLength={80} pattern="[a-zA-Z0-9_-]+" value={board} onChange={e => setBoard(e.target.value)}/><p>One known company board only; this is not universal job-board search.</p></div> : <><div><label htmlFor="discovery-industry">Industry (optional)</label><input id="discovery-industry" maxLength={100} value={industry} onChange={e => setIndustry(e.target.value)}/></div><div><label htmlFor="discovery-country">Country code (optional)</label><input id="discovery-country" maxLength={2} pattern="[A-Za-z]{2}" placeholder="DE" value={country} onChange={e => setCountry(e.target.value)}/></div></>}
        <div><label htmlFor="discovery-location">Location{source === "places" ? " (required)" : " (optional)"}</label><input id="discovery-location" required={source === "places"} maxLength={150} value={location} onChange={e => setLocation(e.target.value)}/></div>
        <div><label htmlFor="discovery-limit">Maximum results</label><select id="discovery-limit" value={limit} onChange={e => setLimit(Number(e.target.value))}>{[5, 10, 20].map(n => <option key={n} value={n}>{n}</option>)}</select></div>
      </div><p className={configured?.configured ? "discovery-note" : "discovery-error"}>{configured?.message || "Source configuration could not be verified."}</p><p className="discovery-note">At most one source request. Billing may apply; cost is unknown. Search never calls AvalAI or sends outreach.</p><button type="submit" disabled={!configured?.configured}>{busy ? "Searching…" : "Search prospects"}</button></fieldset>
    </form>
    {active && <section className="card" aria-label="Discovery results"><div className="discovery-section-heading"><h2>Results · {products.find(p => p.id === active.product_id)?.name || active.product_id}</h2><span>{labels[active.source]}</span></div>
      {active.status === "completed" && !active.results.length && <p>No results within this source and bounded first page. No results were invented.</p>}
      <div className="discovery-results">{active.results.map(item => { const href = discoveryLink(item.url); return <article key={item.source_id}><div className="discovery-result-heading"><input type="checkbox" aria-label={`Select ${item.title}`} disabled={busy || !href} checked={selected.includes(item.source_id)} onChange={e => setSelected(previous => e.target.checked ? [...previous, item.source_id] : previous.filter(id => id !== item.source_id))}/><h3 dir="auto">{item.title}</h3></div><span className="discovery-signal">Not AI evaluated</span><p dir="auto">{item.excerpt}</p><p className="discovery-note">{item.explanation}</p>{item.location && <p>{item.location}</p>}{href ? <a href={href} target="_blank" rel="noopener noreferrer">Open original source</a> : <p className="discovery-error">Source link is unavailable or unsafe.</p>}</article>; })}</div>
      <button disabled={busy || !selected.length || active.status !== "completed"} onClick={() => void save()}>Save selected prospects</button></section>}
    <section className="card" aria-label="Saved prospects"><h2>Saved prospects</h2><p className="discovery-note">Separate from message leads. Company relevance and hiring activity do not confirm buying intent.</p>{!saved.length && <p>No saved prospects yet.</p>}{saved.map(item => <article className="discovery-saved" key={item.id}><h3 dir="auto">{item.title}</h3><p>{item.explanation}</p><span>{item.qualification_status === "not_requested" ? "AI evaluation not requested" : item.qualification_status}</span></article>)}</section>
    <details className="card"><summary>Recent search history ({history.length}, latest 20)</summary>{history.map(item => <button className="discovery-history" key={item.id} disabled={busy} onClick={() => { setActive(item); setSelected([]); }}><span>{labels[item.source]} · {item.status}</span><span>{item.results.length} results · {item.request_count} request(s) · cost unknown</span></button>)}</details>
  </div>;
}
