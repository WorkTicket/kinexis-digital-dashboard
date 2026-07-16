"use client";

import { ViewSkeleton } from "./ViewSkeleton";

type Props = {
  /** Accessible label announced while busy */
  label?: string;
  rows?: number;
  variant?: "spinner" | "cards" | "table" | "board" | "overview";
  /** Compact spinner for inline / nested panels */
  compact?: boolean;
  className?: string;
};

function Spinner({ label, compact }: { label: string; compact?: boolean }) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 ${
        compact ? "py-8" : "py-16 sm:py-20"
      }`}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <div
        className={`${
          compact ? "h-6 w-6" : "h-8 w-8"
        } animate-spin rounded-full border-2 border-[color:var(--border-default)] border-t-kinexis-focus`}
        aria-hidden
      />
      <p className="text-muted text-xs tracking-wide">{label}</p>
    </div>
  );
}

/**
 * Loading surface for the seven shells.
 * Prefer `spinner` for view-level waits; use skeleton variants for dense tables/boards.
 */
export function LoadingState({
  label = "Loading",
  rows = 4,
  variant = "spinner",
  compact = false,
  className = "",
}: Props) {
  if (variant === "spinner") {
    return (
      <div className={className}>
        <Spinner label={label} compact={compact} />
      </div>
    );
  }

  return (
    <div role="status" aria-live="polite" aria-label={label} className={className}>
      <ViewSkeleton rows={rows} variant={variant} />
      <span className="sr-only">{label}</span>
    </div>
  );
}
