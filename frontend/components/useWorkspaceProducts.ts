"use client";
import { useEffect, useState } from "react";
import { allProducts, api } from "@/lib/api";
import { demoProduct } from "@/lib/product-profile";
import { useWorkspace } from "./WorkspaceContext";
export function useWorkspaceProducts() {
  const workspace = useWorkspace();
  const { demo, setProducts, setSelectedProductId } = workspace;
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true); setError(""); setProducts([]); setSelectedProductId("");
    const load = demo ? Promise.resolve({ items: [demoProduct] }) : allProducts();
    load.then(page => {
      if (cancelled) return;
      const stored = demo ? "" : localStorage.getItem("product_id");
      if (stored && !page.items.some(item => item.id === stored)) { localStorage.removeItem("product_id"); setError("The saved profile is unavailable. Choose one of your current profiles."); }
      setProducts(page.items);
      setSelectedProductId(page.items.find(p => p.id === stored)?.id || page.items[0]?.id || "");
    }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load products."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [demo, reload, setProducts, setSelectedProductId]);
  useEffect(() => {
    if (!demo && workspace.products.some(p => p.id === workspace.selectedProductId)) localStorage.setItem("product_id", workspace.selectedProductId);
  }, [demo, workspace.products, workspace.selectedProductId]);
  return { ...workspace, loading, error, retry: () => setReload(value => value + 1) };
}
