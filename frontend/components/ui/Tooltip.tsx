"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";

type Props = {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom";
  delay?: number;
  className?: string;
};

export function Tooltip({ content, children, side = "top", delay = 400, className = "" }: Props) {
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = () => {
    timerRef.current = setTimeout(() => setVisible(true), delay);
  };

  const hide = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    hideTimerRef.current = setTimeout(() => setVisible(false), 80);
  };

  const cancelHide = () => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
  };

  useEffect(() => {
    if (!visible || !triggerRef.current) return;

    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipEl = tooltipRef.current;
    if (!tooltipEl) return;

    const tooltipRect = tooltipEl.getBoundingClientRect();
    let x: number;
    let y: number;

    if (side === "bottom") {
      x = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
      y = triggerRect.bottom + 6;
    } else {
      x = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
      y = triggerRect.top - tooltipRect.height - 6;
    }

    x = Math.max(8, Math.min(x, window.innerWidth - tooltipRect.width - 8));
    setPosition({ x, y });
  }, [visible, side]);

  useEffect(() => {
    if (!visible) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setVisible(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [visible]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, []);

  return (
    <div
      ref={triggerRef}
      className="inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      aria-describedby={visible ? "kinexis-tooltip" : undefined}
    >
      {children}
      {visible && (
        <div
          id="kinexis-tooltip"
          ref={tooltipRef}
          role="tooltip"
          className={`animate-scale-in pointer-events-none fixed z-[100] ${className}`}
          style={{ left: position.x, top: position.y }}
          onMouseEnter={cancelHide}
          onMouseLeave={hide}
        >
          <div
            className="max-w-[240px] whitespace-normal px-3 py-2 text-[11px] font-medium leading-snug text-ink shadow-dropdown"
            style={{
              borderRadius: "var(--radius-sm)",
              background: "var(--surface-elevated)",
              border: "1px solid var(--border-strong)",
            }}
          >
            {content}
          </div>
        </div>
      )}
    </div>
  );
}
