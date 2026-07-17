"use client";

import { useMemo } from "react";
import { Metric } from "@/lib/api";
import { buildKpiSummaries, formatKpiValue, type PeriodOption } from "@/lib/metrics";
import { Stat } from "@/components/ui/Stat";
import { Panel } from "@/components/ui/Panel";

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
    <Panel className="animate-fade-up animate-fade-up-delay-1" padding={false}>
      <div className="flex items-baseline justify-between border-b border-[color:var(--border-subtle)] px-4 py-4">
        <h2 className="text-[13px] font-medium text-ink">Success metrics</h2>
        <span className="text-muted font-mono-data text-[12px]">{periodLabel}</span>
      </div>
      <div className="metric-grid grid-cols-2 p-4 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-7">
        {kpis.map((kpi) => {
          const invert = kpi.key === "ad_cost";
          const rawUp = kpi.changePct != null && kpi.changePct > 0.5;
          const rawDown = kpi.changePct != null && kpi.changePct < -0.5;
          const up = invert ? rawDown : rawUp;
          const down = invert ? rawUp : rawDown;
          const targetPct =
            kpi.target && kpi.target > 0 ? Math.min(100, (kpi.value / kpi.target) * 100) : null;
          const onTrack = targetPct != null && targetPct >= 80;

          const hintParts: string[] = [];
          if (kpi.changePct != null) {
            hintParts.push(`${kpi.changePct > 0 ? "+" : ""}${kpi.changePct.toFixed(0)}%`);
          }
          if (targetPct != null) {
            hintParts.push(
              onTrack ? `On track ${Math.round(targetPct)}%` : `${Math.round(targetPct)}% of target`
            );
          }

          return (
            <Stat
              key={kpi.key}
              label={kpi.label}
              value={formatKpiValue(kpi.value, kpi.format)}
              hint={hintParts.length > 0 ? hintParts.join(" · ") : undefined}
              tone={up ? "success" : down ? "danger" : "default"}
              className="panel-interactive"
            />
          );
        })}
      </div>
    </Panel>
  );
}
