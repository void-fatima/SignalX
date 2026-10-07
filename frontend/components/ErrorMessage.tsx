import { ApiError } from "@/lib/api";
export default function ErrorMessage({ error }: { error: Error | null }) {
  if (!error) return null;
  return <div role="alert" className="card error-message"><p>{error.message}</p>{error instanceof ApiError && error.details.map((d, i) => <p key={i}>{d.row ? `Row ${d.row}: ` : ""}{d.field} — {d.message}</p>)}</div>;
}
