import Link from "next/link";
export default function Home() {
  return <><h1>Find signals in community conversations</h1><div className="card"><p>Analyze a synthetic CSV against a product profile. This foundation uses a deterministic MockProvider and requires no API key.</p><ol className="list-decimal ml-5 mb-6 space-y-3"><li>Create or select a product.</li><li>Import the demo CSV and queue an analysis.</li><li>Watch the separate worker process messages.</li><li>Review scores, evidence and conversation context.</li></ol><Link className="button" href="/products">Start with a product</Link></div><p>Offline context can include up to three previous and two following messages from the same conversation. Mock scores are demonstration data, not measured AI accuracy.</p></>;
}
