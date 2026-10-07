"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";

export default function AuthFormShell({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false), [error, setError] = useState<Error | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError(null);
    try {
      await api.authenticate(mode, String(form.get("email")).trim(), String(form.get("password")));
      localStorage.removeItem("product_id"); localStorage.removeItem("run_id");
      router.push("/products"); router.refresh();
    } catch (error) { setError(error as Error); }
    finally { setBusy(false); }
  }
  return <div className="card max-w-lg mx-auto">
    <h1>{mode === "login" ? "Login" : "Create account"}</h1>
    <p>Sign in to manage your business profiles and analyze messages for a selected product.</p>
    <ErrorMessage error={error}/>
    <form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="email">Email</label><input id="email" name="email" type="email" required maxLength={254} autoComplete="email"/>
      <label htmlFor="password">Password</label><input id="password" name="password" type="password" required minLength={8} maxLength={128} autoComplete={mode === "login" ? "current-password" : "new-password"}/>
      <button className="mt-5">{busy ? "Working…" : mode === "login" ? "Login" : "Create account"}</button>
    </fieldset></form>
    <p className="mt-4"><Link href={mode === "login" ? "/register" : "/login"}>{mode === "login" ? "Create account" : "Back to login"}</Link></p>
  </div>;
}
