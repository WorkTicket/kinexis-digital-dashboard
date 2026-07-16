"use client";

import { Component, type ReactNode, type ErrorInfo } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "./Button";

type Props = {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
};

type State = {
  hasError: boolean;
  error: Error | null;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="panel animate-fade-up mx-auto my-12 max-w-lg p-10 text-center">
          <div
            className="mx-auto mb-5 flex h-14 w-14 items-center justify-center border border-kinexis-risk/15 bg-kinexis-risk/[0.07] text-kinexis-risk"
            style={{ borderRadius: "var(--radius-lg)" }}
            aria-hidden
          >
            <AlertTriangle size={22} strokeWidth={1.5} />
          </div>
          <p className="text-[16px] font-semibold tracking-tight text-ink">Something went wrong</p>
          <p className="text-muted mx-auto mt-2 max-w-sm text-[14px] leading-relaxed">
            {this.state.error?.message || "An unexpected error occurred in this section."}
          </p>
          <div className="mt-6 flex justify-center">
            <Button variant="secondary" onClick={this.handleReset}>
              <RefreshCw size={13} strokeWidth={1.75} />
              Try again
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
