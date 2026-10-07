"use client";
import Link from "next/link";
import { useState } from "react";
import Icon from "@/components/Icon";
import AuthLayout from "./AuthLayout";
import PasswordField from "./PasswordField";
export default function SignInForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return <AuthLayout mode="login"><form onSubmit={event => event.preventDefault()}><div className="auth-field"><label htmlFor="email">Email</label><div className="auth-input"><Icon name="mail" size={24}/><input id="email" type="email" name="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" placeholder="you@example.com" required maxLength={254}/></div></div><PasswordField id="password" label="Password" value={password} onChange={setPassword}/><button className="auth-primary" type="submit" disabled>Sign in<Icon name="arrow" size={25} style={{ transform: "rotate(180deg)" }}/></button><p className="auth-hint" role="status">Sign-in connection is pending implementation.</p></form><p className="auth-switch">New to SignalX? <Link href="/register">Create an account</Link></p></AuthLayout>;
}
