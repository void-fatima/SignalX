import Link from "next/link";

/** Uniform black blends into ink surfaces without a rectangular panel. */
export default function Brand({ variant = "compact", linked = true }: {
  variant?: "compact" | "large" | "mark" | "stacked"; linked?: boolean;
}) {
  const artwork = <span className={`brand brand-${variant}`} aria-label="SignalX">
    <img src={variant === "stacked" ? "/brand/signalx-stacked.png" : "/brand/signalx.png"} alt="" width={variant === "stacked" ? 1024 : 2138} height={variant === "stacked" ? 1024 : 735} />
  </span>;
  return linked ? <Link className="brand-link" href="/" aria-label="SignalX home">{artwork}</Link> : artwork;
}
