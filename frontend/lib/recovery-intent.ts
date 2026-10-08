export type RecoveryIntent = { key: string; text?: string };
export function intentSlot(action: "analysis" | "telegram", account: string, id: string) { return `signalx:intent:${action}:${account}:${id}`; }
export function readIntent(slot: string): RecoveryIntent | null {
  try { const value = JSON.parse(sessionStorage.getItem(slot) || "null"); return value && typeof value.key === "string" && value.key.length > 0 && value.key.length <= 200 ? value : null; } catch { return null; }
}
export function saveIntent(slot: string, value: RecoveryIntent) { sessionStorage.setItem(slot, JSON.stringify(value)); }
export function clearIntent(slot: string) { try { sessionStorage.removeItem(slot); } catch { /* An acknowledged key remains safe to replay. */ } }
