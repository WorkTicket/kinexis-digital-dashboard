"use client";

import { useCallback, useRef, type KeyboardEvent } from "react";

type Option<T extends string> = {
  id: T;
  label: string;
  count?: number;
  badge?: string;
  icon?: React.ReactNode;
};

type Props<T extends string> = {
  options: Option<T>[];
  value: T;
  onChange: (id: T) => void;
  ariaLabel?: string;
  size?: "sm" | "md";
  variant?: "segmented" | "subnav";
};

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel = "Sections",
  size = "md",
  variant = "segmented",
}: Props<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const focusAt = useCallback((index: number) => {
    const el = refs.current[index];
    el?.focus();
  }, []);

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
      if (options.length === 0) return;
      let next = index;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        next = (index + 1) % options.length;
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        next = (index - 1 + options.length) % options.length;
      } else if (e.key === "Home") {
        e.preventDefault();
        next = 0;
      } else if (e.key === "End") {
        e.preventDefault();
        next = options.length - 1;
      } else {
        return;
      }
      const nextOption = options[next];
      if (!nextOption) return;
      onChange(nextOption.id);
      focusAt(next);
    },
    [focusAt, onChange, options]
  );

  if (variant === "subnav") {
    return (
      <div
        role="radiogroup"
        aria-label={ariaLabel}
        className="flex max-w-full flex-wrap gap-1.5 overflow-x-auto"
      >
        {options.map((opt, i) => {
          const active = value === opt.id;
          return (
            <button
              key={opt.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(opt.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`subnav-link ${active ? "subnav-link-active" : "subnav-link-idle"}`}
            >
              {opt.icon}
              <span>{opt.label}</span>
              {opt.badge ? (
                <span className="font-mono-data text-xs opacity-70">{opt.badge}</span>
              ) : typeof opt.count === "number" && opt.count > 0 ? (
                <span className="font-mono-data text-xs opacity-70">{opt.count}</span>
              ) : null}
            </button>
          );
        })}
      </div>
    );
  }

  const item = size === "sm" ? "px-3 py-1.5 text-xs" : "px-3.5 py-2 text-[13px]";

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex max-w-full gap-1 overflow-x-auto border border-[color:var(--border-subtle)] bg-surface-lighter/80 p-1"
      style={{ borderRadius: "var(--radius-lg)" }}
    >
      {options.map((opt, i) => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(opt.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`inline-flex items-center gap-1.5 ${item} motion-micro whitespace-nowrap font-medium ${
              active
                ? "bg-surface-light text-ink shadow-panel"
                : "text-muted hover:text-ink-secondary"
            }`}
            style={{ borderRadius: "var(--radius-md)" }}
          >
            {opt.icon}
            <span>{opt.label}</span>
            {opt.badge ? (
              <span
                className={`font-mono-data text-xs ${active ? "text-kinexis-focus" : "text-muted"}`}
              >
                {opt.badge}
              </span>
            ) : typeof opt.count === "number" && opt.count > 0 ? (
              <span
                className={`font-mono-data min-w-[1rem] text-center text-xs ${
                  active ? "text-kinexis-focus" : "text-muted"
                }`}
              >
                {opt.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
