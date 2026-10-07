import Link from "next/link";
import Brand from "./Brand";
import SignInForm from "./auth/SignInForm";

/** Account creation is filled in by the next stacked feature branch. */
export default function AuthFormShell({ mode }: { mode: "login" | "register" }) {
  if (mode === "login") return <SignInForm/>;
  return <div className="card max-w-lg mx-auto"><Brand variant="large"/><h1>Create account</h1>
    <p role="status">Authentication is not connected yet. This page is a development shell.</p>
    <fieldset disabled><label htmlFor="email">Email</label><input id="email" type="email" autoComplete="email"/>
      <label htmlFor="password">Password</label><input id="password" type="password" autoComplete="new-password"/>
      <button type="button" className="mt-5">Register — pending integration</button></fieldset>
    <p className="mt-4"><Link href="/login">Back to login</Link></p>
  </div>;
}
