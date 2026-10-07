import WorkspaceShell from "@/components/WorkspaceShell";
import "./globals.css";
export const metadata = { title: "SignalX", description: "Find opportunities in community conversations" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en" dir="ltr"><body><WorkspaceShell>{children}</WorkspaceShell></body></html>;
}
