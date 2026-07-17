"use client";

import { useState, useEffect, useRef } from "react";
import { WifiOff, ServerCrash } from "lucide-react";

export function OfflineBanner() {
  const [browserOffline, setBrowserOffline] = useState(false);
  const [backendDown, setBackendDown] = useState(false);
  const [showBack, setShowBack] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const browserOfflineRef = useRef(false);
  const backendDownRef = useRef(false);

  useEffect(() => {
    const clearRecoveryTimer = () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const flashRestored = () => {
      setShowBack(true);
      clearRecoveryTimer();
      timerRef.current = setTimeout(() => setShowBack(false), 2200);
    };

    const recompute = (nextBrowser: boolean, nextBackend: boolean) => {
      const wasDown = browserOfflineRef.current || backendDownRef.current;
      const nowDown = nextBrowser || nextBackend;
      browserOfflineRef.current = nextBrowser;
      backendDownRef.current = nextBackend;
      setBrowserOffline(nextBrowser);
      setBackendDown(nextBackend);
      if (nowDown) {
        clearRecoveryTimer();
        setShowBack(false);
      } else if (wasDown) {
        flashRestored();
      }
    };

    if (!navigator.onLine) recompute(true, backendDownRef.current);

    const onOnline = () => recompute(false, backendDownRef.current);
    const onOffline = () => recompute(true, backendDownRef.current);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    const unsub = window.kinexis?.onBackendUnavailable?.((unavailable) => {
      recompute(browserOfflineRef.current, unavailable);
    });

    return () => {
      clearRecoveryTimer();
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      unsub?.();
    };
  }, []);

  if (!browserOffline && !backendDown && !showBack) return null;

  const message = showBack
    ? "Connection restored"
    : browserOffline
      ? "You're offline — local data still available"
      : "Kinexis backend stopped — restarting…";

  const Icon = showBack || browserOffline ? WifiOff : ServerCrash;

  return (
    <div
      role="status"
      aria-live="polite"
      className="animate-fade-up flex items-center justify-center gap-2 px-3 py-2 text-[12px] font-medium"
      style={{
        background: showBack ? "var(--kinexis-proof)" : "var(--kinexis-signal)",
        color: "var(--kinexis-ink)",
      }}
    >
      <Icon size={13} strokeWidth={1.75} />
      {message}
    </div>
  );
}
