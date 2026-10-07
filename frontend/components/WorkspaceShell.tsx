"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import Brand from "./Brand";
import Icon, { type IconName } from "./Icon";
const navigation: { href: string; label: string; icon: IconName }[] = [
  { href: "/dashboard", label: "Overview", icon: "home" },
  { href: "/products", label: "Products", icon: "product" },
  { href: "/imports", label: "Imports", icon: "file" },
  { href: "/leads", label: "Leads", icon: "leads" },
];
export default function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const current = navigation.find(item => pathname.startsWith(item.href));
  const auth = pathname === "/login" || pathname === "/register";
  return <div className={`workspace ${open ? "navigation-open" : ""}`}>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar" aria-label="Workspace sidebar">
      <Brand />
      <div className="workspace-label">Workspace</div>
      <div className="workspace-switch"><span className="avatar avatar-small">W</span><span>Local workspace</span></div>
      <nav aria-label="Main navigation">{navigation.map(item => <Link key={item.href} href={item.href} aria-current={current?.href === item.href ? "page" : undefined} onClick={() => setOpen(false)}><Icon name={item.icon}/>{item.label}{current?.href === item.href && <Icon name="chevron" size={16}/>}</Link>)}</nav>
      <div className="sidebar-footer"><span className="eyebrow">Human review first</span><p>Every reply stays in your hands.</p><Link href="/login">Account</Link><span className="workspace-caption">Local development workspace</span></div>
    </aside>
    <div className="workspace-body">
      <header className="topbar">
        <button className="icon-button mobile-menu" type="button" aria-label="Toggle workspace navigation" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="menu"/></button>
        <div className="breadcrumb"><span>Workspace</span><span>/</span><strong>{current?.label || (auth ? "Account" : "Welcome")}</strong></div>
        <div className="topbar-note">Conversation intelligence <span className="status-dot"/></div>
      </header>
      <main id="main-content" className={pathname === "/leads" ? "inbox-main" : "page-main"}>{children}</main>
    </div>
  </div>;
}
