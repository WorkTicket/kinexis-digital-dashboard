"use client";

import { ArrowRight, FileText, RotateCcw } from "lucide-react";
import type { ShellTab } from "@/hooks/useShellNavigation";
import { STAGE, STAGE_BLURB } from "@/lib/glossary";
import { recommendNextStep } from "@/components/LoopProgressStrip";

export type LoopStage = "detect" | "prescribe" | "execute" | "prove";

type StepCounts = {
  openIssues: number;
  openTasks: number;
  doneTasks: number;
  unprovenTasks: number;
  reportStatus: string;
};

/** Primary loop stages — Report is a destination; the loop returns to Detect. */
const LOOP_STAGES: { id: LoopStage; label: string; blurb: string }[] = [
  { id: "detect", label: STAGE.detect, blurb: STAGE_BLURB.detect },
  { id: "prescribe", label: STAGE.prescribe, blurb: STAGE_BLURB.prescribe },
  { id: "execute", label: STAGE.execute, blurb: STAGE_BLURB.execute },
  { id: "prove", label: STAGE.prove, blurb: STAGE_BLURB.prove },
];

function stageIndex(tab: ShellTab): number {
  const i = LOOP_STAGES.findIndex((s) => s.id === tab);
  return i;
}

function modeBadge(step: LoopStage, counts: StepCounts): string | null {
  switch (step) {
    case "prescribe":
      return counts.openIssues > 0 ? `${counts.openIssues}` : null;
    case "execute":
      return counts.openTasks > 0 ? `${counts.openTasks}` : null;
    case "prove":
      return counts.unprovenTasks > 0 ? `${counts.unprovenTasks}` : null;
    default:
      return null;
  }
}

function reportBadge(counts: StepCounts): string | null {
  if (counts.reportStatus === "ready") return "Ready";
  if (counts.reportStatus === "stale") return "Stale";
  if (counts.reportStatus === "draft" || counts.reportStatus === "unsaved") return "Draft";
  return null;
}

type Props = {
  activeTab: ShellTab;
  onNavigate: (tab: ShellTab) => void;
  counts: StepCounts;
};

/**
 * Closed-loop navigation for the client workspace.
 * Detect → Prescribe → Execute → Prove → Report → back to Detect.
 */
export default function StageModeRail({ activeTab, onNavigate, counts }: Props) {
  const show = activeTab !== "portfolio" && activeTab !== "settings";
  if (!show) return null;

  const onReport = activeTab === "report";
  const activeLoopIndex = stageIndex(activeTab);
  const next = recommendNextStep({
    openIssues: counts.openIssues,
    openTasks: counts.openTasks,
    doneTasks: counts.doneTasks,
    unprovenTasks: counts.unprovenTasks,
    reportStatus: counts.reportStatus,
    activeTab,
  });
  const activeBlurb =
    onReport
      ? STAGE_BLURB.report
      : LOOP_STAGES.find((s) => s.id === activeTab)?.blurb ?? STAGE_BLURB.detect;
  const showNextHint = next.tab !== activeTab;
  const loopComplete = onReport || (activeLoopIndex === LOOP_STAGES.length - 1 && counts.unprovenTasks === 0);

  return (
    <nav className="loop-rail" aria-label="Client success loop">
      <div className="loop-rail-row">
        <div className="loop-rail-track" role="tablist" aria-label="Loop stages">
          {LOOP_STAGES.map((stage, index) => {
            const isActive = !onReport && stage.id === activeTab;
            const isPast = onReport || (activeLoopIndex >= 0 && index < activeLoopIndex);
            const isRecommended = showNextHint && next.tab === stage.id;
            const badge = modeBadge(stage.id, counts);
            return (
              <div key={stage.id} className="loop-rail-step-wrap">
                {index > 0 && (
                  <span
                    className={`loop-rail-connector ${isPast || isActive ? "loop-rail-connector-lit" : ""}`}
                    aria-hidden
                  />
                )}
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  aria-current={isActive ? "step" : undefined}
                  onClick={() => onNavigate(stage.id)}
                  className={[
                    "loop-rail-step",
                    isActive ? "loop-rail-step-active" : "",
                    isPast && !isActive ? "loop-rail-step-past" : "",
                    isRecommended ? "loop-rail-step-next" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <span className="loop-rail-index" aria-hidden>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="loop-rail-label">{stage.label}</span>
                  {badge && <span className="loop-rail-badge">{badge}</span>}
                </button>
              </div>
            );
          })}
        </div>

        <div className="loop-rail-destination">
          <span className="loop-rail-destination-rule" aria-hidden />
          <button
            type="button"
            role="tab"
            aria-selected={onReport}
            aria-label={`${STAGE.report} — client pack`}
            onClick={() => onNavigate("report")}
            className={`loop-rail-report ${onReport ? "loop-rail-report-active" : ""} ${
              showNextHint && next.tab === "report" ? "loop-rail-step-next" : ""
            }`}
          >
            <FileText size={13} strokeWidth={1.75} aria-hidden />
            <span>{STAGE.report}</span>
            {reportBadge(counts) && (
              <span className="loop-rail-badge loop-rail-badge-dest">{reportBadge(counts)}</span>
            )}
            {!onReport && <ArrowRight size={12} strokeWidth={2} aria-hidden className="opacity-60" />}
          </button>
          {(onReport || loopComplete) && (
            <button
              type="button"
              className={`loop-rail-return ${next.tab === "detect" ? "loop-rail-step-next" : ""}`}
              onClick={() => onNavigate("detect")}
              aria-label="Return to Detect — start the next loop"
              title="Back to Detect"
            >
              <RotateCcw size={12} strokeWidth={2} aria-hidden />
              <span className="hidden sm:inline">Detect</span>
            </button>
          )}
        </div>
      </div>

      <div className="loop-rail-meta">
        <p className="text-caption max-w-2xl">{activeBlurb}</p>
        {showNextHint && (
          <button
            type="button"
            className="loop-rail-next-cta"
            onClick={() => onNavigate(next.tab)}
          >
            Next: {next.label}
            <ArrowRight size={12} strokeWidth={2} aria-hidden />
          </button>
        )}
      </div>
    </nav>
  );
}
