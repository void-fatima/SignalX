import Icon from "../Icon";
import { lines, type ProductDraft } from "@/lib/product-profile";
export default function ProductPreview({ draft, loading, available }: { draft: ProductDraft; loading: boolean; available: boolean }) {
  function criteria(key: "best_fit" | "not_fit", title: string) {
    const items = lines(draft[key]);
    return <section><h3>{title}</h3>{items.length ? <ul>{items.map((item, index) => <li key={`${index}-${item}`}><span className={key === "best_fit" ? "fit-check" : "not-fit-icon"}><Icon name={key === "best_fit" ? "check" : "ban"} size={17}/></span><span dir="auto">{item}</span></li>)}</ul> : <p className="preview-empty">No criteria added yet.</p>}</section>;
  }
  return <aside className="product-preview-column" aria-label="Live product profile preview"><div className="product-preview">
    <div className="preview-corner" aria-hidden="true"/>
    <header><span className="preview-product-icon"><Icon name="product" size={31}/></span><div><span className="eyebrow">Profile preview</span><h2 dir="auto">{available ? draft.name.trim() || "Untitled product" : "Product unavailable"}</h2></div></header>
    {loading ? <p className="preview-empty">Loading the selected product…</p> : !available ? <p className="preview-empty">Load your products or explicitly explore the demo to view a profile.</p> : <>
      <p className="preview-description" dir="auto">{draft.description.trim() || "Add a description to introduce your product."}</p>
      <section><h3>Designed for</h3><p dir="auto">{draft.target_customer.trim() || "Describe who this product helps."}</p></section>
      {criteria("best_fit", "Best fit")}{criteria("not_fit", "Not a fit")}
      <footer><Icon name="info" size={19}/><span>This profile guides conversation matching.</span></footer>
    </>}
  </div><div className="product-guidance"><Icon name="bulb" size={29}/><div><h3>Make the boundaries clear</h3><p>Specific fit criteria help separate useful conversations from noise.</p></div></div></aside>;
}
