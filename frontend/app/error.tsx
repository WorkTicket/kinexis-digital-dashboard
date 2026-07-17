"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Kinexis app error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-6">
      <div className="max-w-md text-center">
        <div
          className="text-title mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-xl font-bold text-white shadow-panel-lg"
          style={{ background: "var(--brand-gradient)" }}
        >
          K
        </div>
        <h2 className="text-title mb-2">Something went wrong</h2>
        <p className="text-body mb-6 text-muted">
          {error?.message || "An unexpected error occurred."}
        </p>
        <button onClick={reset} className="btn-primary">
          Try again
        </button>
      </div>
    </div>
  );
}
