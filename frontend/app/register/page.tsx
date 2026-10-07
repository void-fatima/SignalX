import AuthFormShell from "@/components/AuthFormShell";
import { Suspense } from "react";
export default function RegisterPage() { return <Suspense fallback={<p className="loading-state" role="status">Loading account creation…</p>}><AuthFormShell mode="register"/></Suspense>; }
