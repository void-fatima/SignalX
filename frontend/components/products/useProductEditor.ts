"use client";
import { useEffect, useRef, useState } from "react";
import { allProducts, api, type Product } from "@/lib/api";
import { demoProduct, starterProduct, toDraft, toProductInput, validateProduct, type ProductDraft, type ProductErrors } from "@/lib/product-profile";
import { useWorkspace } from "../WorkspaceContext";
export function useProductEditor() {
  const { demo, products, setProducts, selectedProductId, setSelectedProductId, setSelectionLocked } = useWorkspace();
  const [draft, setDraft] = useState(() => toDraft(starterProduct));
  const [baseline, setBaseline] = useState(draft);
  const [errors, setErrors] = useState<ProductErrors>({});
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [total, setTotal] = useState<number | null>(null), [reload, setReload] = useState(0);
  const selection = useRef<string | null>(null), version = useRef(0);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  useEffect(() => {
    const current = ++version.current;
    let cancelled = false;
    setLoading(true); setBusy(false); setError(""); setNotice(""); setErrors({}); setTotal(null);
    setProducts([]); setSelectedProductId(""); selection.current = null;
    const load = demo ? Promise.resolve({ items: [structuredClone(demoProduct)], total: 1 }) : allProducts();
    load.then(page => {
      if (cancelled || version.current !== current) return;
      const stored = demo ? "" : localStorage.getItem("product_id");
      const product = page.items.find(item => item.id === stored) || page.items[0];
      const initial = toDraft(product || starterProduct);
      if (stored && !page.items.some(item => item.id === stored)) { localStorage.removeItem("product_id"); setNotice("The saved profile is unavailable. Choose one of your current profiles."); }
      setProducts(page.items); setTotal(page.total); setSelectedProductId(product?.id || "");
      selection.current = product?.id || ""; setDraft(initial); setBaseline(initial);
    }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load products."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; ++version.current; };
  }, [demo, reload, setProducts, setSelectedProductId]);
  useEffect(() => {
    if (loading || selection.current === selectedProductId || selection.current === null) return;
    const product = products.find(item => item.id === selectedProductId);
    const initial = toDraft(product || starterProduct);
    selection.current = selectedProductId; setDraft(initial); setBaseline(initial); setErrors({}); setNotice(""); setError("");
  }, [loading, selectedProductId, products]);
  useEffect(() => { setSelectionLocked(dirty || busy || loading); return () => setSelectionLocked(false); }, [dirty, busy, loading, setSelectionLocked]);
  useEffect(() => {
    if (!demo && products.some(product => product.id === selectedProductId)) localStorage.setItem("product_id", selectedProductId);
  }, [demo, products, selectedProductId]);
  function change(key: keyof ProductDraft, value: string) {
    setDraft(previous => ({ ...previous, [key]: value })); setErrors(previous => ({ ...previous, [key]: undefined })); setNotice("");
  }
  function cancel() { setDraft(baseline); setErrors({}); setError(""); setNotice("Changes discarded."); document.getElementById("product-name")?.focus(); }
  async function save() {
    const invalid = validateProduct(draft); setErrors(invalid); setNotice(""); setError("");
    const first = Object.keys(invalid)[0];
    if (first) { document.getElementById(`product-${first}`)?.focus(); return; }
    const current = version.current;
    setBusy(true);
    try {
      const input = toProductInput(draft);
      const result: Product = demo
        ? { ...input, price: input.price == null ? null : String(input.price), id: selectedProductId || `demo-product-${Date.now()}`, created_at: new Date().toISOString() }
        : await api.saveProduct(input, selectedProductId || undefined);
      if (current !== version.current) return;
      const exists = products.some(product => product.id === result.id);
      setProducts(previous => exists ? previous.map(product => product.id === result.id ? result : product) : [...previous, result]);
      if (!exists) setTotal(previous => (previous || 0) + 1);
      selection.current = result.id; setSelectedProductId(result.id);
      const saved = toDraft(result); setDraft(saved); setBaseline(saved);
      if (!demo) localStorage.setItem("product_id", result.id);
      setNotice(demo ? "Saved locally · demo. Changes reset on reload." : "Product saved.");
    } catch (reason) { if (current === version.current) setError(reason instanceof Error ? reason.message : "Could not save product."); }
    finally { if (current === version.current) setBusy(false); }
  }
  return { demo, products, selectedProductId, draft, errors, loading, busy, dirty, error, notice, total, change, cancel, save,
    retry: () => setReload(value => value + 1), create: () => setSelectedProductId(""), select: (id: string) => setSelectedProductId(id) };
}
