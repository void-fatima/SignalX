"use client";
import { useEffect, useState } from "react";
import Dialog from "@/components/Dialog";
import { api, type Product } from "@/lib/api";

export default function ProductDetails({ product, demo, onDismiss }: { product: Product | null; demo: boolean; onDismiss: () => void }) {
  const [value, setValue] = useState<Product | null>(null), [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false; setValue(null); setError("");
    if (!product) return;
    (demo ? Promise.resolve(product) : api.product(product.id)).then(result => {
      if (result.id !== product.id) throw new Error("Profile details do not match the selected product.");
      if (!cancelled) setValue(result);
    }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Profile unavailable."); });
    return () => { cancelled = true; };
  }, [product, demo]);
  return <Dialog open={!!product} onDismiss={onDismiss} title="Product profile" labelId="product-details-title"><div className="product-details">
    {error ? <p role="alert">{error}</p> : !value ? <p role="status">Loading saved profile…</p> : <><p className="badge">{demo ? "DEMO · LOCAL" : "SAVED PROFILE"}</p><h3 dir="auto">{value.name}</h3><dl>{[["Description", value.description], ["Target customer", value.target_customer], ["Problems solved", (value.problems_solved || []).join("\n")], ["Best fit", (value.best_fit || []).join("\n")], ["Not a fit", (value.not_fit || []).join("\n")], ["Price", value.price == null ? "Not specified" : `${value.price} ${value.currency}`]].map(([term, text]) => <div key={term}><dt>{term}</dt><dd dir="auto">{text || "Not specified"}</dd></div>)}</dl><p>Editing this profile does not change previous analysis snapshots.</p></>}
  </div></Dialog>;
}
