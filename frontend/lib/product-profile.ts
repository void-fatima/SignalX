import type { Product, ProductInput } from "./api";
export type ProductDraft = Record<"name" | "description" | "target_customer" | "problems_solved" | "best_fit" | "not_fit" | "price" | "currency", string>;
export type ProductErrors = Partial<Record<keyof ProductDraft, string>>;
export const starterProduct: ProductInput = {
  name: "Backend Academy",
  description: "A project-based backend course covering Python, FastAPI and databases.",
  target_customer: "Developers with basic Python knowledge who want to build real backend projects.",
  problems_solved: ["Moving beyond tutorials", "Learning through practical backend projects"],
  best_fit: ["Hands-on learners", "Developers ready to build an API"],
  not_fit: ["People seeking a frontend-only course", "Advanced system design specialists"],
  price: null, currency: "USD",
};
// Synthetic fixture used only when the user explicitly selects ?demo=1.
export const demoProduct: Product = { ...starterProduct, price: null, id: "demo-product-profile", created_at: "2026-10-07T00:00:00Z" };
export function toDraft(product: ProductInput): ProductDraft {
  return { name: product.name, description: product.description, target_customer: product.target_customer,
    problems_solved: (product.problems_solved || []).join("\n"), best_fit: (product.best_fit || []).join("\n"),
    not_fit: (product.not_fit || []).join("\n"), price: product.price == null ? "" : String(product.price), currency: product.currency };
}
export const lines = (value: string) => value.split("\n").map(line => line.trim()).filter(Boolean);
export function toProductInput(draft: ProductDraft): ProductInput {
  return { name: draft.name.trim(), description: draft.description.trim(), target_customer: draft.target_customer.trim(),
    problems_solved: lines(draft.problems_solved), best_fit: lines(draft.best_fit), not_fit: lines(draft.not_fit),
    price: draft.price.trim() || null, currency: draft.currency.trim().toUpperCase() };
}
export function validateProduct(draft: ProductDraft): ProductErrors {
  const errors: ProductErrors = {};
  for (const [key, max, label] of [["name", 200, "Product name"], ["description", 4000, "Description"], ["target_customer", 2000, "Target customer"]] as const) {
    if (!draft[key].trim()) errors[key] = `${label} is required.`;
    else if (draft[key].length > max) errors[key] = `Use ${max} characters or fewer.`;
  }
  if (draft.price.trim() && !/^\d{1,10}(\.\d{1,2})?$/.test(draft.price.trim())) errors.price = "Use a nonnegative price with up to 10 digits and 2 decimal places.";
  if (!/^[A-Z]{3}$/.test(draft.currency.trim().toUpperCase())) errors.currency = "Use a three-letter currency code, such as USD.";
  return errors;
}
