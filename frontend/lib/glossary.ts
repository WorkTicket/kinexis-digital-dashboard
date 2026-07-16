/**
 * Kinexis product glossary — master labels, blurbs, and ⌘K hints.
 *
 * Stages form a closed loop: Detect → Prescribe → Execute → Prove → Report → Detect
 * Blurbs ≤140 chars: "See X. Do Y."
 */
export const STAGE = {
  detect: "Detect",
  charts: "Charts",
  prescribe: "Prescribe",
  execute: "Execute",
  prove: "Prove",
  report: "Report",
} as const;

export const STAGE_BLURB = {
  detect: "See the next move. Open Evidence for charts & explore. Assign only in Prescribe.",
  charts: "Trend charts — open from Detect → Evidence.",
  prescribe: "The only place to Assign. Fix queue, AI plan, and briefs.",
  execute: "Work queue. Track and complete open work.",
  prove: "Before/after lift. Mark win, loss, or flat.",
  report: "Success reports. Generate a monthly PDF.",
} as const;

export const DETECT = {
  health: {
    id: "health" as const,
    label: "Overview",
    title: "Overview",
    blurb: "See health, KPIs, and the top lever. Open Fix queue to assign.",
  },
  levers: {
    id: "levers" as const,
    label: "Levers",
    title: "Growth Levers",
    blurb: "See open issues ranked by impact. Open Fix queue to assign.",
  },
  funnel: {
    id: "funnel" as const,
    label: "Funnel",
    title: "Funnel",
    blurb: "See the biggest leak. Open Fix queue to assign the fix.",
  },
  explore: {
    id: "explore" as const,
    label: "Opportunities",
    title: "Opportunities",
    blurb: "See rankings and opportunities. Open Fix queue to assign.",
  },
} as const;

export const PRESCRIBE = {
  fixes: {
    id: "fixes" as const,
    label: "Fix queue",
    title: "Fix queue",
    blurb: "One home for fixes. Assign the top playbook here.",
  },
  ai_plan: {
    id: "ai_plan" as const,
    label: "AI plan",
    title: "AI plan",
    blurb: "See why → metric → steps. Assign or skip each action.",
  },
  briefs: {
    id: "briefs" as const,
    label: "Briefs",
    title: "Briefs",
    blurb: "Writer-ready briefs. Create a task from a brief here.",
  },
} as const;

export const EXECUTE = {
  title: "Work queue",
  description: "See open work. Mark done to measure impact in Prove.",
} as const;

export const PROVE = {
  title: "Measured impact",
  description: "See before/after lift. Confirm win, loss, or flat.",
} as const;

export const REPORT = {
  narrativesTitle: "Weekly narratives",
  narrativesBlurb: "See weekly stakeholder copy. Keep monthly PDF as the primary pack.",
} as const;

export const COMMAND_HINTS = {
  detect: "Detect — health score, KPIs, top lever",
  charts: "Charts — trend data, period select, forecast",
  fixQueue: "Prescribe — Fix queue with playbooks",
  workQueue: "Execute — Work queue, track & complete",
  prove: "Prove — Measured impact, before/after lift",
  report: "Report — Success report, generate & export",
} as const;

export const PERIODS = [
  { value: "7d" as const, label: "7d" },
  { value: "30d" as const, label: "30d" },
  { value: "60d" as const, label: "60d" },
  { value: "90d" as const, label: "90d" },
  { value: "1y" as const, label: "YoY" },
] as const;
