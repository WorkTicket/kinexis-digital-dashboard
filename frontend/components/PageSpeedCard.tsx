"use client";

import { Metric } from "@/lib/api";
import { useMemo } from "react";
import { seriesByDate } from "@/lib/metrics";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { CHART, chartPageSpeedTone, chartRingTrack, chartGridProps } from "@/lib/chartTheme";
import { Panel } from "@/components/ui/Panel";
import { KinexisChartTooltip } from "@/components/ui/KinexisChartTooltip";

type Props = {
  metrics: Metric[];
};

function ScoreRing({ score, label }: { score: number | null; label: string }) {
  const circumference = 2 * Math.PI * 36;
  const hasScore = score != null && Number.isFinite(score);
  const value = hasScore ? Math.min(Math.max(score, 0), 100) : 0;
  const offset = circumference - (value / 100) * circumference;
  const color = hasScore ? chartPageSpeedTone(value) : CHART.mist;

  return (
    <div className="flex flex-col items-center">
      <div className="relative h-[5.5rem] w-[5.5rem]">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 80 80" aria-hidden="true">
          <circle cx="40" cy="40" r="36" fill="none" stroke={chartRingTrack} strokeWidth="5" />
          <circle
            cx="40"
            cy="40"
            r="36"
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeDasharray={circumference}
            strokeDashoffset={hasScore ? offset : circumference}
            strokeLinecap="butt"
            className="motion-gauge"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-metric text-lg leading-none" style={{ color }}>
            {hasScore ? Math.round(value) : "\u2014"}
          </span>
        </div>
      </div>
      <span className="text-muted mt-1.5 text-[11px] capitalize">{label}</span>
    </div>
  );
}

function SpeedHistoryChart({
  series,
  label,
  unit,
  color,
}: {
  series: { date: string; value: number }[];
  label: string;
  unit: string;
  color: string;
}) {
  if (series.length < 2) return null;
  return (
    <div className="min-w-0 flex-1">
      <p className="text-muted mb-1 text-[11px] font-medium uppercase tracking-wider">{label}</p>
      <ResponsiveContainer width="100%" height={72}>
        <LineChart data={series} margin={{ top: 2, right: 0, left: -10, bottom: 0 }}>
          <CartesianGrid {...chartGridProps} vertical={false} />
          <XAxis dataKey="date" tick={false} axisLine={false} />
          <YAxis tick={false} axisLine={false} width={0} />
          <Tooltip
            content={<KinexisChartTooltip />}
            cursor={{ stroke: "var(--border-default)", strokeWidth: 1 }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            name={`${label} (${unit})`}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function PageSpeedCard({ metrics }: Props) {
  const scores = useMemo(() => {
    const result: Record<string, Record<string, number>> = {};
    metrics
      .filter((m) => m.source === "pagespeed" && m.metric_name.includes("performance_score"))
      .forEach((m) => {
        const strategy = m.metric_name.replace("performance_score_", "");
        const url = m.dimension_value || "root";
        if (!result[url]) result[url] = {};
        result[url][strategy] = m.value;
      });
    return result;
  }, [metrics]);

  const coreVitals = useMemo(() => {
    const result: Record<string, { lcp: number | null; tbt: number | null; cls: number | null }> =
      {};
    metrics
      .filter((m) => m.source === "pagespeed")
      .forEach((m) => {
        const url = m.dimension_value || "root";
        if (!result[url]) result[url] = { lcp: null, tbt: null, cls: null };
        if (m.metric_name.startsWith("largest_contentful_paint")) result[url].lcp = m.value;
        if (m.metric_name.startsWith("total_blocking_time")) result[url].tbt = m.value;
        if (m.metric_name.startsWith("cumulative_layout_shift")) result[url].cls = m.value;
      });
    return result;
  }, [metrics]);

  const history = useMemo(() => {
    const lcp = seriesByDate(metrics, {
      metricName: "largest_contentful_paint_mobile",
      source: "pagespeed",
    });
    const tbt = seriesByDate(metrics, {
      metricName: "total_blocking_time_mobile",
      source: "pagespeed",
    });
    const cls = seriesByDate(metrics, {
      metricName: "cumulative_layout_shift_mobile",
      source: "pagespeed",
    });
    return { lcp, tbt, cls };
  }, [metrics]);

  const urlEntries = Object.keys(scores).length > 0 ? Object.keys(scores) : Object.keys(coreVitals);
  if (urlEntries.length === 0) return null;

  const hasHistory = history.lcp.length >= 2 || history.tbt.length >= 2 || history.cls.length >= 2;

  return (
    <Panel padding="md">
      <h3 className="text-label mb-4">PageSpeed Insights</h3>

      {urlEntries.map((url) => {
        const urlScores = scores[url] || {};
        const vitals = coreVitals[url] || { lcp: null, tbt: null, cls: null };

        return (
          <div key={url} className="mb-5 last:mb-0">
            <p className="text-muted font-mono-data mb-3 truncate text-xs" title={url}>
              {url}
            </p>
            <div className="flex flex-col flex-wrap gap-6 sm:flex-row sm:items-center sm:gap-8">
              <ScoreRing score={urlScores.mobile ?? null} label="Mobile" />
              <ScoreRing score={urlScores.desktop ?? null} label="Desktop" />
              <div className="grid min-w-0 grid-cols-3 gap-3 sm:gap-5">
                {(
                  [
                    [
                      "LCP",
                      vitals.lcp != null ? `${(vitals.lcp / 1000).toFixed(1)}s` : "\u2014",
                      vitals.lcp != null && vitals.lcp > 2500,
                    ],
                    [
                      "TBT",
                      vitals.tbt != null ? `${Math.round(vitals.tbt)}ms` : "\u2014",
                      vitals.tbt != null && vitals.tbt > 200,
                    ],
                    [
                      "CLS",
                      vitals.cls != null ? vitals.cls.toFixed(2) : "\u2014",
                      vitals.cls != null && vitals.cls > 0.1,
                    ],
                  ] as const
                ).map(([label, value, risk]) => (
                  <div key={label}>
                    <p className="text-label">{label}</p>
                    <p
                      className={`font-mono-data mt-1 text-[13px] ${
                        risk ? "text-kinexis-risk" : "text-ink"
                      }`}
                    >
                      {value}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {hasHistory && (
              <div className="mt-4 flex gap-4 border-t border-[color:var(--border-subtle)] pt-3">
                <SpeedHistoryChart
                  series={history.lcp.map((d) => ({
                    ...d,
                    value: d.value / 1000,
                  }))}
                  label="LCP"
                  unit="s"
                  color={CHART.risk}
                />
                <SpeedHistoryChart
                  series={history.tbt}
                  label="TBT"
                  unit="ms"
                  color={CHART.signal}
                />
                <SpeedHistoryChart
                  series={history.cls.map((d) => ({
                    ...d,
                    value: Math.round(d.value * 1000) / 1000,
                  }))}
                  label="CLS"
                  unit=""
                  color={CHART.momentum}
                />
              </div>
            )}
          </div>
        );
      })}
    </Panel>
  );
}
