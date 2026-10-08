export function TelegramMark() {
  return <svg width="25" height="25" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M21.5 3.5 18 21l-6.5-5-3 3 .5-5 9-8-11 7-5-2Z"/></svg>;
}
export default function TelegramBadge() { return <span className="telegram-badge"><TelegramMark/>Telegram</span>; }
