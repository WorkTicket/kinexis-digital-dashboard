"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";

export type ToastKind = "success" | "error" | "info";

type ToastAction = {
  label: string;
  onClick: () => void | Promise<void>;
};

type ToastItem = {
  id: number;
  kind: ToastKind;
  message: string;
  action?: ToastAction;
  duration: number;
};

type ToastOptions = {
  action?: ToastAction;
  duration?: number;
};

type ToastContextValue = {
  toast: (kind: ToastKind, message: string, options?: ToastOptions) => void;
  success: (message: string, options?: ToastOptions) => void;
  error: (message: string, options?: ToastOptions) => void;
  info: (message: string, options?: ToastOptions) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const remaining = useRef(item.duration);
  const started = useRef(Date.now());
  const timer = useRef<number | null>(null);
  const paused = useRef(false);

  const clear = useCallback(() => {
    if (timer.current != null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const schedule = useCallback(() => {
    clear();
    started.current = Date.now();
    timer.current = window.setTimeout(() => onDismiss(item.id), remaining.current);
  }, [clear, item.id, onDismiss]);

  useEffect(() => {
    schedule();
    return clear;
  }, [schedule, clear]);

  const pause = () => {
    if (paused.current) return;
    paused.current = true;
    remaining.current = Math.max(800, remaining.current - (Date.now() - started.current));
    clear();
  };

  const resume = () => {
    if (!paused.current) return;
    paused.current = false;
    schedule();
  };

  const Icon =
    item.kind === "success" ? CheckCircle2 : item.kind === "error" ? AlertTriangle : Info;
  const tone =
    item.kind === "success"
      ? "border-kinexis-proof/25 bg-surface-elevated text-ink"
      : item.kind === "error"
        ? "border-kinexis-risk/25 bg-surface-elevated text-ink"
        : "border-[color:var(--border-default)] bg-surface-elevated text-ink";
  const iconTone =
    item.kind === "success"
      ? "text-kinexis-proof"
      : item.kind === "error"
        ? "text-kinexis-risk"
        : "text-kinexis-focus";

  const isError = item.kind === "error";

  return (
    <div
      className={`animate-scale-in pointer-events-auto flex items-start gap-2.5 border px-3.5 py-3 ${tone}`}
      style={{ borderRadius: "var(--radius-md)" }}
      role={isError ? "alert" : "status"}
      onMouseEnter={pause}
      onMouseLeave={resume}
      onFocusCapture={pause}
      onBlurCapture={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) resume();
      }}
    >
      <Icon size={16} className={`mt-0.5 shrink-0 ${iconTone}`} />
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-relaxed">{item.message}</p>
        {item.action && (
          <button
            type="button"
            className="motion-micro mt-1.5 text-xs font-medium text-kinexis-focus hover:text-kinexis-focus/80"
            onClick={() => {
              void item.action?.onClick();
              onDismiss(item.id);
            }}
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(item.id)}
        className="icon-btn !h-7 !w-7 shrink-0"
        aria-label="Dismiss"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const toastIdRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((kind: ToastKind, message: string, options?: ToastOptions) => {
    const id = ++toastIdRef.current;
    const duration = options?.duration ?? (options?.action ? 7000 : 4200);
    setItems((prev) => [
      ...prev.slice(-4),
      { id, kind, message, action: options?.action, duration },
    ]);
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      success: (message, options) => toast("success", message, options),
      error: (message, options) => toast("error", message, options),
      info: (message, options) => toast("info", message, options),
    }),
    [toast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(100%-2rem,360px)] flex-col gap-2"
        aria-live="polite"
        aria-relevant="additions"
      >
        {items.map((item) => (
          <ToastCard key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
