import type { components } from "./generated/api";
export type Product = components["schemas"]["ProductOut"];
export type ProductInput = components["schemas"]["ProductInput"];
export type ImportResult = components["schemas"]["ImportOut"];
export type Run = components["schemas"]["RunOut"];
export type Analysis = components["schemas"]["AnalysisOut"];
export type LeadDetail = components["schemas"]["LeadDetail"];
export type CurrentUser = components["schemas"]["CurrentUser"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export class ApiError extends Error {
  constructor(message: string, public details: { row?: number; field?: string; message?: string }[] = [], public status = 0) { super(message); }
}
const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${base}${path}`, { ...options, credentials: "include", cache: "no-store" });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(body?.error?.message || `Request failed (${response.status})`, body?.error?.details || [], response.status);
  if (body === null) throw new ApiError("The server returned an unreadable response. Please try again.");
  return body as T;
}
export const api = {
  me: () => request<CurrentUser>("/auth/me"),
  authenticate: (mode: "login" | "register", email: string, password: string) => request<CurrentUser>(`/auth/${mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  products: (offset = 0, limit = 100) => request<Page<Product>>(`/products?limit=${limit}&offset=${offset}`),
  product: (id: string) => request<Product>(`/products/${id}`),
  saveProduct: (body: ProductInput, id?: string) => request<Product>(id ? `/products/${id}` : "/products", { method: id ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  importCSV: (data: FormData) => request<ImportResult>("/imports", { method: "POST", body: data }),
  startRun: (product_id: string, batch_id: string, key: string) => request<Run>("/analysis/runs", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify({ product_id, batch_id }) }),
  run: (id: string) => request<Run>(`/analysis/runs/${id}`),
  leads: (run: string, decision: string, offset: number, minScore: string) => request<Page<Analysis>>(`/leads?run_id=${encodeURIComponent(run)}&offset=${offset}${decision ? `&decision=${decision}` : ""}${minScore ? `&min_score=${minScore}` : ""}`),
  lead: (id: string) => request<LeadDetail>(`/leads/${id}`),
};
