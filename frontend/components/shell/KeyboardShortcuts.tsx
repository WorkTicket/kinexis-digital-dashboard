"use client";

import { useEffect, useCallback } from "react";
import { X } from "lucide-react";

type Shortcut = {
  keys: string[];
  label: string;
};

const shortcuts: { section: string; items: Shortcut[] }[] = [
  {
    section: "Navigation",
    items: [
      { keys: ["Ctrl", "K"], label: "Command palette" },
      { keys: ["Ctrl", ","], label: "Settings" },
      { keys: ["1"], label: "Detect (Situation)" },
      { keys: ["2"], label: "Charts" },
      { keys: ["3"], label: "Prescribe (Fix queue)" },
      { keys: ["4"], label: "Execute (Work queue)" },
      { keys: ["5"], label: "Prove (Impact)" },
      { keys: ["6"], label: "Report" },
      { keys: ["?"], label: "Keyboard shortcuts" },
    ],
  },
  {
    section: "Actions",
    items: [
      { keys: ["Esc"], label: "Close panel / cancel / dismiss" },
      { keys: ["Enter"], label: "Confirm selection in palette" },
      { keys: ["\u2191", "\u2193"], label: "Navigate palette items" },
    ],
  },
  {
    section: "Workflow shortcuts",
    items: [
      { keys: ["Detect"], label: "See what\u2019s wrong \u2192 Open Fix queue" },
      { keys: ["Prescribe"], label: "Assign here (only place) \u2192 Opens Execute" },
      { keys: ["Execute"], label: "Complete work \u2192 Snapshot saved for Prove" },
      { keys: ["Prove"], label: "Recheck impact \u2192 Causal verdict" },
      { keys: ["Report"], label: "Generate \u2192 Download PDF" },
    ],
  },
];

type Props = {
  open: boolean;
  onClose: () => void;
};

export function KeyboardShortcuts({ open, onClose }: Props) {
  const onKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", onKey);
      return () => document.removeEventListener("keydown", onKey);
    }
    return;
  }, [open, onKey]);

  if (!open) return null;

  return (
    <div className="modal-backdrop animate-fade-in" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="panel-elevated animate-scale-in w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <div>
            <p className="text-[15px] font-semibold tracking-tight text-ink">Keyboard shortcuts</p>
            <p className="text-muted mt-0.5 text-[11px]">
              Press <kbd className="kbd !text-[11px]">?</kbd> anywhere to open this
            </p>
          </div>
          <button type="button" className="icon-btn" aria-label="Close shortcuts" onClick={onClose}>
            <X size={14} strokeWidth={1.75} />
          </button>
        </div>

        <div className="space-y-5">
          {shortcuts.map((section) => (
            <div key={section.section}>
              <p className="section-label mb-2">{section.section}</p>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center justify-between rounded-lg px-3 py-2"
                    style={{ borderRadius: "var(--radius-sm)" }}
                  >
                    <span className="text-[13px] text-ink-secondary">{item.label}</span>
                    <span className="flex items-center gap-1">
                      {item.keys.map((key, ki) => (
                        <span key={ki} className="kbd">
                          {key}
                        </span>
                      ))}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <p className="text-muted mt-5 border-t border-[color:var(--border-subtle)] pt-4 text-center text-[11px] leading-relaxed">
          Tab shortcuts require a client selected. Keys 1\u20136 navigate the proof loop.
        </p>
      </div>
    </div>
  );
}
