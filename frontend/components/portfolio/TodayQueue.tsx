"use client";

import { CheckCircle2, ChevronRight, ArrowUpRight } from "lucide-react";
import { TodayItem } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

function effortTone(effort?: string) {
  if (effort === "low") return "text-kinexis-proof";
  if (effort === "high") return "text-kinexis-risk";
  return "text-kinexis-signal";
}

export type TodayOpenHint = {
  tab?: string;
  insight_id?: number;
  task_id?: number;
};

type Props = {
  todayItems: TodayItem[];
  onOpenClient: (clientId: number, hint?: TodayOpenHint) => void;
  onStartTopAction?: (clientId: number) => void;
  startingClientId?: number | null;
  /** When true, render as the dominant mission-control composition */
  hero?: boolean;
};

export function TodayQueue({
  todayItems,
  onOpenClient,
  onStartTopAction,
  startingClientId = null,
  hero = false,
}: Props) {
  if (todayItems.length === 0) {
    return (
      <section className={hero ? "mission-hero" : "mb-6"}>
        {hero && (
          <div className="mb-5">
            <p className="section-label text-muted mb-1.5 text-[11px] font-semibold tracking-wide">
              Today&apos;s book
            </p>
            <h2 className="text-display text-[28px] leading-tight sm:text-[34px]">All clear</h2>
            <p className="text-muted mt-2 max-w-xl text-[14px] leading-relaxed">
              Nothing urgent queued. At-risk clients will surface here when they need a human.
            </p>
          </div>
        )}
        <div className="flex items-start gap-3 py-2">
          <CheckCircle2
            size={20}
            className="mt-0.5 shrink-0 text-kinexis-proof"
            strokeWidth={1.75}
          />
          <div>
            {!hero && <p className="text-[14px] font-semibold text-ink">All clear for today</p>}
            <p className="text-muted text-[13px] leading-relaxed">
              Capacity and the client directory are open below — scan owners and accounts, or sync
              the book to refresh detections.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className={hero ? "mission-hero" : "mb-6"} aria-label="Today's book">
      {hero && (
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="section-label text-muted mb-1.5 text-[11px] font-semibold tracking-wide">
              Today&apos;s book
            </p>
            <h2 className="text-display text-[28px] leading-tight sm:text-[34px]">
              {todayItems.length} need{todayItems.length === 1 ? "s" : ""} you
            </h2>
            <p className="text-muted mt-2 max-w-xl text-[14px] leading-relaxed">
              Ranked by risk and stuck work. Open the next move — don&apos;t browse the whole book
              first.
            </p>
          </div>
          <span className="font-mono-data text-muted text-[12px] tabular-nums">
            Showing {Math.min(todayItems.length, 12)} of {todayItems.length}
          </span>
        </div>
      )}

      {!hero && (
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-label">Today — {todayItems.length}</h2>
        </div>
      )}

      <ul className="divide-y-0">
        {todayItems.slice(0, 12).map((item, idx) => (
          <li key={item.id} className="queue-row -mx-1 rounded-[var(--radius-md)] px-2">
            <span className="font-mono-data text-muted w-5 shrink-0 text-[11px] tabular-nums">
              {String(idx + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-dim">
                  {(item.kind || "item").replace(/_/g, " ")}
                </span>
                {item.kind === "stuck_task" && <Badge tone="warning">stuck</Badge>}
                {item.kind === "contract_behind" && <Badge tone="danger">off contract</Badge>}
                {item.effort && (
                  <span className={`text-[11px] font-medium ${effortTone(item.effort)}`}>
                    {item.effort} effort
                  </span>
                )}
                <span className="text-muted truncate text-[12px] font-medium">
                  {item.client_name}
                </span>
                {item.due_date && (
                  <span className="font-mono-data text-[11px] text-kinexis-signal">
                    Due {item.due_date}
                  </span>
                )}
              </div>
              <p className="truncate text-[14px] font-semibold text-ink">{item.title}</p>
              {item.detail && (
                <p className="text-muted mt-0.5 truncate text-[12px]">{item.detail}</p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {onStartTopAction ? (
                <Button
                  variant="primary"
                  size="sm"
                  disabled={startingClientId === item.client_id}
                  onClick={() => onStartTopAction(item.client_id)}
                >
                  {startingClientId === item.client_id ? "Starting…" : "Start"}
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() =>
                    onOpenClient(item.client_id, {
                      tab: item.cta_tab,
                      insight_id: item.insight_id,
                      task_id: item.task_id,
                    })
                  }
                >
                  {item.cta}
                  {hero ? <ArrowUpRight size={13} /> : <ChevronRight size={11} />}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
