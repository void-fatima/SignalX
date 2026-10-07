import WorkspaceShell from "@/components/WorkspaceShell";
import { Suspense } from "react";
import "./globals.css";
export const metadata = { title: "SignalX", description: "Find opportunities in community conversations" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en" dir="ltr"><body><Suspense fallback={<p className="loading-state" role="status">Loading workspace…</p>}><WorkspaceShell>{children}</WorkspaceShell></Suspense></body></html>;
}
