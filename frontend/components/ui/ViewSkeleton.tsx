"use client";

import { Skeleton } from "@/components/Skeleton";
import { Panel } from "./Panel";

type Props = {
  rows?: number;
  className?: string;
  variant?: "cards" | "table" | "board" | "overview" | "report" | "plan";
};

export function ViewSkeleton({ rows = 4, className = "", variant = "cards" }: Props) {
  if (variant === "overview") {
    return (
      <div className={`animate-fade-in space-y-6 ${className}`.trim()} aria-busy="true">
        <Panel elevated padding="lg">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[180px_1fr]">
            <div className="flex flex-col items-center gap-3">
              <Skeleton className="h-[140px] w-[140px] rounded-full" />
              <Skeleton className="h-3 w-24" />
            </div>
            <div className="space-y-3">
              <Skeleton className="h-6 w-3/4 max-w-md" />
              <Skeleton className="h-4 w-full max-w-xl" />
              <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
                <Skeleton className="h-20 rounded-xl" />
                <Skeleton className="h-20 rounded-xl" />
              </div>
            </div>
          </div>
        </Panel>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (variant === "report") {
    return (
      <div className={`animate-fade-in space-y-6 ${className}`.trim()} aria-busy="true">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Panel className="space-y-3 md:col-span-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-72" />
            <div className="grid grid-cols-2 gap-3 pt-2">
              <Skeleton className="h-12 rounded-lg" />
              <Skeleton className="h-12 rounded-lg" />
            </div>
          </Panel>
          <Panel className="space-y-3">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-3 w-32" />
          </Panel>
        </div>
        <Panel className="space-y-4">
          <Skeleton className="h-5 w-40" />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
            <Skeleton className="h-24 rounded-xl" />
          </div>
        </Panel>
        <Panel className="space-y-3">
          <Skeleton className="h-5 w-36" />
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </Panel>
      </div>
    );
  }

  if (variant === "plan") {
    return (
      <div className={`animate-fade-in space-y-4 ${className}`.trim()} aria-busy="true">
        <div className="flex items-center justify-between">
          <Skeleton className="h-6 w-44" />
          <Skeleton className="h-9 w-32 rounded-lg" />
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <Panel key={i} className="space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-5 w-56" />
                <Skeleton className="h-3 w-full max-w-md" />
              </div>
              <Skeleton className="h-6 w-16 shrink-0 rounded-full" />
            </div>
            <div className="flex gap-2">
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-6 w-24 rounded-full" />
            </div>
            <Skeleton className="h-3 w-3/4" />
          </Panel>
        ))}
      </div>
    );
  }

  if (variant === "table") {
    return (
      <Panel
        padding={false}
        className={`animate-fade-in overflow-hidden ${className}`.trim()}
        aria-busy
      >
        <div className="flex gap-4 border-b border-[color:var(--border-subtle)] px-4 py-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 w-16" />
        </div>
        <div className="divide-y divide-[color:var(--border-subtle)]">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="flex items-center gap-4 px-4 py-3.5">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="ml-auto h-4 w-16" />
              <Skeleton className="h-4 w-12" />
            </div>
          ))}
        </div>
      </Panel>
    );
  }

  if (variant === "board") {
    return (
      <div
        className={`animate-fade-in grid grid-cols-1 gap-4 md:grid-cols-3 ${className}`.trim()}
        aria-busy
      >
        {Array.from({ length: 3 }).map((_, col) => (
          <Panel key={col} padding="sm" className="min-h-[200px] space-y-2">
            <Skeleton className="mb-3 h-3 w-20" />
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-lg" />
            ))}
          </Panel>
        ))}
      </div>
    );
  }

  return (
    <div className={`animate-fade-in space-y-3 ${className}`.trim()} aria-busy>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-24 rounded-xl" />
      ))}
    </div>
  );
}
