"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

type Props = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
  children?: ReactNode;
};

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
  children,
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocus.current = document.activeElement as HTMLElement | null;
    if (danger) cancelRef.current?.focus();
    else confirmRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        e.preventDefault();
        onCancel();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable.length) return;
      const first = focusable[0] as HTMLElement;
      const last = focusable[focusable.length - 1] as HTMLElement;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const el = previousFocus.current;
      if (el && el.isConnected && "focus" in el) {
        (el as HTMLElement).focus();
      }
    };
  }, [open, busy, onCancel, danger]);

  if (!open) return null;

  return (
    <div
      className="modal-backdrop animate-fade-in"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div
        ref={panelRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={description ? "confirm-desc" : undefined}
        className="panel-elevated animate-scale-in w-full max-w-sm p-6"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 id="confirm-title" className="text-[1.05rem] font-medium tracking-tight text-ink">
            {title}
          </h3>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="icon-btn"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>
        {description && (
          <p id="confirm-desc" className="text-muted mb-4 text-sm leading-relaxed">
            {description}
          </p>
        )}
        {children}
        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="btn-secondary px-3 py-2 text-sm"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={() => void onConfirm()}
            disabled={busy}
            className={`btn-primary !px-3.5 !py-2 ${
              danger ? "!bg-kinexis-risk hover:!bg-kinexis-risk/90" : ""
            }`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
