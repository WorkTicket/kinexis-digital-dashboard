"use client";

import { useMemo, useState, useEffect } from "react";
import { Insight, api } from "@/lib/api";
import { buildHealthFromApi, HealthArea, type ApiHealthInput } from "@/lib/metrics";
import { chartHealthRingTone, chartRingTrack } from "@/lib/chartTheme";
import { useToast } from "@/components/Toast";
import { Stat } from "@/components/ui/Stat";
import { Panel } from "@/components/ui/Panel";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { AlertTriangle, ArrowRight, ShieldCheck, Lightbulb, TrendingUp } from "lucide-react";

type Props = {
  clientId?: number;
  insights: Insight[];
  clientName?: string;
  overdueTasks?: number;
  staleDays?: number | null;
  daysSinceRelaunch?: number | null;
  onOpenFunnel?: () => void;
};

function statusColor(status: HealthArea["status"]) {
  switch (status) {
    case "strong":
      return { bar: "bg-kinexis-proof", text: "text-kinexis-proof", label: "Strong" };
    case "watch":
      return { bar: "bg-kinexis-signal", text: "text-kinexis-signal", label: "Watch" };
    case "critical":
      return { bar: "bg-kinexis-risk", text: "text-kinexis-risk", label: "Critical" };
    default:
      return { bar: "bg-kinexis-mist", text: "text-muted", label: "—" };
  }
}

function statusStatTone(status: HealthArea["status"]) {
  switch (status) {
    case "strong":
      return "success" as const;
    case "watch":
      return "warning" as const;
    case "critical":
      return "danger" as const;
    default:
      return "default" as const;
  }
}

function gradeTone(grade: string) {
  if (grade === "Excellent" || grade === "Healthy") return "proof" as const;
  if (grade === "Needs work" || grade === "Building baseline" || grade === "Stabilizing")
    return "signal" as const;
  if (grade === "No data") return "default" as const;
  return "risk" as const;
}

const gradeClass = {
  proof: "text-kinexis-proof border-kinexis-proof/30",
  signal: "text-kinexis-signal border-kinexis-signal/30",
  risk: "text-kinexis-risk border-kinexis-risk/30",
  default: "text-muted border-[color:var(--border-default)]",
};

function tipsDefaultOpen(area: HealthArea) {
  return area.status === "critical" || area.status === "watch" || area.score < 75;
}

export default function ClientHealth({
  clientId,
  insights,
  clientName,
  overdueTasks = 0,
  staleDays = null,
  daysSinceRelaunch = null,
  onOpenFunnel,
}: Props) {
  const { error: toastError } = useToast();
  const [apiHealth, setApiHealth] = useState<ApiHealthInput | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!clientId) {
      setApiHealth(null);
      setLoaded(true);
      return;
    }
    let cancelled = false;
    setLoaded(false);
    api.health
      .forClient(clientId)
      .then((res) => {
        if (cancelled) return;
        setApiHealth({
          health_score: res.health_score,
          risk: res.risk,
          risk_reasons: res.risk_reasons,
          pillars: res.pillars ?? null,
          top_action: res.top_action ?? null,
        });
        setLoaded(true);
      })
      .catch((e) => {
        if (cancelled) return;
        setApiHealth(null);
        setLoaded(true);
        toastError(e instanceof Error ? e.message : "Couldn't load health score");
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, toastError]);

  const healthDisplay = useMemo(
    () =>
      buildHealthFromApi(apiHealth, {
        insights,
        daysSinceRelaunch,
      }),
    [apiHealth, insights, daysSinceRelaunch]
  );

  const ringColor = chartHealthRingTone(healthDisplay.score);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (healthDisplay.score / 100) * circumference;
  const grade = gradeTone(healthDisplay.grade);
  const topPlay = healthDisplay.improvements[0];
  const hasAuthoritative = loaded && apiHealth != null && (apiHealth.health_score ?? 0) > 0;

  return (
    <Panel className="animate-fade-up overflow-hidden" padding={false}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-4 pb-4 pt-4">
        <div>
          <p className="text-label">Client health</p>
          <p className="text-muted mt-0.5 text-[13px]">
            {clientName ? `${clientName}` : ""}
            {healthDisplay.inGracePeriod
              ? ` · stabilizing (site relaunched ${healthDisplay.daysSinceRelaunch}d ago)`
              : overdueTasks > 0
                ? ` · ${overdueTasks} overdue task${overdueTasks === 1 ? "" : "s"}`
                : staleDays != null && staleDays >= 3
                  ? ` · data ${staleDays}d stale`
                  : hasAuthoritative
                    ? " · 7-day health score"
                    : " · awaiting sync"}
          </p>
        </div>
        <span className={`badge ${gradeClass[grade]}`}>{healthDisplay.grade}</span>
      </div>

      <div className="grid grid-cols-1 gap-6 p-4 sm:p-6 lg:grid-cols-[168px_1fr]">
        <div className="flex flex-col items-center justify-center">
          <div className="relative h-[132px] w-[132px]">
            <svg className="h-full w-full -rotate-90" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="54" fill="none" stroke={chartRingTrack} strokeWidth="6" />
              <circle
                cx="60"
                cy="60"
                r="54"
                fill="none"
                stroke={ringColor}
                strokeWidth="6"
                strokeLinecap="butt"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                className="motion-gauge"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-display leading-none" style={{ color: ringColor }}>
                {healthDisplay.score > 0 ? healthDisplay.score : "—"}
              </span>
              <span className="text-muted font-mono-data mt-1.5 text-[11px] font-medium">
                {healthDisplay.score > 0 ? "Score" : ""}
              </span>
            </div>
          </div>
          <div className="text-muted mt-3 flex flex-col items-center gap-1 text-[11px]">
            <div className="flex items-center gap-3">
              {(healthDisplay.openIssues.high > 0 ||
                healthDisplay.openIssues.medium > 0 ||
                healthDisplay.openIssues.low > 0) && (
                <>
                  {healthDisplay.openIssues.high > 0 && (
                    <span className="font-medium text-kinexis-risk">
                      {healthDisplay.openIssues.high} high
                    </span>
                  )}
                  {healthDisplay.openIssues.medium > 0 && (
                    <span className="text-kinexis-signal">
                      {healthDisplay.openIssues.medium} med
                    </span>
                  )}
                  {healthDisplay.openIssues.low > 0 && (
                    <span>{healthDisplay.openIssues.low} low</span>
                  )}
                </>
              )}
              {healthDisplay.openIssues.high === 0 &&
                healthDisplay.openIssues.medium === 0 &&
                healthDisplay.openIssues.low === 0 && (
                  <span
                    className={`flex items-center gap-1 ${healthDisplay.score >= 70 ? "text-kinexis-proof" : "text-kinexis-signal"}`}
                  >
                    {healthDisplay.score >= 70 ? (
                      <>
                        <ShieldCheck size={12} strokeWidth={1.75} /> No problems
                      </>
                    ) : (
                      <>
                        <TrendingUp size={12} strokeWidth={1.75} />{" "}
                        {healthDisplay.improvements.length} raise play
                        {healthDisplay.improvements.length === 1 ? "" : "s"}
                      </>
                    )}
                  </span>
                )}
            </div>
            {healthDisplay.openOpportunities > 0 && (
              <span className="text-ink-dim">
                {healthDisplay.openOpportunities} growth opportunit
                {healthDisplay.openOpportunities === 1 ? "y" : "ies"}
              </span>
            )}
          </div>
        </div>

        <div className="flex min-w-0 flex-col">
          <h2 className="text-title text-balance leading-snug">{healthDisplay.headline}</h2>
          <p className="text-muted mt-2 max-w-2xl text-[13px] leading-relaxed">
            {healthDisplay.diagnosis}
          </p>

          {topPlay && healthDisplay.score > 0 && healthDisplay.score < 85 && (
            <div className="mt-3 rounded-[var(--radius-sm)] border border-kinexis-signal/25 bg-kinexis-signal/5 px-3 py-3">
              <p className="text-[11px] font-medium text-kinexis-signal">
                Score tip
              </p>
              <p className="mt-0.5 text-[13px] font-medium text-ink">{topPlay.title}</p>
              {topPlay.detail && (
                <p className="text-muted mt-0.5 text-[12px] leading-snug">{topPlay.detail}</p>
              )}
            </div>
          )}

          {healthDisplay.areas.length > 0 && (
            <div className="metric-grid mt-5 grid-cols-1 sm:grid-cols-2">
              {healthDisplay.areas.map((area) => {
                const tone = statusColor(area.status);
                return (
                  <div key={area.id} className="space-y-2">
                    <Stat
                      label={area.label}
                      value={area.score}
                      hint={`${tone.label} · ${area.summary}`}
                      tone={statusStatTone(area.status)}
                      className="w-full"
                    />
                    <div className="progress-track">
                      <div
                        className={`progress-fill ${tone.bar} motion-bar`}
                        style={{ width: `${area.score}%` }}
                      />
                    </div>
                    {area.fixes.length > 0 && (
                      <CollapsibleSection
                        label={`${area.fixes.length} tip${area.fixes.length === 1 ? "" : "s"}`}
                        defaultOpen={tipsDefaultOpen(area)}
                        className="[&>div:first-child]:!mb-1 [&>div:first-child]:!mt-0"
                      >
                        <ul className="space-y-1 border-t border-[color:var(--border-subtle)] pt-2">
                          {area.fixes.map((fix, fi) => (
                            <li
                              key={fi}
                              className="flex items-start gap-2 text-[11px] leading-relaxed text-ink-dim"
                            >
                              <Lightbulb
                                size={11}
                                strokeWidth={1.75}
                                className="mt-0.5 shrink-0 text-kinexis-signal"
                              />
                              {fix}
                            </li>
                          ))}
                        </ul>
                      </CollapsibleSection>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            {onOpenFunnel && (
              <button type="button" onClick={onOpenFunnel} className="btn-secondary">
                Inspect funnel
                <ArrowRight size={13} />
              </button>
            )}
            {healthDisplay.openIssues.high > 0 && (
              <span className="inline-flex items-center gap-2 px-2 py-2 text-xs text-kinexis-risk">
                <AlertTriangle size={12} strokeWidth={1.75} />
                High-severity first — assign in Fix queue
              </span>
            )}
          </div>
        </div>
      </div>
    </Panel>
  );
}
