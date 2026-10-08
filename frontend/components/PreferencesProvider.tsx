"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { defaultPreferences, parsePreferences, preferenceKey, type Preferences } from "@/lib/preferences";
import { textDirection } from "@/lib/lead-presentation";
type PreferenceState = { preferences: Preferences; ready: boolean; stored: boolean; error: string; save: (value: Preferences) => boolean; reset: () => boolean };
const Context = createContext<PreferenceState | null>(null);
export default function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [preferences, setPreferences] = useState(defaultPreferences), [ready, setReady] = useState(false), [stored, setStored] = useState(false), [error, setError] = useState("");
  useEffect(() => {
    try { const raw = localStorage.getItem(preferenceKey); if (raw) { const value = parsePreferences(JSON.parse(raw)); if (!value) throw new Error("Invalid preferences"); setPreferences(value); setStored(true); } }
    catch { setError("Stored preferences could not be read. Default appearance is active."); }
    setReady(true);
    function sync(event: StorageEvent) { if (event.key !== preferenceKey) return; try { const value = event.newValue ? parsePreferences(JSON.parse(event.newValue)) : defaultPreferences; if (value) { setPreferences(value); setStored(!!event.newValue); setError(""); } } catch { /* Keep the last valid preferences. */ } }
    window.addEventListener("storage", sync); return () => window.removeEventListener("storage", sync);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function apply() {
      document.documentElement.dataset.theme = preferences.theme === "system" ? media.matches ? "dark" : "light" : preferences.theme;
      document.documentElement.dataset.density = preferences.density;
      document.documentElement.dataset.messageDirection = preferences.messageDirection;
    }
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [preferences, ready]);
  function save(value: Preferences) {
    const valid = parsePreferences(value);
    if (!valid) { setError("These preferences are not supported."); return false; }
    try { localStorage.setItem(preferenceKey, JSON.stringify(valid)); setPreferences(valid); setStored(true); setError(""); return true; }
    catch { setError("Browser storage is unavailable. Preferences were not saved."); return false; }
  }
  function reset() {
    try { localStorage.removeItem(preferenceKey); setPreferences(defaultPreferences); setStored(false); setError(""); return true; }
    catch { setError("Browser storage is unavailable. Preferences were not reset."); return false; }
  }
  return <Context.Provider value={{ preferences, ready, stored, error, save, reset }}>{children}</Context.Provider>;
}
export function usePreferences() {
  const value = useContext(Context);
  if (!value) throw new Error("Preferences provider is required.");
  return value;
}
export function useMessageDirection() {
  const { preferences } = usePreferences();
  return (text: string) => preferences.messageDirection === "auto" ? textDirection(text) : preferences.messageDirection;
}
