export type Preferences = { theme: "dark" | "light" | "system"; accent: "violet"; density: "comfortable" | "compact"; language: "en"; messageDirection: "auto" | "ltr" | "rtl" };
export const preferenceKey = "signalx:preferences:v1";
export const defaultPreferences: Preferences = { theme: "dark", accent: "violet", density: "comfortable", language: "en", messageDirection: "auto" };
export function parsePreferences(value: unknown): Preferences | null {
  if (!value || typeof value !== "object") return null;
  const p = value as Partial<Preferences>;
  return ["dark", "light", "system"].includes(p.theme || "") && p.accent === "violet" && ["comfortable", "compact"].includes(p.density || "") && p.language === "en" && ["auto", "ltr", "rtl"].includes(p.messageDirection || "") ? { theme: p.theme!, accent: "violet", density: p.density!, language: "en", messageDirection: p.messageDirection! } : null;
}
