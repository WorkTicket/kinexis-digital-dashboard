"use client";

import { useState, useId } from "react";

type Props = {
  label: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
};

export function CollapsibleSection({
  label,
  defaultOpen = false,
  children,
  className = "",
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className={className}>
      <div className="mb-2 mt-6">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-muted motion-micro text-xs font-medium hover:text-ink-secondary"
          aria-expanded={open}
          aria-controls={contentId}
        >
          {open ? "Hide" : "Show"} {label}
        </button>
      </div>
      {open && (
        <div id={contentId} className="animate-fade-up space-y-4">
          {children}
        </div>
      )}
    </div>
  );
}
