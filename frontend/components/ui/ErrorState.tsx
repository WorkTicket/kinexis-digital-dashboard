"use client";

import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./Button";
import { Panel } from "./Panel";

type Props = {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
};

export function ErrorState({
  title = "Something went wrong",
  description = "We couldn’t load this data. Check your connection and try again.",
  onRetry,
  className = "",
}: Props) {
  return (
    <Panel className={`py-10 text-center ${className}`.trim()}>
      <div className="mb-3 flex justify-center text-kinexis-risk" aria-hidden>
        <AlertCircle size={28} strokeWidth={1.75} />
      </div>
      <p className="font-medium text-ink-secondary">{title}</p>
      <p className="text-muted mx-auto mt-1.5 max-w-md text-sm leading-relaxed">{description}</p>
      {onRetry && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <RefreshCw size={14} />
            Retry
          </Button>
        </div>
      )}
    </Panel>
  );
}
