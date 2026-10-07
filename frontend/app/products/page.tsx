"use client";
import Link from "next/link";
import Icon from "@/components/Icon";
import ProductPreview from "@/components/products/ProductPreview";
import { useProductEditor } from "@/components/products/useProductEditor";
import type { ProductDraft } from "@/lib/product-profile";
import "./product.css";
export default function Products() {
  const editor = useProductEditor();
  const { draft, errors, loading, busy, demo, dirty, selectedProductId, total, error, notice } = editor;
  function field(key: keyof ProductDraft, label: string, multiline = false, maxLength?: number, hint?: string) {
    const props = { id: `product-${key}`, name: key, value: draft[key], onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => editor.change(key, event.target.value),
      maxLength, "aria-invalid": !!errors[key], "aria-describedby": errors[key] ? `product-${key}-error` : hint ? `product-${key}-hint` : undefined, dir: "auto" as const };
    return <div className={`product-field product-field-${key}`}><label htmlFor={props.id}>{label}</label>{multiline ? <textarea {...props} rows={2}/> : <input {...props} inputMode={key === "price" ? "decimal" : "text"} placeholder={key === "price" ? "Not specified" : undefined}/>}
      {hint && <p className="field-hint" id={`product-${key}-hint`}>{hint}</p>}{errors[key] && <p className="field-error" id={`product-${key}-error`}>{errors[key]}</p>}</div>;
  }
  return <><div className="product-heading"><div><div className="product-title"><h1>Product profile</h1><span className="badge">{demo ? "MOCK DATA" : selectedProductId ? "CONNECTED" : "NEW DRAFT"}</span></div><p>Define who your product helps and when it is a good fit.</p></div><span className="saved-count">Saved products <strong>{total == null ? "—" : String(total).padStart(2, "0")}</strong></span></div>
    {loading && <p role="status" className="product-feedback">Loading product profiles…</p>}
    {error && <div role="alert" className="product-feedback product-error"><p>{error}</p>{total == null && <><button type="button" onClick={editor.retry}>Retry loading products</button> <Link href="/login">Sign in</Link> · <Link href="/products?demo=1">Explore demo</Link></>}</div>}
    {!loading && total === 0 && <p className="product-feedback">No saved products yet. Start with this editable example.</p>}
    <div className="product-grid"><form className="product-editor" noValidate aria-busy={loading || busy} onSubmit={event => { event.preventDefault(); void editor.save(); }}><fieldset disabled={loading || busy || total == null}>
      <section aria-labelledby="product-basics"><h2 id="product-basics" className="eyebrow">Product basics</h2>{field("name", "Product name", false, 200)}{field("description", "Description", true, 4000)}{field("target_customer", "Target customer", true, 2000)}</section>
      <section aria-labelledby="product-fit"><h2 id="product-fit" className="eyebrow">Fit criteria</h2>{field("problems_solved", "Problems solved", true, undefined, "One item per line")}
        <div className="product-field-pair">{field("best_fit", "Best fit", true)}{field("not_fit", "Not a fit", true)}</div><div className="product-field-pair">{field("price", "Price (optional)")}{field("currency", "Currency", false, 3)}</div></section>
      <div className="product-actions"><button type="submit" disabled={!!selectedProductId && !dirty}><Icon name="check"/>{busy ? "Saving…" : "Save product"}</button><button type="button" className="product-cancel" onClick={editor.cancel} disabled={!dirty}>Cancel</button><span className="product-save-state">{dirty || !selectedProductId ? "Changes not saved" : demo ? "Demo profile" : "Saved profile"}</span></div>
    </fieldset>{notice && <p role="status" className="product-feedback product-success">{notice}</p>}</form>
    <ProductPreview draft={draft} loading={loading} available={total != null}/></div>
    {!loading && total != null && <details className="saved-products"><summary>Manage saved products ({total})</summary><div><button type="button" className="product-cancel" disabled={dirty || busy || !selectedProductId} onClick={editor.create}><Icon name="plus" size={16}/>New product</button>{editor.products.map(product => <div className="saved-product-row" key={product.id}><span dir="auto">{product.name}</span>{demo ? <span className="field-hint">Demo · local only</span> : <Link href="/imports" onClick={() => localStorage.setItem("product_id", product.id)}>Select &amp; import →</Link>}</div>)}</div></details>}
  </>;
}
