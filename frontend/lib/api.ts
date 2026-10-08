import type { components } from "./generated/api";
import type { components as handoff } from "./generated/failure-api";
export type Product = components["schemas"]["ProductOut"];
export type ProductInput = components["schemas"]["ProductInput"];
export type ImportResult = components["schemas"]["ImportOut"];
export type Run = components["schemas"]["RunOut"] & Partial<Pick<handoff["schemas"]["RunOut"], "attempt_no">>;
export type Analysis = handoff["schemas"]["AnalysisOut"];
export type LeadDetail = Omit<handoff["schemas"]["LeadDetail"], "source"> & { source?: "csv" | "telegram" };
export type Credentials = components["schemas"]["Credentials"];
export type CurrentUser = components["schemas"]["CurrentUser"];
export type SessionGrant = components["schemas"]["SessionGrant"];
export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
export class ApiError extends Error {
  constructor(message: string, public details: { row?: number; field?: string; message?: string }[] = [], public status = 0, public code = "") { super(message); }
}
const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
export async function request<T>(path: string, options: RequestInit = {}, endpoint = base): Promise<T> {
  const response = await fetch(`${endpoint}${path}`, { ...options, credentials: "include", cache: "no-store" });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => { throw new ApiError(`The server returned an unreadable response (${response.status}).`, [], response.status, "unreadable_response"); });
  if (!response.ok) throw new ApiError(body.error?.message || `Request failed (${response.status})`, body.error?.details || [], response.status, body.error?.code || "");
  return body as T;
}
export const api = {
  login: (body: Credentials) => request<CurrentUser | SessionGrant>("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  register: (body: Credentials) => request<CurrentUser>("/auth/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  me: () => request<CurrentUser>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  products: (offset = 0, limit = 100) => request<Page<Product>>(`/products?limit=${limit}&offset=${offset}`),
  product: (id: string) => request<Product>(`/products/${id}`),
  saveProduct: (body: ProductInput, id?: string) => request<Product>(id ? `/products/${id}` : "/products", { method: id ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  importCSV: (data: FormData) => request<ImportResult>("/imports", { method: "POST", body: data }),
  startRun: (product_id: string, batch_id: string, key: string) => request<Run>("/analysis/runs", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify({ product_id, batch_id }) }),
  run: (id: string) => request<Run>(`/analysis/runs/${id}`),
  leads: (run: string, decision: string, offset: number, minScore: string, status = "") => request<Page<Analysis>>(`/leads?run_id=${encodeURIComponent(run)}&offset=${offset}${status === "failed" ? "&status=failed" : decision ? `&decision=${decision}` : ""}${status !== "failed" && minScore ? `&min_score=${minScore}` : ""}`),
  retryRun: (id: string, key: string) => request<Run>(`/analysis/runs/${encodeURIComponent(id)}/retry`, { method: "POST", headers: { "Idempotency-Key": key } }),
  lead: (id: string) => request<LeadDetail>(`/leads/${id}`),
};
