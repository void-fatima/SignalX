"use client";
import { useEffect, useRef } from "react";
import Icon from "./Icon";

/** Native top-layer dialog: viewport centering, inert background and focus containment. */
export default function Dialog({ open, onDismiss, title, labelId, children }: {
  open: boolean; onDismiss: () => void; title: string; labelId: string; children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const backdropPress = useRef(false);
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const previousPadding = document.body.style.paddingRight;
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    if (scrollbar > 0) document.body.style.paddingRight = `${scrollbar}px`;
    dialog.showModal();
    return () => {
      dialog.close();
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPadding;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [open]);
  function outside(event: React.MouseEvent | React.PointerEvent) {
    const bounds = ref.current?.getBoundingClientRect();
    return bounds && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom);
  }
  return <dialog ref={ref} className="viewport-dialog" aria-labelledby={labelId} onCancel={event => { event.preventDefault(); onDismiss(); }} onPointerDown={event => { backdropPress.current = !!outside(event); }} onClick={event => { if (backdropPress.current && outside(event)) onDismiss(); backdropPress.current = false; }}>
    <div className="dialog-heading"><h2 id={labelId}><Icon name="review" size={32}/>{title}</h2><span className="escape-hint">Esc</span><button autoFocus type="button" className="icon-button" aria-label={`Close ${title.toLowerCase()}`} onClick={onDismiss}><Icon name="close" size={23}/></button></div>
    {children}
  </dialog>;
}
