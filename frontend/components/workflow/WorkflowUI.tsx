import Link from "next/link";
export function PageHeading({ title, children, actions, date }: { title: string; children: React.ReactNode; actions?: React.ReactNode; date?: string }) {
  return <div className="workflow-heading"><div><div className="workflow-title"><h1>{title}</h1>{date && <span>{date}</span>}</div>{children}</div>{actions && <div className="workflow-actions">{actions}</div>}</div>;
}
export function Panel({ title, children, extra, className = "" }: { title: string; children: React.ReactNode; extra?: React.ReactNode; className?: string }) {
  return <section className={`workflow-panel ${className}`}><div className="panel-heading"><h2>{title}</h2>{extra}</div>{children}</section>;
}
export function DemoNotice({ children }: { children?: React.ReactNode }) {
  return <p className="workflow-notice"><span className="badge">MOCK DATA</span>{children || "Synthetic demo · no live AI processing or provider charges."}</p>;
}
export function TableScroll({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="workflow-table-scroll" role="region" aria-label={label} tabIndex={0}>{children}</div>;
}
export function WorkflowLink({ href, children, secondary = false }: { href: string; children: React.ReactNode; secondary?: boolean }) {
  return <Link className={`button ${secondary ? "workflow-secondary" : ""}`} href={href}>{children}</Link>;
}
