"use client";

import type { ReactNode } from "react";
import GrowthLeverGauge from "@/components/GrowthLeverGauge";
import { EmptyState } from "@/components/ui/EmptyState";
import type { GrowthLever, SuccessReport } from "@/lib/api";
import { motion } from "@/lib/motion";

type Stage = "detect" | "prescribe" | "execute" | "prove";

const STAGE_META: Record<Stage, { label: string; title: string }> = {
  detect: {
    label: "Detected",
    title: "What surfaced",
  },
  prescribe: {
    label: "Prescribed",
    title: "What we chose to pull",
  },
  execute: {
    label: "Executed",
    title: "What shipped",
  },
  prove: {
    label: "Proved",
    title: "What improved",
  },
};

function LoopSection({
  stage,
  children,
  aside,
  stagger = 1,
}: {
  stage: Stage;
  children: ReactNode;
  aside?: ReactNode;
  stagger?: 1 | 2 | 3 | 4;
}) {
  const meta = STAGE_META[stage];
  return (
    <section
      className={`report-loop-section pl-5 ${motion.loadIn} ${motion.staggerClass(stagger - 1)}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p
            className="text-[12px] font-semibold"
            style={{
              color:
                stage === "detect"
                  ? "var(--kinexis-signal)"
                  : stage === "prescribe"
                    ? "var(--kinexis-focus)"
                    : stage === "execute"
                      ? "var(--kinexis-momentum)"
                      : "var(--kinexis-proof)",
            }}
          >
            {meta.label}
          </p>
          <h2 className="mt-1.5 font-display text-lg font-normal tracking-[-0.02em] text-[var(--kinexis-ink)]">
            {meta.title}
          </h2>
          <div className="mt-3 space-y-2 text-sm text-ink-secondary">{children}</div>
        </div>
        {aside}
      </div>
    </section>
  );
}

type Props = {
  report: SuccessReport;
  provenLevers: GrowthLever[];
};

export function ReportLoopNarrative({ report, provenLevers }: Props) {
  const opps = report.opportunities;
  const funnel = report.funnel;
  const growthLever = funnel?.growth_lever;
  const leak = funnel?.biggest_leak;
  const lever = growthLever
    ? growthLever
    : leak
      ? {
          stage: leak.stage,
          title: leak.stage,
          cause:
            leak.dropoff != null
              ? `${leak.dropoff}% drop-off`
              : "Largest gap vs expected conversion at this stage",
          fix: undefined as string | undefined,
        }
      : null;
  const work = report.work ?? {
    tasks_completed: 0,
    insights_resolved: 0,
    insights_open: 0,
    briefs_created: 0,
    completed_items: [] as { task_id: number; label: string }[],
  };
  const impactWins = report.impact_wins ?? [];

  const detectItems: string[] = [];
  if (opps?.rising_queries?.length) {
    const top = opps.rising_queries[0];
    if (!top) return null;
    detectItems.push(`Rising query “${top.query}” (+${top.growth_pct}%)`);
  }
  if (opps?.ctr_underperformers?.length) {
    const n = opps.ctr_underperformers.length;
    detectItems.push(`${n} CTR underperformer${n === 1 ? "" : "s"} surfaced`);
  }
  if ((work.insights_open ?? 0) > 0) {
    detectItems.push(
      `${work.insights_open} issue${work.insights_open === 1 ? "" : "s"} still open`
    );
  }

  const topLever = provenLevers[0];

  return (
    <div className="space-y-8">
      <LoopSection
        stage="detect"
        stagger={1}
        aside={
          topLever?.impact_score != null ? (
            <GrowthLeverGauge
              score={topLever.impact_score}
              confidence={topLever.confidence_label ?? "medium"}
              size={72}
              label="Detection strength"
              className="report-gauge"
            />
          ) : undefined
        }
      >
        {detectItems.length > 0 ? (
          <ul className="list-disc space-y-1.5 pl-4">
            {detectItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-[var(--kinexis-mist)]">
            No new detections highlighted for this period.
          </p>
        )}
      </LoopSection>

      <LoopSection stage="prescribe" stagger={2}>
        {lever || report.next_actions?.[0] ? (
          <>
            {lever && (
              <div>
                <p className="font-medium text-[var(--kinexis-ink)]">
                  {lever.title || lever.stage || "Growth lever"}
                </p>
                {lever.cause && <p className="mt-1 text-[var(--kinexis-mist)]">{lever.cause}</p>}
                {lever.fix && (
                  <p className="mt-2 text-sm">
                    <span className="font-medium text-[var(--kinexis-focus)]">Prescription: </span>
                    {lever.fix}
                  </p>
                )}
              </div>
            )}
            {report.next_actions?.[0]?.title && (
              <p>
                <span className="text-[var(--kinexis-mist)]">Next: </span>
                {report.next_actions[0].title}
              </p>
            )}
          </>
        ) : (
          <p className="text-[var(--kinexis-mist)]">No prescription locked for this period.</p>
        )}
      </LoopSection>

      <LoopSection stage="execute" stagger={3}>
        <div className="mb-3 flex flex-wrap gap-6">
          <div>
            <p className="font-mono text-2xl font-medium text-[var(--kinexis-ink)]">
              {work.tasks_completed ?? 0}
            </p>
            <p className="text-[12px] font-medium text-[var(--kinexis-mist)]">tasks done</p>
          </div>
          <div>
            <p className="font-mono text-2xl font-medium text-[var(--kinexis-ink)]">
              {work.insights_resolved ?? 0}
            </p>
            <p className="text-[12px] font-medium text-[var(--kinexis-mist)]">issues resolved</p>
          </div>
          <div>
            <p className="font-mono text-2xl font-medium text-[var(--kinexis-ink)]">
              {work.briefs_created ?? 0}
            </p>
            <p className="text-[12px] font-medium text-[var(--kinexis-mist)]">briefs</p>
          </div>
        </div>
        {work.completed_items && work.completed_items.length > 0 ? (
          <ul className="list-disc space-y-1 pl-4">
            {work.completed_items.slice(0, 8).map((item) => (
              <li key={item.task_id}>{item.label}</li>
            ))}
          </ul>
        ) : (
          <p className="text-[var(--kinexis-mist)]">
            No completed work items logged in this period.
          </p>
        )}
      </LoopSection>

      <LoopSection
        stage="prove"
        stagger={4}
        aside={
          topLever?.impact_score != null || impactWins[0] ? (
            <GrowthLeverGauge
              score={
                topLever?.impact_score ??
                Math.min(100, 60 + Math.abs(impactWins[0]?.avg_primary_metric_change ?? 0))
              }
              confidence={topLever?.confidence_label}
              size={80}
              label="Proven lift"
              className="report-gauge"
            />
          ) : undefined
        }
      >
        {provenLevers.length > 0 && (
          <ul className="mb-3 space-y-2">
            {provenLevers.slice(0, 3).map((l) => (
              <li key={l.id}>
                <p className="font-medium text-[var(--kinexis-ink)]">{l.title}</p>
                {l.impact_summary && (
                  <p className="text-xs text-[var(--kinexis-mist)]">{l.impact_summary}</p>
                )}
              </li>
            ))}
          </ul>
        )}
        {impactWins.length === 0 ? (
          <EmptyState
            className="!border-0 !bg-transparent !px-0 !py-4"
            title="No attributed wins yet"
            description="Complete work and recheck impact in Prove."
          />
        ) : (
          <ul className="space-y-2">
            {impactWins.map((w) => (
              <li key={w.task_id} className="flex gap-3">
                <span className="shrink-0 font-mono font-semibold text-[var(--kinexis-proof)]">
                  +{w.avg_primary_metric_change}%
                </span>
                <span>
                  {w.label}
                  {w.proof_copy && (
                    <span className="mt-0.5 block text-xs text-[var(--kinexis-mist)]">
                      {w.proof_copy}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </LoopSection>
    </div>
  );
}
