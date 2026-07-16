"use client";

import { ShellTab } from "@/hooks/useShellNavigation";
import { STAGE, STAGE_BLURB } from "@/lib/glossary";

/** Recommend the next loop step from current work state. */
export function recommendNextStep(opts: {
  openIssues: number;
  openTasks: number;
  doneTasks: number;
  unprovenTasks?: number;
  reportStatus?: string;
  activeTab: ShellTab;
}): { tab: ShellTab; label: string; reason: string } {
  const {
    openIssues,
    openTasks,
    doneTasks,
    unprovenTasks = doneTasks,
    reportStatus,
    activeTab,
  } = opts;
  if (openIssues > 0 && activeTab !== "prescribe") {
    return {
      tab: "prescribe",
      label: `${STAGE.prescribe} · ${openIssues} open issue${openIssues === 1 ? "" : "s"}`,
      reason: STAGE_BLURB.prescribe,
    };
  }
  if (openTasks > 0 && activeTab !== "execute") {
    return {
      tab: "execute",
      label: `${STAGE.execute} · ${openTasks} active task${openTasks === 1 ? "" : "s"}`,
      reason: STAGE_BLURB.execute,
    };
  }
  if (unprovenTasks > 0 && activeTab !== "prove" && activeTab !== "report") {
    return {
      tab: "prove",
      label: `${STAGE.prove} · ${unprovenTasks} completed, ready to measure`,
      reason: STAGE_BLURB.prove,
    };
  }
  if (reportStatus === "unsaved" || reportStatus === "stale" || reportStatus === "draft") {
    return {
      tab: "report",
      label: `${STAGE.report} · ${reportStatus === "stale" ? "data is old — refresh" : "generate or finalize"}`,
      reason: STAGE_BLURB.report,
    };
  }
  if (activeTab === "report") {
    return {
      tab: "detect",
      label: `${STAGE.detect} · review latest Situation`,
      reason: STAGE_BLURB.detect,
    };
  }
  return {
    tab: "detect",
    label: `${STAGE.detect} · start with Situation`,
    reason: STAGE_BLURB.detect,
  };
}
