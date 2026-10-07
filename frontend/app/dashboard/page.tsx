"use client";
import Icon from "@/components/Icon";
import { useWorkspaceProducts } from "@/components/useWorkspaceProducts";
import { DemoNotice, PageHeading, WorkflowLink } from "@/components/workflow/WorkflowUI";
import "@/app/workflow.css";
export default function DashboardPage() {
  const { demo } = useWorkspaceProducts();
  const suffix = demo ? "?demo=1" : "";
  return <div className="workflow-page"><PageHeading title="Workspace overview" actions={<><WorkflowLink href={`/leads${suffix}`}><Icon name="mail" size={16}/>Open lead inbox</WorkflowLink><WorkflowLink href={`/imports${suffix}`} secondary><Icon name="plus" size={16}/>New analysis</WorkflowLink></>}><p>A clear view of conversations, decisions and feedback.</p></PageHeading>
    {demo && <DemoNotice/>}
    <div className="overview-metrics">{[["20", "Messages analyzed", "chat"], ["9", "Relevant opportunities", "leads"], ["3", "Approved drafts", "check"], ["$0.00", "Mock run cost", "product"]].map(([value, label, icon]) => <div className="overview-metric" key={label}><Icon name={icon as "chat"} size={31}/><div><strong>{demo ? value : "—"}</strong><span>{label}</span></div></div>)}</div>
  </div>;
}
