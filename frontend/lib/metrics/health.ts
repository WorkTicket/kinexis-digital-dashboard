/** Client health display helpers — score comes from the API (`/actions/health/{id}`). */

export type HealthArea = {
  id: string;
  label: string;
  status: "strong" | "watch" | "critical" | "unknown";
  score: number;
  summary: string;
  fixes: string[];
};

export type HealthGrade =
  | "Excellent"
  | "Healthy"
  | "Needs work"
  | "At risk"
  | "Critical"
  | "No data"
  | "Building baseline"
  | "Stabilizing";

export type HealthImprovement = {
  id: string;
  areaId: string;
  title: string;
  detail: string;
  steps: string[];
  effort: string;
  estimatedROI: string;
  metric: string;
};

export type ClientHealth = {
  score: number;
  grade: HealthGrade;
  headline: string;
  diagnosis: string;
  areas: HealthArea[];
  improvements: HealthImprovement[];
  openIssues: { high: number; medium: number; low: number };
  openOpportunities: number;
  overduePenalty: number;
  stalePenalty: number;
  inGracePeriod?: boolean;
  daysSinceRelaunch?: number | null;
};

export function gradeFromScore(
  score: number,
  opts?: {
    inGracePeriod?: boolean;
    unresolvedProblems?: number;
    openOpportunities?: number;
  }
): HealthGrade {
  if (opts?.inGracePeriod) return "Stabilizing";
  if (score <= 0) return "No data";
  if (
    score > 0 &&
    score < 40 &&
    (opts?.unresolvedProblems ?? 0) === 0 &&
    (opts?.openOpportunities ?? 0) === 0
  ) {
    return "Building baseline";
  }
  if (score >= 85) return "Excellent";
  if (score >= 70) return "Healthy";
  if (score >= 55) return "Needs work";
  if (score >= 40) return "At risk";
  return "Critical";
}

export type BackendPillars = {
  search_visibility: number;
  conversion_performance: number;
  traffic_quality: number;
  efficiency: number;
  technical: number;
};

const DEFAULT_AREAS: HealthArea[] = [
  {
    id: "visibility",
    label: "Visibility",
    status: "unknown",
    score: 0,
    summary: "Search visibility pillar",
    fixes: [],
  },
  {
    id: "engagement",
    label: "Traffic quality",
    status: "unknown",
    score: 0,
    summary: "Traffic quality pillar",
    fixes: [],
  },
  {
    id: "conversion",
    label: "Conversion",
    status: "unknown",
    score: 0,
    summary: "Conversion performance pillar",
    fixes: [],
  },
  {
    id: "efficiency",
    label: "Efficiency",
    status: "unknown",
    score: 0,
    summary: "Efficiency pillar",
    fixes: [],
  },
  {
    id: "technical",
    label: "Technical",
    status: "unknown",
    score: 0,
    summary: "Technical health pillar",
    fixes: [],
  },
];

/** Map backend pillar points (max 25/25/15/20/10) onto 0–100 area bars. */
export function areasFromBackendPillars(
  pillars: BackendPillars,
  baseAreas: HealthArea[] = DEFAULT_AREAS
): HealthArea[] {
  const norm = (pts: number, max: number) =>
    Math.max(5, Math.min(100, Math.round((pts / max) * 100)));
  const byId: Record<string, number> = {
    visibility: norm(pillars.search_visibility, 25),
    engagement: norm(pillars.traffic_quality, 15),
    conversion: norm(pillars.conversion_performance, 25),
    efficiency: norm(pillars.efficiency, 20),
    technical: norm(pillars.technical, 10),
  };
  return baseAreas.map((area) => {
    const score = byId[area.id] ?? area.score;
    const status: HealthArea["status"] =
      score >= 75 ? "strong" : score >= 50 ? "watch" : score > 0 ? "critical" : "unknown";
    return {
      ...area,
      score,
      status,
      summary:
        status === "strong"
          ? "On track"
          : status === "watch"
            ? "Watch this pillar"
            : status === "critical"
              ? "Needs attention"
              : area.summary,
    };
  });
}

type InsightLike = {
  severity: string;
  resolved: boolean;
  type: string;
  message?: string;
  kind?: string;
};

const PROBLEM_TYPES = new Set([
  "decline_alert",
  "zero_click_alert",
  "error_spike_alert",
  "pagespeed_urgent",
  "cro_opportunity",
  "bounce_cro_alert",
  "ads_spend_low_leads",
  "leads_revenue_leak",
  "organic_leads_leak",
  "mobile_ctr_gap",
  "ctr_gap",
  "gbp_low_engagement",
  "gbp_discovery_decline",
]);

export function insightKind(i: { kind?: string; type?: string }): "problem" | "opportunity" {
  const k = (i.kind || "").toLowerCase();
  if (k === "problem" || k === "opportunity") return k;
  return PROBLEM_TYPES.has(i.type || "") ? "problem" : "opportunity";
}

const GRACE_PERIOD_DAYS = 21;

export type ApiHealthInput = {
  health_score: number | null;
  risk?: string;
  risk_reasons?: string[];
  pillars?: BackendPillars | null;
  top_action?: {
    title: string;
    detail?: string;
    effort?: string;
  } | null;
};

/** Build display model from authoritative API health + local insight counts. */
export function buildHealthFromApi(
  api: ApiHealthInput | null,
  opts?: {
    insights?: InsightLike[];
    daysSinceRelaunch?: number | null;
  }
): ClientHealth {
  const insights = opts?.insights ?? [];
  const unresolvedAll = insights.filter((i) => !i.resolved);
  const unresolved = unresolvedAll.filter((i) => insightKind(i) === "problem");
  const openOpportunities = unresolvedAll.filter((i) => insightKind(i) === "opportunity").length;
  const high = unresolved.filter((i) => i.severity === "high").length;
  const medium = unresolved.filter((i) => i.severity === "medium").length;
  const low = unresolved.filter((i) => i.severity === "low").length;

  const daysSinceRelaunch = opts?.daysSinceRelaunch ?? null;
  const inGracePeriod =
    daysSinceRelaunch != null && daysSinceRelaunch >= 0 && daysSinceRelaunch < GRACE_PERIOD_DAYS;

  const score =
    api && typeof api.health_score === "number" && Number.isFinite(api.health_score)
      ? Math.max(0, Math.min(100, Math.round(api.health_score)))
      : 0;

  const areas = api?.pillars
    ? areasFromBackendPillars(api.pillars)
    : DEFAULT_AREAS.map((a) => ({ ...a }));

  const grade = gradeFromScore(score, {
    inGracePeriod,
    unresolvedProblems: high + medium + low,
    openOpportunities,
  });

  const improvements: HealthImprovement[] = [];
  if (api?.top_action?.title) {
    improvements.push({
      id: "api-top-action",
      areaId: "visibility",
      title: api.top_action.title,
      detail: api.top_action.detail || "",
      steps: [],
      effort: api.top_action.effort || "medium",
      estimatedROI: "",
      metric: "",
    });
  }

  const reasons = (api?.risk_reasons || []).filter(Boolean);
  const weakest = [...areas].sort((a, b) => a.score - b.score)[0];
  const criticalAreas = areas.filter((a) => a.status === "critical");

  let headline: string;
  let diagnosis: string;
  if (inGracePeriod) {
    headline = "Stabilizing after site relaunch";
    diagnosis = `Site relaunched ${daysSinceRelaunch}d ago — health is settling through the ${GRACE_PERIOD_DAYS}-day grace window.`;
  } else if (score <= 0) {
    headline = "No health score yet";
    diagnosis = "Sync connected sources to compute the authoritative 7-day health score.";
  } else if (grade === "Excellent" || grade === "Healthy") {
    headline = "Performance is in good shape — keep compounding wins";
    diagnosis =
      reasons[0] ||
      (openOpportunities > 0
        ? `Score is ${score}/100. ${openOpportunities} growth opportunit${openOpportunities === 1 ? "y" : "ies"} available in Prescribe.`
        : `Score is ${score}/100 on the 7-day portfolio formula.`);
  } else if (criticalAreas.length > 0) {
    headline = `${criticalAreas.map((a) => a.label).join(" & ")} need immediate attention`;
    diagnosis =
      reasons[0] ||
      (improvements[0]
        ? `Score is ${score}/100. Raise it by: ${improvements[0].title}.`
        : `Score is ${score}/100. Focus on the weakest pillars below.`);
  } else {
    headline = `Primary drag: ${weakest?.label ?? "mixed signals"}`;
    diagnosis =
      reasons[0] ||
      (improvements[0]
        ? `Score is ${score}/100. Next move: ${improvements[0].title}.`
        : `Score is ${score}/100 (7d). Focus on the weakest pillars below.`);
  }

  return {
    score,
    grade,
    headline,
    diagnosis,
    areas: score > 0 ? areas : [],
    improvements,
    openIssues: { high, medium, low },
    openOpportunities,
    overduePenalty: 0,
    stalePenalty: 0,
    ...(inGracePeriod
      ? { inGracePeriod: true, daysSinceRelaunch }
      : { inGracePeriod: false, daysSinceRelaunch }),
  };
}
