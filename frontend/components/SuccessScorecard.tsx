"use client";

import { useMemo } from "react";
import { Metric } from "@/lib/api";
import { buildKpiSummaries, formatKpiValue, type PeriodOption } from "@/lib/metrics";
import { TrendingUp, TrendingDown, Minus, Target } from "lucide-react";

type Props = {
  metrics: Metric[];
  period?: PeriodOption;
};

export default function SuccessScorecard({ metrics, period = "7d" }: Props) {
  const kpis = useMemo(() => buildKpiSummaries(metrics, period), [metrics, period]);
  const periodLabel =
    period === "1y"
      ? "30d vs 1 year ago"
      : period === "90d"
        ? "90d vs prior 90d"
        : period === "60d"
          ? "60d vs prior 60d"
          : period === "30d"
            ? "30d vs prior 30d"
            : "7d vs prior 7d";

  if (kpis.length === 0) return null;

  return (
    <div className="animate-fade-up animate-fade-up-delay-1 mb-7">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-ink">Success metrics</h2>
        <span className="text-muted font-mono-data text-[12px]">{periodLabel}</span>
      </div>
      <div className="metric-grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-7">
        {kpis.map((kpi) => {
          const invert = kpi.key === "ad_cost";
          const rawUp = kpi.changePct != null && kpi.changePct > 0.5;
          const rawDown = kpi.changePct != null && kpi.changePct < -0.5;
          const up = invert ? rawDown : rawUp;
          const down = invert ? rawUp : rawDown;
          const targetPct =
            kpi.target && kpi.target > 0 ? Math.min(100, (kpi.value / kpi.target) * 100) : null;
          const onTrack = targetPct != null && targetPct >= 80;

          return (
            <div key={kpi.key} className="metric-tile panel-interactive" title={kpi.hint}>
              <p className="text-label mb-2">{kpi.label}</p>
              <p className="text-metric text-[1.35rem] leading-none">
                {formatKpiValue(kpi.value, kpi.format)}
              </p>
              {targetPct != null && (
                <div className="mt-1.5 flex items-center gap-1.5">
                  <Target
                    size={10}
                    className={onTrack ? "text-kinexis-proof" : "text-kinexis-risk"}
                  />
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-surface-border">
                    <div
                      className={`h-full rounded-full transition-all duration-bar ${
                        onTrack ? "bg-kinexis-proof/60" : "bg-kinexis-risk/60"
                      }`}
                      style={{ width: `${targetPct}%` }}
                    />
                  </div>
                  <span
                    className={`font-mono-data text-[11px] font-medium ${
                      onTrack ? "text-kinexis-proof/80" : "text-kinexis-risk/80"
                    }`}
                  >
                    {Math.round(targetPct)}%
                  </span>
                </div>
              )}
              <div className="mt-2.5 flex items-center gap-1">
                {kpi.changePct == null ? (
                  <span className="text-muted flex items-center gap-0.5 text-xs">
                    <Minus size={10} /> —
                  </span>
                ) : (
                  <span
                    className={`font-mono-data flex items-center gap-0.5 text-[11px] font-medium ${
                      up ? "text-kinexis-proof/80" : down ? "text-kinexis-risk/80" : "text-muted"
                    }`}
                    aria-label={`${kpi.label}: ${kpi.changePct > 0 ? "+" : ""}${kpi.changePct.toFixed(0)}% change`}
                  >
                    {up ? (
                      <TrendingUp size={11} aria-hidden />
                    ) : down ? (
                      <TrendingDown size={11} aria-hidden />
                    ) : (
                      <Minus size={11} aria-hidden />
                    )}
                    {kpi.changePct > 0 ? "+" : ""}
                    {kpi.changePct.toFixed(0)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
