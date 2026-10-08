import type { Analysis } from "@/lib/api";
const reasons: Record<string, string> = {
  provider_timeout: "The provider did not respond in time.", provider_failure: "The provider could not complete this analysis.",
  invalid_provider_output: "The provider output could not be validated.", provider_refusal: "The provider declined this analysis.",
  internal_analysis_failure: "This message could not be analyzed.",
};
export default function AnalysisFailure({ analysis }: { analysis: Analysis }) {
  return <section className="workflow-warning" role="status"><div><h2>Analysis failed</h2><p>{reasons[analysis.failure_category || ""] || "This message could not be analyzed. Check run recovery for available actions."}</p><p>No score, decision or reply is available for this failed analysis.</p></div></section>;
}
