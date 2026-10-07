import AuthFormShell from "@/components/AuthFormShell";
import { Suspense } from "react";
export default function LoginPage() { return <Suspense fallback={<p className="loading-state" role="status">Loading sign in…</p>}><AuthFormShell mode="login"/></Suspense>; }
