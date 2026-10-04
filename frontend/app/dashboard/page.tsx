import Link from "next/link";
export default function DashboardPage() {
  return <><h1>Dashboard</h1><div className="card"><p>Use the working Mock flow to create a product, import messages and inspect results.</p>
    <div className="flex flex-wrap gap-5"><Link href="/products">Products</Link><Link href="/imports">Import CSV</Link><Link href="/leads">Results</Link></div></div>
    <div className="card"><h2>Cost and quality</h2><p>Run analytics and feedback are pending backend integration. No measured accuracy or real provider cost is available.</p></div></>;
}
