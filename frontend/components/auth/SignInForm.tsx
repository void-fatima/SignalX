"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { validateCredentials } from "@/lib/auth-validation";
import Icon from "@/components/Icon";
import AuthLayout from "./AuthLayout";
import PasswordField from "./PasswordField";

export default function SignInForm() {
  const router = useRouter(), demo = useSearchParams().get("demo") === "1";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [busy, setBusy] = useState(false), [feedback, setFeedback] = useState("");
  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invalid = validateCredentials(email, password);
    setErrors(invalid); setFeedback("");
    if (Object.keys(invalid).length) { document.getElementById(invalid.email ? "email" : "password")?.focus(); return; }
    if (demo) { setFeedback("Demo form checked. No account was signed in."); return; }
    setBusy(true);
    try {
      await api.login({ email: email.trim(), password });
      // Confirm the browser received a usable cookie before navigating.
      await api.me();
      setPassword(""); router.push("/products");
    } catch (cause) { setFeedback(cause instanceof TypeError ? "Unable to reach SignalX. Check the connection and try again." : cause instanceof Error ? cause.message : "Sign in failed. Please try again."); }
    finally { setBusy(false); }
  }
  return <AuthLayout mode="login" demo={demo}><form noValidate onSubmit={signIn} aria-busy={busy}><div className="auth-field"><label htmlFor="email">Email</label><div className={`auth-input ${errors.email ? "input-error" : ""}`}><Icon name="mail" size={24}/><input id="email" type="email" name="email" value={email} onChange={event => { setEmail(event.target.value); setErrors(current => ({ ...current, email: undefined })); setFeedback(""); }} autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder="you@example.com" required maxLength={254} disabled={busy} aria-invalid={!!errors.email} aria-describedby={errors.email ? "email-error" : undefined}/></div>{errors.email && <p id="email-error" className="field-error">{errors.email}</p>}</div><PasswordField id="password" label="Password" value={password} onChange={value => { setPassword(value); setErrors(current => ({ ...current, password: undefined })); setFeedback(""); }} error={errors.password} disabled={busy}/><button className="auth-primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}<Icon name="arrow" size={25} style={{ transform: "rotate(180deg)" }}/></button>{feedback && <p className="auth-feedback" role={demo ? "status" : "alert"}>{feedback}</p>}{demo && <p className="auth-demo-note">Demo preview · no authentication is performed.</p>}</form><p className="auth-switch">New to SignalX? <Link href={demo ? "/register?demo=1" : "/register"}>Create an account</Link></p></AuthLayout>;
}
