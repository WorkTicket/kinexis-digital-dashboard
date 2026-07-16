"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

/** Form select only — use `Menu` from `@/components/ui/Menu` for action menus. */
type SelectOption = { value: string; label: string };

type SelectDropdownProps = {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
};

export function SelectDropdown({
  value,
  options,
  onChange,
  placeholder = "Select…",
  className = "",
}: SelectDropdownProps) {
  const selected = options.find((o) => o.value === value);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      setActiveIdx(0);
      return;
    }
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (!open) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, options.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" && open) {
        e.preventDefault();
        const opt = options[activeIdx];
        if (opt) {
          onChange(opt.value);
          setOpen(false);
        }
      }
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, activeIdx, options, onChange]);

  return (
    <div ref={ref} className={`relative ${open ? "z-50" : ""} ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="motion-micro flex w-full items-center justify-between gap-2 rounded-lg border border-[color:var(--border-default)] bg-surface px-3 py-2 text-sm text-ink hover:border-[color:var(--border-strong)] hover:bg-surface-elevated"
      >
        <span className={`truncate text-left ${selected ? "text-ink" : "text-muted"}`}>
          {selected?.label || placeholder}
        </span>
        <ChevronDown
          size={14}
          className={`text-muted motion-micro-transform shrink-0 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div
          ref={listRef}
          role="listbox"
          className="panel animate-scale-in absolute left-0 z-50 mt-1.5 max-h-64 w-max min-w-full max-w-xs overflow-y-auto rounded-lg py-1 shadow-dropdown"
        >
          {options.map((opt, idx) => (
            <button
              key={opt.value || "empty"}
              type="button"
              role="option"
              aria-selected={opt.value === value}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              onMouseEnter={() => setActiveIdx(idx)}
              className={`motion-micro w-full px-3 py-2 text-left text-sm ${
                opt.value === value || idx === activeIdx
                  ? "bg-[color:var(--active-fill)] text-ink"
                  : "text-ink-secondary hover:bg-[color:var(--hover-fill)] hover:text-ink"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
