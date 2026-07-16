"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { Insight, api } from "@/lib/api";
import { buildHealthFromApi, HealthArea, type ApiHealthInput } from "@/lib/metrics";
import { chartHealthRingTone, chartRingTrack } from "@/lib/chartTheme";
import { useToast } from "@/components/Toast";
import {
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  ChevronDown,
  Lightbulb,
  TrendingUp,
} from "lucide-react";

type Props = {
  clientId?: number;
  insights: Insight[];
  clientName?: string;
  overdueTasks?: number;
  staleDays?: number | null;
  daysSinceRelaunch?: number | null;
  onStartFix?: () => void;
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

function initialExpanded(areas: HealthArea[]) {
  const initial = new Set<string>();
  for (const area of areas) {
    if (area.status === "critical" || area.status === "watch" || area.score < 75) {
      initial.add(area.id);
    }
  }
  return initial;
}

export default function ClientHealth({
  clientId,
  insights,
  clientName,
  overdueTasks = 0,
  staleDays = null,
  daysSinceRelaunch = null,
  onStartFix,
  onOpenFunnel,
}: Props) {
  const { error: toastError } = useToast();
  const [apiHealth, setApiHealth] = useState<ApiHealthInput | null>(null);
  const [loaded, setLoaded] = useState(false);
  const userToggled = useRef(false);

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
        toastError(e instanceof Error ? e.message : "Couldn't load authoritative health score");
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

  const areasKey = healthDisplay.areas.map((a) => `${a.id}:${a.status}:${a.score}`).join("|");
  const [expandedFixes, setExpandedFixes] = useState<Set<string>>(() =>
    initialExpanded(healthDisplay.areas)
  );

  useEffect(() => {
    if (userToggled.current) return;
    setExpandedFixes(initialExpanded(healthDisplay.areas));
  }, [areasKey, healthDisplay.areas]);

  function toggleFixes(id: string) {
    userToggled.current = true;
    setExpandedFixes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const ringColor = chartHealthRingTone(healthDisplay.score);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (healthDisplay.score / 100) * circumference;
  const grade = gradeTone(healthDisplay.grade);
  const topPlay = healthDisplay.improvements[0];
  const hasAuthoritative = loaded && apiHealth != null && (apiHealth.health_score ?? 0) > 0;

  return (
    <section className="panel animate-fade-up mb-7 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 pb-3.5 pt-4">
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
                    ? " · 7d authoritative score"
                    : " · awaiting sync"}
          </p>
        </div>
        <span className={`badge ${gradeClass[grade]}`}>{healthDisplay.grade}</span>
      </div>

      <div className="grid grid-cols-1 gap-7 p-5 sm:p-6 lg:grid-cols-[168px_1fr]">
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
              <span className="text-metric text-[2rem] leading-none" style={{ color: ringColor }}>
                {healthDisplay.score > 0 ? healthDisplay.score : "—"}
              </span>
              <span className="text-muted font-mono-data mt-1.5 text-[11px] font-medium">
                {healthDisplay.score > 0 ? "Score" : ""}
              </span>
            </div>
          </div>
          <div className="text-muted mt-3.5 flex flex-col items-center gap-1 text-[11px]">
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
            <div className="mt-3 rounded-[var(--radius-sm)] border border-kinexis-signal/25 bg-kinexis-signal/5 px-3 py-2.5">
              <p className="text-[11px] font-medium text-kinexis-signal">
                Next move to raise score
              </p>
              <p className="mt-0.5 text-[13px] font-medium text-ink">{topPlay.title}</p>
              {topPlay.detail && (
                <p className="text-muted mt-0.5 text-[12px] leading-snug">{topPlay.detail}</p>
              )}
              {onStartFix && (
                <button
                  type="button"
                  className="btn-secondary mt-2 !h-7 !text-[11px]"
                  onClick={onStartFix}
                >
                  Open Fix queue
                </button>
              )}
            </div>
          )}

          {healthDisplay.areas.length > 0 && (
            <div className="metric-grid mt-5 grid-cols-1 sm:grid-cols-2">
              {healthDisplay.areas.map((area) => {
                const tone = statusColor(area.status);
                return (
                  <div key={area.id} className="metric-tile">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-[13px] font-medium text-ink-secondary">
                        {area.label}
                      </span>
                      <span className={`text-[11px] font-medium ${tone.text}`}>{tone.label}</span>
                    </div>
                    <div className="progress-track mb-2">
                      <div
                        className={`progress-fill ${tone.bar} motion-bar`}
                        style={{ width: `${area.score}%` }}
                      />
                    </div>
                    <p className="text-muted text-[12px] leading-snug">{area.summary}</p>
                    {area.fixes.length > 0 && (
                      <button
                        type="button"
                        onClick={() => toggleFixes(area.id)}
                        className="mt-2 flex items-center gap-1 text-[11px] font-medium text-kinexis-signal transition-colors hover:text-kinexis-risk"
                      >
                        <Lightbulb size={11} strokeWidth={1.75} />
                        {expandedFixes.has(area.id)
                          ? "Hide tips"
                          : `${area.fixes.length} tip${area.fixes.length === 1 ? "" : "s"}`}
                        <ChevronDown
                          size={11}
                          strokeWidth={1.75}
                          className={`transition-transform ${expandedFixes.has(area.id) ? "rotate-180" : ""}`}
                        />
                      </button>
                    )}
                    {expandedFixes.has(area.id) && area.fixes.length > 0 && (
                      <ul className="mt-2 space-y-1 border-t border-[color:var(--border-subtle)] pt-2">
                        {area.fixes.map((fix, fi) => (
                          <li
                            key={fi}
                            className="flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-dim"
                          >
                            <span className="mt-0.5 shrink-0 text-kinexis-signal">&#9656;</span>
                            {fix}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            {onStartFix && healthDisplay.score > 0 && healthDisplay.grade !== "Excellent" && (
              <button type="button" onClick={onStartFix} className="btn-primary">
                Open Fix queue
                <ArrowRight size={13} />
              </button>
            )}
            {onOpenFunnel && (
              <button type="button" onClick={onOpenFunnel} className="btn-secondary">
                Inspect funnel
              </button>
            )}
            {healthDisplay.openIssues.high > 0 && (
              <span className="inline-flex items-center gap-1.5 px-2 py-2 text-xs text-kinexis-risk">
                <AlertTriangle size={12} strokeWidth={1.75} />
                Assign high-severity first in Fix queue
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
