import { useState } from "react";
import Icon from "@/components/Icon";
import Dialog from "@/components/Dialog";
import Avatar from "@/components/leads/Avatar";
import { useMessageDirection } from "@/components/PreferencesProvider";
import type { TelegramLead } from "@/lib/telegram";
import TelegramBadge, { TelegramMark } from "./TelegramBadge";
import TelegramMessageText from "./TelegramMessageText";

export function TelegramDestination({ lead }: { lead: TelegramLead }) {
  const m = lead.original_message;
  return <section className="telegram-destination"><h2>Reply destination</h2><div><Icon name="arrow" size={25}/><span className="telegram-circle"><TelegramMark/></span><div><h3><bdi>{m.chat_title || `Chat ${m.chat_id}`}</bdi></h3><p>Reply to Message {m.message_id}{m.message_thread_id !== null && ` · Topic ${m.message_thread_id}`}</p></div><p className="telegram-chat-id">Chat {m.chat_id}{m.message_thread_id !== null && <><br/>Topic {m.message_thread_id}</>}</p></div></section>;
}

export default function TelegramSource({ lead }: { lead: TelegramLead }) {
  const [open, setOpen] = useState(false), direction = useMessageDirection();
  const m = lead.original_message, analysis = lead.analysis, scoring = analysis.scoring;
  const evidence = analysis.qualification?.evidence || [];
  return <section className="review-source telegram-source" aria-label="Original Telegram message">
    <div className="review-identity"><Avatar name={m.sender_display_name}/><div><h2><bdi>{m.sender_display_name}</bdi></h2><p className="telegram-username">{m.sender_username ? <bdi>@{m.sender_username}</bdi> : `Sender ${m.sender_id}`}</p></div><TelegramBadge/></div>
    <div className="telegram-community"><Icon name="leads" size={30}/><div><h3><bdi>{m.chat_title || `Chat ${m.chat_id}`}</bdi></h3><p>Chat {m.chat_id} · Message {m.message_id}{m.message_thread_id !== null && ` · Topic ${m.message_thread_id}`}</p></div></div>
    <section className="telegram-original"><header><h3>Original message</h3><time dateTime={m.timestamp}>{new Date(m.timestamp).toLocaleString("en-GB", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })} UTC</time></header><blockquote dir={direction(m.text)}><TelegramMessageText lead={lead}/></blockquote></section>
    <section className="telegram-signal"><h3><Icon name="review" size={27}/>Signal analysis</h3><div><span className="telegram-score"><strong>{scoring?.score ?? "—"}</strong><span>/100</span></span><span className={`decision decision-${scoring?.decision.toLowerCase() || "unknown"}`}>{scoring?.decision === "RESPOND" || scoring?.decision === "REVIEW" ? <Icon name={scoring.decision === "RESPOND" ? "respond" : "review"} size={25}/> : null}{scoring?.decision === "RESPOND" ? "Respond" : scoring?.decision === "REVIEW" ? "Review" : scoring?.decision === "IGNORE" ? "Skip" : "Unavailable"}</span></div><p dir="auto">{analysis.decision_reason || "Decision explanation unavailable."}</p><button className="text-action" onClick={() => setOpen(true)}>View analysis <Icon name="chevron" size={18}/></button></section>
    <section className="telegram-evidence"><h3>Evidence</h3>{evidence.length === 0 && <p>No evidence returned.</p>}{evidence.map((e, i) => <div key={`${e.message_id}:${i}`}><span className="telegram-evidence-number">{i + 1}</span><div><strong>{e.message_id === lead.message_id ? "Message content" : "Context message"}</strong><p dir="auto">{e.reason}</p></div><blockquote dir={direction(e.quote)}>“{e.quote}”</blockquote></div>)}</section>
    <Dialog open={open} onDismiss={() => setOpen(false)} title="Telegram signal analysis" labelId="telegram-analysis-title"><div className="telegram-analysis-details"><p dir="auto">{analysis.decision_reason || "Decision explanation unavailable."}</p>{analysis.qualification && <><h3>Qualification</h3><p dir="auto">{analysis.qualification.need}</p><p>Intent: <bdi>{analysis.qualification.intent}</bdi></p><dl>{(["purchase_intent", "product_fit", "need_strength", "urgency", "confidence", "response_opportunity"] as const).map(key => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{analysis.qualification![key]}</dd></div>)}</dl>{analysis.qualification.limitations.map((text, i) => <p key={i} dir="auto">{text}</p>)}</>}<h3>Conversation context</h3>{lead.context.length ? lead.context.map(message => <div key={message.id}><strong><bdi>{message.author}</bdi></strong><p dir={direction(message.content)}>{message.content}</p></div>) : <p>No additional context returned.</p>}<p>Prompt: {analysis.prompt_version || "Unavailable"} · Scoring: {analysis.scoring_version || "Unavailable"}</p></div></Dialog>
  </section>;
}
