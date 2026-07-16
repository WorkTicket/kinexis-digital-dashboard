"use client";

import type { ShellTab } from "@/hooks/useShellNavigation";
import { STAGE } from "@/lib/glossary";

type StepCounts = {
  openIssues: number;
  openTasks: number;
  doneTasks: number;
  unprovenTasks: number;
  reportStatus: string;
};

const MODES: { id: ShellTab; label: string }[] = [
  { id: "detect", label: STAGE.detect },
  { id: "prescribe", label: STAGE.prescribe },
  { id: "execute", label: STAGE.execute },
  { id: "prove", label: STAGE.prove },
  { id: "report", label: STAGE.report },
];

function modeBadge(step: ShellTab, counts: StepCounts): string | null {
  switch (step) {
    case "prescribe":
      return counts.openIssues > 0 ? `${counts.openIssues}` : null;
    case "execute":
      return counts.openTasks > 0 ? `${counts.openTasks}` : null;
    case "prove":
      return counts.unprovenTasks > 0 ? `${counts.unprovenTasks}` : null;
    case "report":
      return counts.reportStatus === "ready" ? "Ready" : null;
    default:
      return null;
  }
}

type Props = {
  activeTab: ShellTab;
  onNavigate: (tab: ShellTab) => void;
  counts: StepCounts;
};

/** Compact stage mode switcher for the client war room — not a chip stepper. */
export default function StageModeRail({ activeTab, onNavigate, counts }: Props) {
  const show = activeTab !== "portfolio" && activeTab !== "settings";
  if (!show) return null;

  return (
    <nav className="stage-mode-rail" aria-label="Client stage">
      <div className="stage-mode-rail-track" role="tablist">
        {MODES.map((mode) => {
          const isActive = mode.id === activeTab;
          const badge = modeBadge(mode.id, counts);
          return (
            <button
              key={mode.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onNavigate(mode.id)}
              className={`stage-mode-btn ${isActive ? "stage-mode-btn-active" : ""}`}
            >
              {mode.label}
              {badge && <span className="stage-mode-badge">{badge}</span>}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
