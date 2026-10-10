/** Historical snapshot only: never substitute today's editable product profile. */
export default function ProductSnapshot({ snapshot }: { snapshot: Record<string, unknown> }) {
  const fields = [
    ["name", "Name"], ["description", "Description"], ["target_customer", "Target customer"],
    ["problems_solved", "Problems solved"], ["best_fit", "Best fit"], ["not_fit", "Not a fit"],
    ["price", "Supplied price"], ["currency", "Currency"],
  ];
  return <details className="product-snapshot"><summary>Product snapshot</summary>
    <p className="muted small">Profile used for this analysis. Later profile edits do not change this snapshot.</p>
    <dl>{fields.map(([key, label]) => {
      const value = snapshot[key];
      const list = Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && !!item.trim()) : null;
      const text = typeof value === "string" && value.trim() ? value : typeof value === "number" && Number.isFinite(value) ? String(value) : null;
      return <div key={key}><dt>{label}</dt><dd dir="auto">{list?.length ? <ul>{list.map((item, index) => <li key={index} dir="auto">{item}</li>)}</ul> : text || "Not supplied"}</dd></div>;
    })}</dl>
  </details>;
}
