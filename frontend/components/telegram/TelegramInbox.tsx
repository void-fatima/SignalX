"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type Page } from "@/lib/api";
import { telegramApi, type TelegramLead } from "@/lib/telegram";
import Avatar from "@/components/leads/Avatar";
import TelegramBadge from "./TelegramBadge";
import "@/app/workflow.css";
import "./telegram.css";

export default function TelegramInbox() {
  const query = useSearchParams().get("q")?.toLowerCase() || "";
  const [page, setPage] = useState<Page<TelegramLead> | null>(null), [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true), [error, setError] = useState(""), [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false; setLoading(true); setError(""); setPage(null);
    telegramApi.leads(offset).then(value => { if (!cancelled) setPage(value); }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Telegram leads unavailable."); }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [offset, reload]);
  const items = (page?.items || []).filter(lead => `${lead.original_message.sender_display_name} ${lead.original_message.sender_username || ""} ${lead.original_message.chat_title || ""} ${lead.original_message.text}`.toLowerCase().includes(query));
  return <div className="telegram-inbox"><header><h1>Telegram opportunities</h1><TelegramBadge/><Link href="/leads">CSV opportunities</Link></header><p>Review the original message and evidence before approving a reply.</p>{loading && <p role="status">Loading Telegram leads…</p>}{error && <div className="workflow-error" role="alert"><p>{error}</p><button onClick={() => setReload(value => value + 1)}>Refresh leads</button> <Link href="/login">Sign in</Link></div>}{page && <><div className="workflow-table-scroll" tabIndex={0} role="region" aria-label="Telegram opportunities"><table><caption className="sr-only">Telegram leads and delivery status</caption><thead><tr><th scope="col">User</th><th scope="col">Community / message</th><th scope="col">Score</th><th scope="col">Decision</th><th scope="col">Delivery</th><th scope="col">Action</th></tr></thead><tbody>{items.map(lead => <tr key={lead.id}><td><div className="telegram-sender"><Avatar small name={lead.original_message.sender_display_name}/><div><bdi>{lead.original_message.sender_display_name}</bdi><small>{lead.original_message.sender_username ? `@${lead.original_message.sender_username}` : `Sender ${lead.original_message.sender_id}`}</small></div></div></td><td className="telegram-message-preview"><strong><bdi>{lead.original_message.chat_title || `Chat ${lead.original_message.chat_id}`}</bdi></strong><p dir="auto">{lead.original_message.text}</p></td><td>{lead.analysis.scoring?.score ?? "—"}</td><td>{lead.analysis.scoring?.decision === "RESPOND" ? "Respond" : "Review"}</td><td>{lead.delivery.delivery_uncertain ? "Uncertain" : lead.delivery.status.replace("_", " ")}</td><td><Link href={`/leads/${lead.id}?source=telegram`}>Review lead</Link></td></tr>)}</tbody></table></div>{!items.length && <p role="status">{query ? "No Telegram leads match this search on this page." : "No Telegram opportunities are available yet."}</p>}<footer><button className="secondary-button" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</button><span>{page.total ? `${offset + 1}–${Math.min(offset + page.limit, page.total)} of ${page.total}` : "0 leads"}</span><button className="secondary-button" disabled={loading || offset + page.limit >= page.total} onClick={() => setOffset(offset + 20)}>Next</button></footer></>}</div>;
}
