"use client";

import type { ReactNode } from "react";
import GrowthLeverGauge from "@/components/GrowthLeverGauge";
import type { GrowthLever, SuccessReport } from "@/lib/api";
import { motion } from "@/lib/motion";

type Stage = "detect" | "prescribe" | "execute" | "prove";

const STAGE_META: Record<Stage, { label: string; title: string }> = {
  detect: {
    label: "Opportunity",
    title: "What we found",
  },
  prescribe: {
    label: "Plan",
    title: "What we prioritized",
  },
  execute: {
    label: "Delivery",
    title: "What we shipped",
  },
  prove: {
    label: "Results",
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
      className={`report-loop-section ${motion.loadIn} ${motion.staggerClass(stagger - 1)}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="min-w-0 flex-1">
          <p
            className="text-label"
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
          <h2 className="report-loop-chapter-title mt-2 font-display font-normal text-[var(--kinexis-ink)]">
            {meta.title}
          </h2>
          <div className="mt-4 space-y-3 text-[15px] leading-relaxed text-ink-secondary">
            {children}
          </div>
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
    <div className="space-y-12">
      <LoopSection
        stage="detect"
        stagger={1}
        aside={
          topLever?.impact_score != null ? (
            <div className="report-no-print shrink-0">
              <GrowthLeverGauge
                score={topLever.impact_score}
                confidence={topLever.confidence_label ?? "medium"}
                size={72}
                label="Opportunity strength"
                className="report-gauge"
              />
            </div>
          ) : undefined
        }
      >
        {detectItems.length > 0 ? (
          <ul className="list-disc space-y-2 pl-4">
            {detectItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="text-[var(--kinexis-mist)]">
            No new opportunities highlighted for this period.
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
                  <p className="mt-2">
                    <span className="font-medium text-[var(--kinexis-focus)]">Recommended: </span>
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
          <p className="text-[var(--kinexis-mist)]">No priority locked for this period.</p>
        )}
      </LoopSection>

      <LoopSection stage="execute" stagger={3}>
        <div className="mb-4 flex flex-wrap gap-6">
          <div>
            <p className="report-kpi-value text-[var(--kinexis-ink)]">{work.tasks_completed ?? 0}</p>
            <p className="text-label mt-1">tasks done</p>
          </div>
          <div>
            <p className="report-kpi-value text-[var(--kinexis-ink)]">
              {work.insights_resolved ?? 0}
            </p>
            <p className="text-label mt-1">issues resolved</p>
          </div>
          <div>
            <p className="report-kpi-value text-[var(--kinexis-ink)]">{work.briefs_created ?? 0}</p>
            <p className="text-label mt-1">briefs</p>
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
            <div className="report-no-print shrink-0">
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
            </div>
          ) : undefined
        }
      >
        {provenLevers.length > 0 && (
          <ul className="mb-4 space-y-3">
            {provenLevers.slice(0, 3).map((l) => (
              <li key={l.id}>
                <p className="font-medium text-[var(--kinexis-ink)]">{l.title}</p>
                {l.impact_summary && (
                  <p className="mt-0.5 text-xs text-[var(--kinexis-mist)]">{l.impact_summary}</p>
                )}
              </li>
            ))}
          </ul>
        )}
        {impactWins.length === 0 ? (
          <p className="text-[var(--kinexis-mist)]">No attributed wins yet for this period.</p>
        ) : (
          <ul className="space-y-3">
            {impactWins.map((w) => (
              <li key={w.task_id} className="flex gap-3">
                <span className="report-kpi-value shrink-0 text-[var(--kinexis-proof)]">
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
