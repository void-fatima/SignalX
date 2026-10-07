import Link from "next/link";
import Brand from "./Brand";

/** File/UI shell only. No simulated login, token storage or route protection. */
export default function AuthFormShell({ mode }: { mode: "login" | "register" }) {
  return <div className="card max-w-lg mx-auto"><Brand variant="large"/><h1>{mode === "login" ? "Login" : "Create account"}</h1>
    <p role="status">Authentication is not connected yet. This page is a development shell.</p>
    <fieldset disabled><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email"/>
      <label htmlFor="password">Password</label><input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"}/>
      <button type="button" className="mt-5">{mode === "login" ? "Login" : "Register"} — pending integration</button></fieldset>
    <p className="mt-4"><Link href={mode === "login" ? "/register" : "/login"}>{mode === "login" ? "Create account" : "Back to login"}</Link></p>
  </div>;
}
