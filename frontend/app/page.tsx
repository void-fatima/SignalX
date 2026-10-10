import Link from "next/link";
export default function Home() {
  return <><h1>Find signals in community conversations</h1><div className="card"><p>Discover and qualify potential sales leads from community messages using your product profile and real AI provider-backed analysis.</p><ol className="list-decimal ml-5 mb-6 space-y-3"><li>Create or select a product.</li><li>Import a CSV of community messages and start an analysis.</li><li>Follow the analysis as messages are processed.</li><li>Review scores, evidence and conversation context.</li></ol><Link className="button" href="/products">Start with a product</Link></div><p>Use grounded evidence and conversation context to review each potential lead before deciding how to respond.</p></>;
}
