"use client";

import { useState, useEffect, useMemo } from "react";
import ClientHealth from "@/components/ClientHealth";
import SuccessScorecard from "@/components/SuccessScorecard";
import GrowthLeverGauge, { parseLeverFixSteps } from "@/components/GrowthLeverGauge";
import { Insight, Metric, api } from "@/lib/api";
import {
  buildKpiSummaries,
  formatKpiValue,
  insightKind,
  type KpiSummary,
  type PeriodOption,
} from "@/lib/metrics";
import { ArrowRight, TrendingUp, BarChart3, Zap } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Stat } from "@/components/ui/Stat";
import { Panel } from "@/components/ui/Panel";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { useToast } from "@/components/Toast";

function KpiStats({ kpis }: { kpis: KpiSummary[] }) {
  if (!kpis.length) return null;
  const priority = ["clicks", "sessions", "conversions", "leads", "revenue", "ad_cost"];
  const ordered = priority
    .map((k) => kpis.find((p) => p.key === k))
    .filter(Boolean) as KpiSummary[];
  const display = ordered.slice(0, 6);

  return (
    <div className="flex flex-wrap gap-2">
      {display.map((kpi) => {
        const invert = kpi.key === "ad_cost";
        const rawUp = (kpi.changePct ?? 0) > 0;
        const rawDown = (kpi.changePct ?? 0) < 0;
        const good = invert ? rawDown : rawUp;
        const bad = invert ? rawUp : rawDown;
        const tone = good ? "success" : bad ? "danger" : "default";
        const hint =
          kpi.changePct != null && kpi.previous > 0
            ? `${kpi.changePct > 0 ? "+" : ""}${kpi.changePct.toFixed(1)}%`
            : undefined;
        return (
          <Stat
            key={kpi.key}
            label={kpi.label}
            value={formatKpiValue(kpi.value, kpi.format)}
            hint={hint}
            tone={tone}
            className="!min-w-[7.5rem] flex-1 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[1.2rem]"
          />
        );
      })}
    </div>
  );
}

type Props = {
  metrics: Metric[];
  insights: Insight[];
  clientId?: number;
  clientName?: string;
  industry?: string;
  overdueTasks?: number;
  staleDays?: number | null;
  daysSinceRelaunch?: number | null;
  onStartFix: () => void;
  onOpenFunnel?: () => void;
};

export default function OverviewView({
  metrics,
  insights,
  clientId,
  clientName,
  industry: _industry,
  overdueTasks = 0,
  staleDays = null,
  daysSinceRelaunch = null,
  onStartFix,
  onOpenFunnel,
}: Props) {
  const { error: toastError } = useToast();
  const [period, setPeriod] = useState<PeriodOption>("7d");
  const [growthLever, setGrowthLever] = useState<{
    title: string;
    cause?: string;
    fix?: string;
    score?: number | null;
    confidence?: string | null;
  } | null>(null);

  useEffect(() => {
    if (!clientId) {
      setGrowthLever(null);
      return;
    }
    let cancelled = false;
    Promise.all([
      api.actions.getFunnel(clientId).catch((e) => {
        console.warn("Failed to load overview funnel", e);
        return null;
      }),
      api.levers.list(clientId).catch((e) => {
        console.warn("Failed to load levers for overview", e);
        return [] as Awaited<ReturnType<typeof api.levers.list>>;
      }),
    ])
      .then(([data, levers]) => {
        if (cancelled || !data) return;
        const topThread = Array.isArray(levers)
          ? [...levers].sort((a, b) => (b.impact_score ?? 0) - (a.impact_score ?? 0))[0]
          : null;
        const lever = data.growth_lever;
        const score = topThread?.impact_score ?? null;
        const leakNote =
          lever?.leak_pct != null
            ? `${Math.round(Number(lever.leak_pct))}% leak at this stage`
            : data.biggest_leak?.dropoff != null
              ? `${Math.round(Number(data.biggest_leak.dropoff))}% drop-off at this stage`
              : undefined;

        if (lever) {
          setGrowthLever({
            title: lever.title || lever.stage || "Growth lever",
            cause: lever.cause || leakNote,
            fix: lever.fix,
            score,
            confidence: topThread?.confidence_label,
          });
        } else if (data.biggest_leak) {
          setGrowthLever({
            title: `Improve ${data.biggest_leak.stage}`,
            cause: leakNote || `${data.biggest_leak.dropoff}% drop-off at this stage`,
            score,
            confidence: topThread?.confidence_label,
          });
        } else if (topThread) {
          setGrowthLever({
            title: topThread.title,
            cause: topThread.cause ?? undefined,
            fix: topThread.fix ?? undefined,
            score: topThread.impact_score,
            confidence: topThread.confidence_label,
          });
        } else {
          setGrowthLever(null);
        }
      })
      .catch((e) => {
        console.warn("Failed to load overview funnel/lever", e);
        if (!cancelled) {
          setGrowthLever(null);
          toastError("Couldn't load growth lever");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, toastError]);

  const kpis = useMemo(() => buildKpiSummaries(metrics, period), [metrics, period]);
  const fixSteps = useMemo(
    () => (growthLever?.fix ? parseLeverFixSteps(growthLever.fix) : []),
    [growthLever?.fix]
  );

  const healthIndicator = useMemo(() => {
    const openProblems = insights.filter((i) => !i.resolved && insightKind(i) === "problem").length;
    const openOpps = insights.filter((i) => !i.resolved && insightKind(i) === "opportunity").length;
    if (openProblems === 0 && openOpps === 0) return { label: "All clear", tone: "proof" as const };
    if (openProblems === 0)
      return {
        label: `${openOpps} opportunit${openOpps === 1 ? "y" : "ies"}`,
        tone: "momentum" as const,
      };
    if (openProblems <= 3)
      return {
        label: `${openProblems} problem${openProblems === 1 ? "" : "s"}`,
        tone: "warning" as const,
      };
    return { label: `${openProblems} problems`, tone: "danger" as const };
  }, [insights]);

  const movers = kpis
    .filter((k) => (k.changePct ?? 0) > 0 && k.key !== "ad_cost" && k.key !== "revenue")
    .slice(0, 3);

  return (
    <div className="animate-fade-up space-y-6">
      {/* Next move leads — morning answer before health chrome */}
      <Panel padding="lg" className="mission-hero !mb-0 border-kinexis-focus/15">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <p className="section-label text-muted text-[11px] font-semibold tracking-wide">
            Next move
          </p>
          <Badge tone={healthIndicator.tone}>{healthIndicator.label}</Badge>
        </div>

        {growthLever ? (
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:gap-6">
            <GrowthLeverGauge
              score={growthLever.score}
              confidence={growthLever.confidence}
              size={96}
              className="mx-auto sm:mx-0"
            />
            <div className="min-w-0 flex-1">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-semibold text-kinexis-focus">
                  Do this next
                </span>
                {growthLever.confidence && <Badge tone="default">{growthLever.confidence}</Badge>}
              </div>
              <h3 className="text-title text-[18px] leading-tight">{growthLever.title}</h3>
              {growthLever.cause && (
                <p className="text-muted mt-3 max-w-2xl text-[13px] leading-relaxed">
                  {growthLever.cause}
                </p>
              )}
              {fixSteps.length > 0 && (
                <ol className="mt-4 max-w-2xl space-y-2">
                  {fixSteps.slice(0, 3).map((step, i) => (
                    <li
                      key={i}
                      className="flex gap-3 text-[13px] leading-relaxed text-ink-secondary"
                    >
                      <span className="font-mono-data mt-0.5 w-5 shrink-0 text-[11px] text-kinexis-focus">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              )}
              <div className="mt-4">
                <Button variant="primary" size="sm" onClick={onStartFix}>
                  <Zap size={12} /> Open Fix queue <ArrowRight size={13} />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-4 py-2">
            <div
              className="flex h-14 w-14 shrink-0 items-center justify-center bg-[color:var(--hover-fill)]"
              style={{ borderRadius: "var(--radius-lg)" }}
            >
              <BarChart3 size={22} className="text-muted" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <h3 className="text-title text-[18px]">Waiting for data</h3>
              <p className="text-muted mt-1.5 max-w-md text-[13px] leading-relaxed">
                Sync sources so we can name the one lever that matters for this client.
              </p>
            </div>
          </div>
        )}
      </Panel>

      <ClientHealth
        clientId={clientId}
        insights={insights}
        clientName={clientName}
        overdueTasks={overdueTasks}
        staleDays={staleDays}
        daysSinceRelaunch={daysSinceRelaunch}
        onOpenFunnel={onOpenFunnel}
      />

      {movers.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {movers.map((k) => (
            <div
              key={k.key}
              className="inline-flex items-center gap-2 text-[12px] text-ink-secondary"
            >
              <TrendingUp size={11} className="text-kinexis-proof" />
              {k.label}{" "}
              <span className="font-mono-data font-medium text-kinexis-proof">
                +{k.changePct?.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      )}

      <CollapsibleSection label="Pulse KPIs" defaultOpen>
        <div className="mb-3 flex justify-end">
          <div className="flex rounded-md border border-[color:var(--border-subtle)] p-0.5">
            {(
              [
                { value: "7d" as const, label: "7d" },
                { value: "30d" as const, label: "30d" },
              ] as const
            ).map((p) => (
              <button
                key={p.value}
                type="button"
                onClick={() => setPeriod(p.value)}
                className={`motion-micro rounded-[calc(var(--radius-md)-2px)] px-3 py-1 text-[12px] font-medium ${
                  period === p.value
                    ? "bg-[color:var(--surface-elevated)] text-ink shadow-panel"
                    : "text-muted hover:text-ink-secondary"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        <KpiStats kpis={kpis} />
      </CollapsibleSection>

      <CollapsibleSection label="Success scorecard">
        <SuccessScorecard metrics={metrics} period={period} />
      </CollapsibleSection>
    </div>
  );
}
