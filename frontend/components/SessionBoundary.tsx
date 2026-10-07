"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type CurrentUser } from "@/lib/api";
import ErrorMessage from "@/components/ErrorMessage";

const privatePaths = ["/products", "/imports", "/leads", "/runs", "/dashboard"];

export default function SessionBoundary({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(), router = useRouter();
  const [session, setSession] = useState<{ path: string; user: CurrentUser | null } | null>(null);
  const [error, setError] = useState<Error | null>(null), [busy, setBusy] = useState(false);
  const protectedPage = privatePaths.some(path => pathname === path || pathname.startsWith(`${path}/`));
  useEffect(() => {
    if (!protectedPage) { setSession(null); return; }
    let active = true;
    setError(null);
    api.me().then(user => {
      if (!active) return;
      if (localStorage.getItem("business_user_id") !== user.id) {
        localStorage.removeItem("product_id"); localStorage.removeItem("run_id");
      }
      localStorage.setItem("business_user_id", user.id);
      setSession({ path: pathname, user });
    }).catch(error => {
      if (!active) return;
      if (!(error instanceof ApiError && error.status === 401)) setError(error as Error);
      setSession({ path: pathname, user: null });
    });
    return () => { active = false; };
  }, [pathname, protectedPage]);
  async function logout() {
    setBusy(true); setError(null);
    try {
      await api.logout();
      for (const key of ["product_id", "run_id", "business_user_id"]) localStorage.removeItem(key);
      setSession(null); router.push("/login"); router.refresh();
    } catch (error) { setError(error as Error); }
    finally { setBusy(false); }
  }
  if (!protectedPage) return children;
  if (session?.path !== pathname) return <p role="status">Checking your session…</p>;
  if (!session.user) return <div className="card"><h1>Sign in to continue</h1><ErrorMessage error={error}/><p>Business profiles and results are private to your account.</p><Link href="/login">Login</Link><span> · </span><Link href="/register">Create account</Link></div>;
  return <><div className="flex flex-wrap items-center gap-4 mb-5"><span>Signed in as {session.user.email}</span><button className="ml-auto" onClick={logout} disabled={busy}>Sign out</button></div><ErrorMessage error={error}/>{children}</>;
}
