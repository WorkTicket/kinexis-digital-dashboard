"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

type ReportSessionValue = {
  status: string;
  setStatus: (status: string) => void;
  focusGenerateKey: number;
  requestGenerateFocus: () => void;
  resetForClient: () => void;
};

const ReportSessionContext = createContext<ReportSessionValue | null>(null);

export function ReportSessionProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState("draft");
  const [focusGenerateKey, setFocusGenerateKey] = useState(0);

  const requestGenerateFocus = useCallback(() => {
    setFocusGenerateKey((k) => k + 1);
  }, []);

  const resetForClient = useCallback(() => {
    setStatus("draft");
  }, []);

  const value = useMemo(
    () => ({
      status,
      setStatus,
      focusGenerateKey,
      requestGenerateFocus,
      resetForClient,
    }),
    [status, focusGenerateKey, requestGenerateFocus, resetForClient]
  );

  return <ReportSessionContext.Provider value={value}>{children}</ReportSessionContext.Provider>;
}

export function useReportSession() {
  const ctx = useContext(ReportSessionContext);
  if (!ctx) {
    throw new Error("useReportSession must be used within ReportSessionProvider");
  }
  return ctx;
}
