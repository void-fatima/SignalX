import Link from "next/link";
import "./globals.css";
import SessionBoundary from "@/components/SessionBoundary";
export const metadata = { title: "singnalX", description: "Business-conditioned community lead discovery" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><header className="bg-white border-b border-slate-200"><nav className="max-w-5xl mx-auto p-5 flex flex-wrap items-center gap-6" aria-label="Main navigation"><Link href="/" className="font-bold text-xl">singnalX</Link><Link href="/products">Business setup</Link><Link href="/imports">Import CSV</Link><Link href="/leads">Results</Link><span className="badge ml-auto">Community lead discovery</span></nav></header><main className="max-w-5xl mx-auto p-6"><SessionBoundary>{children}</SessionBoundary></main></body></html>;
}
