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
    <div className="flex min-h-screen items-center justify-center bg-[#08090c] p-6">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[#2563EB] to-[#06B6D4] text-lg font-bold text-white shadow-lg shadow-[#06B6D4]/30">
          K
        </div>
        <h2 className="mb-2 text-lg font-semibold text-[#edeef2]">Something went wrong</h2>
        <p className="mb-6 text-sm text-[#6b7080]">
          {error?.message || "An unexpected error occurred."}
        </p>
        <button
          onClick={reset}
          className="inline-flex items-center gap-2 rounded-lg bg-[#06B6D4] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#05a0bc]"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
