"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { validateRegistration } from "@/lib/auth-validation";
import Icon from "@/components/Icon";
import AuthLayout from "./AuthLayout";
import PasswordField from "./PasswordField";

export default function SignUpForm() {
  const demo = useSearchParams().get("demo") === "1";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string; confirmation?: string }>({});
  const [busy, setBusy] = useState(false), [feedback, setFeedback] = useState(""), [registered, setRegistered] = useState(false);
  function clearFeedback() { setFeedback(""); setRegistered(false); }
  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateRegistration(email, password, confirmation);
    setErrors(invalid); clearFeedback();
    if (Object.keys(invalid).length) { document.getElementById(invalid.email ? "email" : invalid.password ? "password" : "confirm-password")?.focus(); return; }
    if (demo) { setFeedback("Demo form checked. No account was created."); return; }
    setBusy(true);
    try {
      await api.register({ email: email.trim(), password });
      setRegistered(true); setPassword(""); setConfirmation("");
      setFeedback("Account created. Sign in to continue.");
    } catch (cause) { setFeedback(cause instanceof TypeError ? "Unable to reach SignalX. Check the connection and try again." : cause instanceof Error ? cause.message : "Account creation failed. Please try again."); }
    finally { setBusy(false); }
  }
  return <AuthLayout mode="register" demo={demo}><form noValidate onSubmit={createAccount} aria-busy={busy}><div className="auth-field"><label htmlFor="email">Email</label><div className={`auth-input ${errors.email ? "input-error" : ""}`}><Icon name="mail" size={24}/><input id="email" type="email" name="email" value={email} onChange={event => { setEmail(event.target.value); setErrors(current => ({ ...current, email: undefined })); clearFeedback(); }} autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder="you@example.com" required maxLength={254} disabled={busy} aria-invalid={!!errors.email} aria-describedby={errors.email ? "email-error" : undefined}/></div>{errors.email && <p id="email-error" className="field-error">{errors.email}</p>}</div><PasswordField id="password" label="Password" value={password} onChange={value => { setPassword(value); setErrors(current => ({ ...current, password: undefined, confirmation: undefined })); clearFeedback(); }} autoComplete="new-password" hint="Choose a strong, unique password. Use at least 8 characters." error={errors.password} disabled={busy}/><PasswordField id="confirm-password" label="Confirm password" value={confirmation} onChange={value => { setConfirmation(value); setErrors(current => ({ ...current, confirmation: undefined })); clearFeedback(); }} autoComplete="new-password" error={errors.confirmation} disabled={busy}/><button className="auth-primary" type="submit" disabled={busy || registered}>{busy ? "Creating account…" : registered ? "Account created" : "Create account"}<Icon name="arrow" size={25} style={{ transform: "rotate(180deg)" }}/></button>{feedback && <p className={`auth-feedback ${registered ? "success" : ""}`} role={registered || demo ? "status" : "alert"}>{feedback}</p>}{demo && <p className="auth-demo-note">Demo preview · no account is created.</p>}</form><p className="auth-switch">Already have an account? <Link href={demo ? "/login?demo=1" : "/login"}>Sign in</Link></p></AuthLayout>;
}
