export type RunContext = { product: string; community: string; filename: string; total: number };
export function saveRunContext(id: string, value: RunContext) {
  try { sessionStorage.setItem(`signalx:run:${id}`, JSON.stringify(value)); } catch { /* Run still exists if browser storage is unavailable. */ }
}
export function readRunContext(id: string): RunContext | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(`signalx:run:${id}`) || "null");
    return value && typeof value.product === "string" && typeof value.community === "string" && typeof value.filename === "string" && Number.isInteger(value.total) && value.total > 0 ? value : null;
  } catch { return null; }
}
