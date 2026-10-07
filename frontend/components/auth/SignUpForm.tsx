"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import Icon from "@/components/Icon";
import AuthLayout from "./AuthLayout";
import PasswordField from "./PasswordField";

export default function SignUpForm() {
  const demo = useSearchParams().get("demo") === "1";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  return <AuthLayout mode="register" demo={demo}><form onSubmit={event => event.preventDefault()}><div className="auth-field"><label htmlFor="email">Email</label><div className="auth-input"><Icon name="mail" size={24}/><input id="email" type="email" name="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder="you@example.com" required maxLength={254}/></div></div><PasswordField id="password" label="Password" value={password} onChange={setPassword} autoComplete="new-password" hint="Choose a strong, unique password."/><PasswordField id="confirm-password" label="Confirm password" value={confirmation} onChange={setConfirmation} autoComplete="new-password"/><button className="auth-primary" type="submit" disabled>Create account<Icon name="arrow" size={25} style={{ transform: "rotate(180deg)" }}/></button><p className="auth-hint" role="status">Account creation connection is pending implementation.</p></form><p className="auth-switch">Already have an account? <Link href={demo ? "/login?demo=1" : "/login"}>Sign in</Link></p></AuthLayout>;
}
