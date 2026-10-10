"use client";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { clearWorkspaceSelection, verifyWorkspaceAccount } from "@/lib/workspace-session";
import { api, ApiError, type CurrentUser, type Product } from "@/lib/api";
import { WorkspaceContext } from "./WorkspaceContext";
import Brand from "./Brand";
import Icon, { type IconName } from "./Icon";
import { ReviewSessionProvider } from "./leads/ReviewSession";
const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/dashboard", label: "Overview", icon: "home" },
  { href: "/products", label: "Products", icon: "product" },
  { href: "/imports", label: "Imports", icon: "file" },
  { href: "/leads", label: "Leads", icon: "leads" },
];
export default function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const search = useSearchParams(), router = useRouter(), demo = search.get("demo") === "1";
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const sessionVersion = useRef(0);
  const [verifiedPath, setVerifiedPath] = useState("");
  const [sessionLoading, setSessionLoading] = useState(true), [sessionError, setSessionError] = useState(""), [sessionReload, setSessionReload] = useState(0);
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProductId, setSelectedProductId] = useState("");
  const [selectionLocked, setSelectionLocked] = useState(false);
  const [query, setQuery] = useState("");
  const [accountError, setAccountError] = useState("");
  const [signingOut, setSigningOut] = useState(false);
  const current = navigation.find(item => pathname.startsWith(item.href) || (item.href === "/imports" && pathname.startsWith("/runs/")));
  const auth = pathname === "/login" || pathname === "/register";
  const privatePage = navigation.some(item => pathname.startsWith(item.href)) || pathname.startsWith("/runs/") || pathname === "/settings";
  useEffect(() => {
    let cancelled = false;
    setAccountError(""); setSessionError("");
    if (demo || auth || !privatePage) { setUser(null); setSessionLoading(false); return; }
    setSessionLoading(true);
    async function check() {
      const version = ++sessionVersion.current;
      try {
        const value = await api.me();
        if (cancelled || version !== sessionVersion.current) return;
        if (typeof value.id !== "string" || typeof value.email !== "string") throw new Error("The server returned an invalid session.");
        if (verifyWorkspaceAccount(value.id)) { setProducts([]); setSelectedProductId(""); setSelectionLocked(false); }
        setUser(value); setVerifiedPath(pathname); setSessionError("");
      } catch (reason) {
        if (cancelled || version !== sessionVersion.current) return;
        setUser(null); setProducts([]); setSelectedProductId(""); setSelectionLocked(false);
        setSessionError(reason instanceof Error ? reason.message : "Session could not be verified.");
        if (reason instanceof ApiError && reason.status === 401) clearWorkspaceSelection();
      } finally { if (!cancelled && version === sessionVersion.current) setSessionLoading(false); }
    }
    function expire() {
      ++sessionVersion.current;
      setUser(null); setProducts([]); setSelectedProductId(""); setSelectionLocked(false); clearWorkspaceSelection();
      setSessionError("Your session expired. Sign in to continue."); setSessionLoading(false);
    }
    void check();
    window.addEventListener("focus", check); window.addEventListener("signalx:session-expired", expire);
    return () => { cancelled = true; ++sessionVersion.current; window.removeEventListener("focus", check); window.removeEventListener("signalx:session-expired", expire); };
  }, [demo, auth, privatePage, pathname, sessionReload]);
  useEffect(() => { setQuery(search.get("q") || ""); setOpen(false); }, [search]);
  function searchConversations(event: FormEvent) {
    event.preventDefault();
    const params = new URLSearchParams({ q: query });
    if (search.get("source") === "telegram") params.set("source", "telegram");
    if (demo) params.set("demo", "1");
    router.push(`/leads?${params}`);
  }
  async function signOut() {
    if (signingOut) return;
    if (demo) { router.push("/login?demo=1"); return; }
    setSigningOut(true); setAccountError("");
    try {
      await api.logout(); setUser(null); setProducts([]); setSelectedProductId("");
      clearWorkspaceSelection();
      router.push("/login");
    }
    catch { setAccountError("Sign out failed. Please try again."); }
    finally { setSigningOut(false); }
  }
  if (auth) return <main id="main-content" className="auth-main">{children}</main>;
  const name = demo ? "User" : user?.email.split("@")[0] || "Guest";
  const initials = demo ? "U" : name.slice(0, 1).toUpperCase();
  const modeLink = `${pathname}${demo ? "" : "?demo=1"}`;
  return <WorkspaceContext.Provider value={{ demo, user, products, setProducts, selectedProductId, setSelectedProductId, selectionLocked, setSelectionLocked, signOut, signingOut, accountError }}><div className={`workspace ${pathname === "/products" ? "workspace-products" : ""} ${["/dashboard", "/imports", "/settings"].includes(pathname) || pathname.startsWith("/runs/") ? "workspace-workflow" : ""} ${open ? "navigation-open" : ""}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar" aria-label="Workspace sidebar">
      <Brand />
      <div className="workspace-label">Workspace</div>
      <details className="workspace-picker"><summary><span className="avatar avatar-small">{name.slice(0, 1).toUpperCase()}</span><span>{demo ? "User" : "Local workspace"}</span><Icon name="chevron" size={15}/></summary><div className="workspace-picker-menu"><span>{demo ? "Synthetic demo workspace" : user ? "Connected account workspace" : "Sign in to access your products"}</span><Link href={modeLink}>{demo ? "Use connected workspace" : "Explore demo workspace"}</Link></div></details>
      <nav aria-label="Main navigation">{navigation.map(item => <Link key={item.href} href={demo ? `${item.href}?demo=1` : item.href} aria-current={current?.href === item.href ? "page" : undefined} onClick={() => setOpen(false)}><Icon name={item.icon}/>{item.label}{current?.href === item.href && <Icon name="chevron" size={16}/>}</Link>)}</nav>
      <div className="sidebar-footer"><Link className="sidebar-settings" href={demo ? "/settings?demo=1" : "/settings"} aria-current={pathname === "/settings" ? "page" : undefined} onClick={() => setOpen(false)}><Icon name="settings"/>Settings</Link><details className="sidebar-utility"><summary><Icon name="help"/>Help &amp; support</summary><p>Define a product, import a CSV, then review the signals. <Link href="/imports">Open Imports</Link></p></details><div className="workspace-profile"><span className="avatar avatar-small">{initials}</span><div><strong><bdi>{name}</bdi></strong><span>{demo ? "Demo profile" : user?.email || "Not signed in"}</span></div>{user ? <button className="account-action" onClick={signOut} type="button">Sign out</button> : <Link className="account-action" href={demo ? "/login?demo=1" : "/login"}>Account</Link>}</div>{accountError && <p role="alert">{accountError}</p>}</div>
    </aside>
    <button className={`mobile-navigation-backdrop ${open ? "is-visible" : ""}`} type="button" aria-label="Close workspace navigation" aria-hidden={!open} tabIndex={open ? 0 : -1} onClick={() => setOpen(false)}/>
    <div className="workspace-body">
      <header className="topbar">
        <button className="icon-button mobile-menu" type="button" aria-label="Toggle workspace navigation" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="menu"/></button>
        <div className="breadcrumb"><span>Workspace</span><span>/</span><strong>{current?.label || (pathname === "/settings" ? "Settings" : auth ? "Account" : "Welcome")}</strong>{search.get("source") === "telegram" && <><span>/</span><strong>Telegram</strong></>}</div>
        <form className="topbar-search" onSubmit={searchConversations} role="search"><Icon name="search" size={17}/><input type="search" aria-label="Search workspace conversations" placeholder="Search conversations…" value={query} onChange={event => setQuery(event.target.value)}/><kbd>↵</kbd></form>
        <select className="topbar-product" aria-label="Selected product" value={selectedProductId} onChange={event => setSelectedProductId(event.target.value)} disabled={selectionLocked || !products.length || (!demo && !user)} title={selectionLocked ? "Save or cancel your changes before switching products." : undefined}><option value="">{products.length ? "New product" : "Choose a product"}</option>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select>
        <span className="avatar avatar-small topbar-avatar" aria-label={demo ? "Demo profile" : name}>{initials}</span>
      </header>
      <main id="main-content" className={pathname === "/leads" ? "inbox-main" : pathname.startsWith("/leads/") ? "review-main" : pathname === "/products" ? "product-main" : "page-main"}><ReviewSessionProvider key={demo ? "demo" : user?.id || "guest"} scope={demo ? "demo" : user?.id || "guest"}><div className="workspace-route-transition" key={pathname}>{!demo && privatePage && (!user || verifiedPath !== pathname) ? <section className="session-boundary" aria-live="polite">{sessionLoading || (!!user && verifiedPath !== pathname) ? <p role="status">Checking your session...</p> : <><h1>Sign in to your workspace</h1><p role="alert">{sessionError || "A verified session is required to view this page."}</p><div className="session-actions"><Link className="button" href="/login">Sign in</Link><span className="session-or" aria-hidden="true">or</span><Link className="session-demo-link" href={`${pathname}?demo=1`}>Explore demo</Link></div><button className="session-retry" onClick={() => { setSessionLoading(true); setSessionReload(value => value + 1); }}>Retry session check</button></>}</section> : children}</div></ReviewSessionProvider></main>
    </div>
  </div></WorkspaceContext.Provider>;
}
