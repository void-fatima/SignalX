import type { CSSProperties } from "react";

export type IconName = "home" | "product" | "file" | "leads" | "search" | "respond" | "review" | "chat" | "chevron" | "arrow" | "plus" | "close" | "expand" | "edit" | "copy" | "check" | "filter" | "menu" | "mail" | "lock" | "eye" | "eye-off" | "settings" | "help" | "info" | "bulb" | "ban" | "refresh" | "thumbs-up";
const paths: Record<IconName, React.ReactNode> = {
  home: <><path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z" /></>,
  product: <><path d="m12 2 9 5v10l-9 5-9-5V7Zm0 10 9-5M12 12 3 7m9 5v10" /></>,
  file: <><path d="M6 2h8l5 5v15H6Zm8 0v6h5M9 12h7m-7 4h7" /></>,
  leads: <><circle cx="9" cy="7" r="3"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M17 4a3 3 0 0 1 0 6m2 4a6 6 0 0 1 3 5v2"/></>,
  search: <><circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/></>,
  respond: <><path d="M18 7a8 8 0 0 1-11 12l-5 2 2-5A8 8 0 1 1 18 7Z"/><path d="m7 11 3 3 5-5M17 2a8 8 0 0 1 5 5M18 5a4 4 0 0 1 2 2"/></>,
  review: <><circle cx="10" cy="10" r="8"/><circle cx="10" cy="10" r="4"/><path d="m16 16 6 6"/></>,
  chat: <><path d="M3 3h18v14H9l-6 4Zm4 5h10M7 12h7"/></>,
  chevron: <path d="m9 5 7 7-7 7"/>, arrow: <path d="M20 12H4m6-6-6 6 6 6"/>,
  plus: <path d="M12 3v18M3 12h18"/>, close: <path d="m5 5 14 14M5 19 19 5"/>,
  expand: <path d="M14 3h7v7m0-7-7 7M10 21H3v-7m0 7 7-7"/>,
  edit: <><path d="m15 3 6 6L9 21H3v-6Zm-3 3 6 6M3 21l6-2-4-4"/></>,
  copy: <><rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/></>,
  check: <path d="m4 12 5 5L20 6"/>, filter: <path d="M3 3h18l-7 8v9l-4-2v-7Z"/>,
  menu: <path d="M3 5h18M3 12h18M3 19h18"/>,
  mail: <><rect x="2" y="4" width="20" height="16" rx="1"/><path d="m2 5 10 8L22 5"/></>,
  lock: <><rect x="5" y="10" width="14" height="12" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v3"/></>,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></>,
  "eye-off": <><path d="m3 3 18 18M9 5a12 12 0 0 1 3 0c6 0 10 7 10 7a17 17 0 0 1-3 4M6 6a19 19 0 0 0-4 6s4 7 10 7a12 12 0 0 0 5-1"/></>,
  settings: <><path d="m9 3 1-2h4l1 2 3 2 3 1v4l-2 2v2l2 2v4l-3 1-3 2h-6l-3-2-3-1v-4l2-2v-2-2L3 8V5l3-1Z" transform="translate(0 1) scale(.9)"/><circle cx="12" cy="12" r="3"/></>,
  help: <><circle cx="12" cy="12" r="10"/><path d="M9 8a3 3 0 1 1 4 3c-1 .5-1 1-1 3m0 3h.01"/></>,
  info: <><circle cx="12" cy="12" r="10"/><path d="M12 11v7m0-12h.01"/></>,
  bulb: <><path d="M8 17a7 7 0 1 1 8 0l-1 3H9Zm2 6h4M12 1V0M2 4l2 2M22 4l-2 2M0 12h3m18 0h3"/></>,
  ban: <><circle cx="12" cy="12" r="10"/><path d="m5 5 14 14"/></>,
  refresh: <><path d="M20 7a9 9 0 0 0-15-2L2 8m0-6v6h6M4 17a9 9 0 0 0 15 2l3-3m0 6v-6h-6"/></>,
  "thumbs-up": <><path d="M8 21H3V10h5Zm0-11 4-7c2-1 3 1 2 4l-1 3h7a2 2 0 0 1 2 2l-2 8a2 2 0 0 1-2 1H8Z"/></>,
};
export default function Icon({ name, size = 20, style }: { name: IconName; size?: number; style?: CSSProperties }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}>{paths[name]}</svg>;
}
