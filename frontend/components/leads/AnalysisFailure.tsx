"use client";
import Link from "next/link";
import { useWorkspace } from "@/components/WorkspaceContext";
import type { Analysis } from "@/lib/api";
const categories: Record<string, { label: string; reason: string }> = {
  provider_timeout: { label: "Provider timeout", reason: "The provider did not respond in time." },
  provider_failure: { label: "Provider failure", reason: "The provider could not complete this analysis." },
  invalid_provider_output: { label: "Invalid provider output", reason: "The provider output could not be validated." },
  provider_refusal: { label: "Provider refusal", reason: "The provider declined this analysis." },
  internal_analysis_failure: { label: "Internal analysis failure", reason: "This message could not be analyzed." },
};
export default function AnalysisFailure({ analysis }: { analysis: Analysis }) {
  const { demo } = useWorkspace();
  // Only documented categories are safe diagnostics; never render exception text.
  const category = Object.prototype.hasOwnProperty.call(categories, analysis.failure_category || "") ? categories[analysis.failure_category!] : undefined;
  return <section className="workflow-warning" role="status"><div><h2>Analysis failed</h2><p>Failure category: {category?.label || (analysis.failure_category ? "Unrecognized category" : "Unavailable")}{category && <> (<bdi>{analysis.failure_category}</bdi>)</>}</p><p>{category?.reason || "This message could not be analyzed. Check run recovery for available actions."}</p><p>No score, decision or reply is available for this failed analysis.</p><Link className="text-action" href={`/runs/${encodeURIComponent(analysis.run_id)}${demo ? "?demo=1" : ""}`}>Open run recovery</Link></div></section>;
}
