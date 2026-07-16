"use client";

type SkeletonProps = {
  className?: string;
};

export function Skeleton({ className = "" }: SkeletonProps) {
  return (
    <div className={`rounded-lg bg-[color:var(--border-subtle)] ${className}`} aria-hidden="true" />
  );
}

export function OverviewSkeleton() {
  return (
    <div className="animate-fade-in space-y-6" aria-busy="true" aria-label="Loading client data">
      <div className="panel-elevated overflow-hidden rounded-xl">
        <div className="flex items-center justify-between border-b border-[color:var(--border-subtle)] px-6 py-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-8 rounded-lg" />
            <div className="space-y-2">
              <Skeleton className="h-3 w-36" />
              <Skeleton className="h-3 w-52" />
            </div>
          </div>
          <Skeleton className="h-6 w-20 rounded-md" />
        </div>
        <div className="grid grid-cols-1 gap-8 p-6 lg:grid-cols-[200px_1fr]">
          <div className="flex flex-col items-center gap-3">
            <Skeleton className="h-[140px] w-[140px] rounded-full" />
            <Skeleton className="h-3 w-24" />
          </div>
          <div className="space-y-3">
            <Skeleton className="h-6 w-3/4 max-w-md" />
            <Skeleton className="h-4 w-full max-w-xl" />
            <Skeleton className="h-4 w-5/6 max-w-lg" />
            <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
              <Skeleton className="h-20 rounded-xl" />
              <Skeleton className="h-20 rounded-xl" />
              <Skeleton className="h-20 rounded-xl" />
              <Skeleton className="h-20 rounded-xl" />
            </div>
          </div>
        </div>
      </div>

      <div>
        <Skeleton className="mb-3 h-3 w-28" />
        <div className="grid grid-cols-2 gap-2.5 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[88px] rounded-xl" />
          ))}
        </div>
      </div>

      <div>
        <Skeleton className="mb-2 h-3 w-20" />
        <Skeleton className="mb-4 h-4 w-48" />
        <div className="space-y-3">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      </div>
    </div>
  );
}
