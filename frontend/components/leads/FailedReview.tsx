import Link from "next/link";
export default function FailedReview({ runId, demo }: { runId: string; demo: boolean }) {
  return <section className="reply-panel"><h2>Analysis recovery</h2><p>Failed messages have no reply to approve. Successful results are preserved when you explicitly retry eligible work from the run page.</p><Link className="reply-expand-link" href={`/runs/${encodeURIComponent(runId)}${demo ? "?demo=1&state=partial" : ""}`}>Open run recovery</Link></section>;
}
