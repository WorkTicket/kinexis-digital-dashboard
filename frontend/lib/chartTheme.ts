/**
 * Shared Recharts theme — reads Kinexis semantic CSS tokens.
 */

export const CHART = {
  focus: "var(--kinexis-focus)",
  focusSoft: "color-mix(in srgb, var(--kinexis-focus) 70%, transparent)",
  signal: "var(--kinexis-signal)",
  proof: "var(--kinexis-proof)",
  risk: "var(--kinexis-risk)",
  momentum: "var(--kinexis-momentum)",
  mist: "var(--muted)",
  gridOpacity: 0.45,
  axisFill: "var(--muted)",
  monoFamily: "var(--font-mono), ui-monospace, monospace",
} as const;

export type ChartRole = "focus" | "signal" | "proof" | "risk" | "momentum" | "mist";

export function chartColor(role: ChartRole = "focus"): string {
  return CHART[role];
}

export function chartToneForDelta(delta: number | null | undefined): string {
  if (delta == null || delta === 0) return CHART.mist;
  if (delta > 0) return CHART.proof;
  return CHART.risk;
}

export function chartHealthRingTone(score: number): string {
  if (score >= 70) return CHART.focus;
  if (score >= 55) return CHART.signal;
  if (score > 0) return CHART.risk;
  return CHART.mist;
}

export function chartPageSpeedTone(score: number): string {
  if (score >= 90) return CHART.proof;
  if (score >= 70) return CHART.signal;
  if (score >= 50) return CHART.momentum;
  return CHART.risk;
}

export const chartRingTrack = "var(--border-subtle, var(--surface-border))";

export const chartAxisTick = {
  fontSize: 11,
  fill: CHART.axisFill,
  fontFamily: CHART.monoFamily,
} as const;

export const chartGridProps = {
  strokeDasharray: "4 4" as const,
  stroke: "var(--border-subtle, var(--surface-border))",
  strokeOpacity: CHART.gridOpacity,
  vertical: false,
};
