import Link from "next/link";

/** Uniform black blends into ink surfaces without a rectangular panel. */
export default function Brand({ variant = "compact", linked = true }: {
  variant?: "compact" | "large" | "mark"; linked?: boolean;
}) {
  const artwork = <span className={`brand brand-${variant}`} aria-label="SignalX">
    <img src="/brand/signalx.png" alt="" width="2138" height="735" />
  </span>;
  return linked ? <Link className="brand-link" href="/" aria-label="SignalX home">{artwork}</Link> : artwork;
}
