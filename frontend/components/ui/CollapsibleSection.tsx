"use client";

import { useState, useId } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

type Props = {
  label: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  className?: string;
};

/** Density control for secondary content — chevron + label, not Show/Hide ops chrome. */
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
          className="text-muted motion-micro inline-flex items-center gap-1.5 text-xs font-medium hover:text-ink-secondary"
          aria-expanded={open}
          aria-controls={contentId}
        >
          {open ? <ChevronDown size={12} strokeWidth={2} /> : <ChevronRight size={12} strokeWidth={2} />}
          {label}
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
