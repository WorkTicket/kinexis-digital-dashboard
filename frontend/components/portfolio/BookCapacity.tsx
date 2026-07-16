"use client";

import { Panel } from "@/components/ui/Panel";
import type { CapacityOwner } from "@/hooks/usePortfolioData";

type Props = {
  openWork: number;
  overdueWork: number;
  owners: CapacityOwner[];
};

const OWNER_OPEN_WARN = 8;
const OWNER_OVERDUE_WARN = 2;

export function BookCapacity({ openWork, overdueWork, owners }: Props) {
  const overloaded = owners.filter(
    (o) => o.open >= OWNER_OPEN_WARN || o.overdue >= OWNER_OVERDUE_WARN
  );
  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-label">Book capacity</h2>
        <span className="text-muted text-[11px]">
          {openWork} open · {overdueWork} overdue tasks
          {overloaded.length > 0 ? ` · ${overloaded.length} overloaded` : ""}
        </span>
      </div>
      {overloaded.length > 0 && (
        <p className="mb-2 text-[12px] text-kinexis-risk">
          Overload threshold: ≥{OWNER_OPEN_WARN} open or ≥{OWNER_OVERDUE_WARN} overdue per owner —
          rebalance before quality collapses.
        </p>
      )}
      {owners.length === 0 ? (
        <Panel padding="md">
          <p className="text-muted text-sm">No open work across the book.</p>
        </Panel>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {owners.map((o) => {
            const isOver = o.open >= OWNER_OPEN_WARN || o.overdue >= OWNER_OVERDUE_WARN;
            return (
              <div
                key={o.name}
                className={`panel flex flex-col gap-1 !p-3 ${
                  isOver ? "border border-kinexis-risk/40" : ""
                }`}
              >
                <span className="truncate text-[12px] font-medium text-ink">
                  {o.name}
                  {isOver ? " · overload" : ""}
                </span>
                <span
                  className={`font-mono-data text-[18px] font-semibold tabular-nums ${
                    isOver ? "text-kinexis-risk" : "text-ink"
                  }`}
                >
                  {o.open}
                </span>
                <span className="text-muted text-[11px]">
                  in progress
                  {o.overdue > 0 ? (
                    <span className="text-kinexis-momentum"> · {o.overdue} overdue</span>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
