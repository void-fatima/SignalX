"use client";
import { use } from "react";
import Link from "next/link";
import RunRecovery from "@/components/RunRecovery";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <><h1>Analysis progress</h1><div className="card">
    <RunRecovery key={id} id={id}/>
    <Link href={`/leads?run_id=${id}`} onClick={() => localStorage.setItem("run_id", id)}>View results →</Link>
    <p><Link href={`/leads?run_id=${id}&status=failed`}>View failed analyses</Link></p>
  </div></>;
}
