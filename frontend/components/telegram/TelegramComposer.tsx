import Icon from "@/components/Icon";
import { useMessageDirection } from "@/components/PreferencesProvider";
import type { useTelegramReview } from "./useTelegramReview";
export default function TelegramComposer({ review }: { review: ReturnType<typeof useTelegramReview> }) {
  const { lead, draft, unavailable, busy, actionError, edit, save, generate } = review;
  const direction = useMessageDirection(), editing = draft.editingText !== null;
  const eligible = !!lead?.analysis.qualification && !!lead.analysis.scoring && lead.analysis.scoring.decision !== "IGNORE";
  return <section className="telegram-reply" aria-label="Suggested reply" aria-busy={busy !== null}><header className="telegram-reply-heading"><h2>Suggested reply <span className="badge">DRAFT</span></h2>{lead?.analysis.suggested_reply !== null && <button className="generate-reply" disabled={unavailable || editing || !eligible} onClick={() => void generate(true)}><Icon name="refresh"/>Generate again</button>}</header>
    {editing ? <><label className="sr-only" htmlFor="telegram-reply-draft">Reply draft</label><textarea autoFocus id="telegram-reply-draft" className="telegram-reply-text" dir={direction(draft.editingText!)} value={draft.editingText!} maxLength={4000} onChange={event => edit(event.target.value)}/><div className="telegram-edit-actions"><button disabled={!draft.editingText?.trim() || draft.editingText.length > 4000 || busy !== null} onClick={save}>Save reply</button><button className="secondary-button" onClick={() => edit(null)}>Cancel</button><span>{draft.editingText?.length}/4000</span></div></> : <div className="telegram-reply-text" dir={direction(draft.text)}>{draft.text || "No suggested reply has been generated. Generate a draft to review before approving."}</div>}
    {!draft.text && <button disabled={unavailable || !eligible} onClick={() => void generate(false)}>{busy === "generate" ? "Generating…" : "Generate suggested reply"}</button>}
    {draft.text && !editing && <button className="secondary-button" disabled={unavailable} onClick={() => edit(draft.text)}><Icon name="edit"/>Edit reply</button>}
    {busy === "generate" && <p role="status">Generating a suggested reply. No Telegram message is being sent.</p>}
    {editing && <p>Unsaved edits are preserved in this session. Save or cancel before regenerating.</p>}
    {!eligible && <p>Qualified analysis is required to generate a reply.</p>}
    {actionError && <p className="telegram-action-error" role="alert">{actionError}</p>}
  </section>;
}
