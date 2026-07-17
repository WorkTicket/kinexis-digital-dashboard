"use client";

import {
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  ComposedChart,
} from "recharts";
import { Metric } from "@/lib/api";
import { memo, useMemo, useId } from "react";
import { seriesByDate, generateProjection } from "@/lib/metrics";
import { Panel } from "@/components/ui/Panel";
import { KinexisChartTooltip } from "@/components/ui/KinexisChartTooltip";
import { CHART, chartAxisTick, chartGridProps } from "@/lib/chartTheme";

export type KnownEventOverlay = {
  name: string;
  start: string;
  end: string;
  type: string;
};

type Props = {
  metrics: Metric[];
  metricName: string;
  label: string;
  color?: string;
  source?: string;
  sources?: readonly string[];
  projectionDays?: number;
  lookbackDays?: number;
  compareDays?: number;
  events?: KnownEventOverlay[];
};

function DashboardChart({
  metrics,
  metricName,
  label,
  color = CHART.focus,
  source,
  sources,
  projectionDays = 0,
  lookbackDays,
  compareDays = 0,
  events,
}: Props) {
  const uid = useId();
  const gradientId = `${sources ? "paid" : source || "all"}-${metricName}-${uid}`;
  const compareGradientId = `compare-${gradientId}`;

  const { chartData, prevData, projData, showCompare } = useMemo(() => {
    const series = seriesByDate(metrics, {
      metricName,
      source: sources ? undefined : source,
      sources,
      lookbackDays,
    });
    const data = series.map((d) => ({
      date: d.date,
      [metricName]: d.value,
    }));

    const showComp = compareDays > 0 && series.length >= 14;
    let prevSeriesPoints: { date: string; value: number }[] = [];
    if (showComp) {
      const prev = seriesByDate(metrics, {
        metricName,
        source: sources ? undefined : source,
        sources,
        lookbackDays: (lookbackDays ?? 90) + compareDays,
      });
      if (prev.length >= compareDays + 7) {
        prevSeriesPoints = prev.slice(0, prev.length - compareDays);
      }
    }
    const prevMapped = prevSeriesPoints.map((d) => ({
      date: d.date,
      compare: d.value,
    }));

    const proj = projectionDays > 0 ? generateProjection(series, projectionDays) : [];
    const projPoints = proj.map((d) => ({
      date: d.date,
      projection: d.value,
    }));

    return { chartData: data, prevData: prevMapped, projData: projPoints, showCompare: showComp };
  }, [metrics, metricName, source, sources, projectionDays, lookbackDays, compareDays]);

  const mergedData = useMemo(() => {
    if (!showCompare || prevData.length === 0) {
      return projData.length > 0 ? [...chartData, ...projData] : chartData;
    }
    const map = new Map<string, { date: string; [k: string]: unknown }>();
    for (const d of chartData) {
      map.set(d.date, { ...d });
    }
    for (const d of prevData) {
      const existing = map.get(d.date);
      if (existing) {
        existing.compare = d.compare;
      } else {
        map.set(d.date, { date: d.date, compare: d.compare });
      }
    }
    for (const d of projData) {
      map.set(d.date, { ...(map.get(d.date) || {}), ...d });
    }
    return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
  }, [chartData, prevData, projData, showCompare]);

  const chartEvents = useMemo(() => {
    if (!events || events.length === 0 || chartData.length === 0) return [];
    const dates = chartData.map((d) => d.date).sort();
    const first = dates[0];
    const last = dates[dates.length - 1];
    if (!first || !last) return [];
    return events.filter((e) => e.start <= last && e.end >= first);
  }, [events, chartData]);

  if (chartData.length === 0) return null;

  const compareColor = color + "80";

  return (
    <Panel padding="md" className="motion-micro">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-1">
        <h3 className="text-label">{label}</h3>
        <div className="flex items-center gap-2">
          {showCompare && (
            <span className="text-muted font-mono text-[11px]">vs prev {compareDays}d</span>
          )}
          {projectionDays > 0 && projData.length > 0 && (
            <span className="text-muted font-mono text-[11px]">+{projectionDays}d forecast</span>
          )}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={mergedData} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.12} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
            {showCompare && (
              <linearGradient id={`grad-${compareGradientId}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={compareColor} stopOpacity={0.07} />
                <stop offset="95%" stopColor={compareColor} stopOpacity={0} />
              </linearGradient>
            )}
          </defs>
          <CartesianGrid {...chartGridProps} />
          <XAxis dataKey="date" tick={chartAxisTick} axisLine={false} tickLine={false} />
          <YAxis tick={chartAxisTick} axisLine={false} tickLine={false} />
          <Tooltip
            content={<KinexisChartTooltip />}
            cursor={{ stroke: "var(--border-default)", strokeWidth: 1 }}
          />
          <Area
            type="monotone"
            dataKey={metricName}
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#grad-${gradientId})`}
            name={label}
          />
          {showCompare && prevData.length > 0 && (
            <Line
              type="monotone"
              dataKey="compare"
              stroke={compareColor}
              strokeWidth={1.2}
              strokeDasharray="4 3"
              dot={false}
              connectNulls
              name={`Prev ${compareDays}d`}
            />
          )}
          {projData.length > 0 && chartData.length > 0 && (
            <ReferenceLine
              x={chartData[chartData.length - 1]?.date ?? ""}
              stroke="var(--border-default)"
              strokeDasharray="3 3"
              strokeWidth={1}
            />
          )}
          {projData.length > 0 && (
            <Line
              type="monotone"
              dataKey="projection"
              stroke={color}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              connectNulls
              name="Forecast"
            />
          )}
          {chartEvents.map((ev) => (
            <ReferenceArea
              key={ev.name}
              x1={ev.start}
              x2={ev.end}
              strokeOpacity={0}
              fill="var(--kinexis-signal)"
              fillOpacity={0.08}
              label={{
                value: ev.type === "core_update" ? "CU" : "S",
                position: "insideTopRight",
                fontSize: 9,
                fill: "var(--kinexis-signal)",
              }}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      {chartEvents.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {chartEvents.map((ev) => (
            <span
              key={ev.name}
              className="inline-flex items-center gap-1 rounded bg-kinexis-signal/10 px-2 py-0.5 text-[11px] text-kinexis-signal"
              title={`${ev.name}: ${ev.start} \u2013 ${ev.end}`}
            >
              {ev.type === "core_update" ? "Core Update" : "Seasonal"}: {ev.name}
            </span>
          ))}
        </div>
      )}
    </Panel>
  );
}

export default memo(DashboardChart);
