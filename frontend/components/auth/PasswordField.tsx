"use client";
import { useState } from "react";
import Icon from "@/components/Icon";
export default function PasswordField({ id, label, value, onChange, autoComplete = "current-password", error, hint, disabled = false }: {
  id: string; label: string; value: string; onChange: (value: string) => void;
  autoComplete?: "current-password" | "new-password"; error?: string; hint?: string; disabled?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  return <div className="auth-field"><label htmlFor={id}>{label}</label><div className={`auth-input ${error ? "input-error" : ""}`}><Icon name="lock" size={24}/><input id={id} name={id} type={visible ? "text" : "password"} value={value} onChange={event => onChange(event.target.value)} autoComplete={autoComplete} required maxLength={128} disabled={disabled} placeholder="••••••••••" aria-invalid={!!error} aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}/><button type="button" className="password-toggle" aria-label={`${visible ? "Hide" : "Show"} ${label.toLowerCase()}`} aria-pressed={visible} onClick={() => setVisible(!visible)} disabled={disabled}><Icon name={visible ? "eye-off" : "eye"} size={24}/></button></div>{hint && <p id={`${id}-hint`} className="auth-hint">{hint}</p>}{error && <p id={`${id}-error`} className="field-error">{error}</p>}</div>;
}
