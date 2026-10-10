import type { components } from "./generated/api";
import { request } from "./api";
export type SearchInput = components["schemas"]["SearchInput"];
export type SearchOut = components["schemas"]["SearchOut"];
export type Prospect = components["schemas"]["ProspectOut"];
export type SourceStatus = components["schemas"]["SourceStatus"];
export const discoveryApi = {
  qualify: (id: string, key: string) => request<Prospect>(`/discovery/prospects/${id}/qualify`, { method: "POST", headers: { "Idempotency-Key": key } }),
  sources: () => request<components["schemas"]["SourcesOut"]>("/discovery/sources"),
  history: () => request<SearchOut[]>("/discovery/searches?limit=20"),
  prospects: () => request<Prospect[]>("/discovery/prospects?limit=20"),
  search: (input: SearchInput, key: string) => request<SearchOut>("/discovery/searches", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(input) }),
  save: (search_id: string, source_ids: string[]) => request<Prospect[]>("/discovery/prospects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ search_id, source_ids }) }),
};
/** Do not render active links for malformed or private URL literals. No page is fetched. */
export function discoveryLink(value: string): string | null {
  try {
    const url = new URL(value), host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443") || !host.includes(".") || /^(?:\d+(?:\.\d+){3}|\[)/.test(host) || /(?:\.local|\.internal|\.localhost|\.test)$/.test(host)) return null;
    return url.href;
  } catch { return null; }
}
