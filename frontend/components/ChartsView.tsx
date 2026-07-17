"use client";

import { useState, useMemo, useEffect } from "react";
import DashboardChart, { type KnownEventOverlay } from "@/components/DashboardChart";
import { Metric, api } from "@/lib/api";
import { downloadCSV } from "@/lib/utils";
import { seriesByDate, PAID_SOURCES } from "@/lib/metrics";
import { CHART } from "@/lib/chartTheme";
import { Download, Layers, TrendingUp, GitCompare } from "lucide-react";
import { Panel } from "@/components/ui/Panel";
import { Stat } from "@/components/ui/Stat";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import type { PeriodOption } from "@/lib/metrics";

type TrendDef = {
  metricName: string;
  label: string;
  color: string;
  source?: string;
  sources?: readonly string[];
};

const TREND_DEFS: TrendDef[] = [
  { metricName: "clicks", label: "Clicks (GSC)", color: CHART.focus, source: "gsc" },
  { metricName: "impressions", label: "Impressions (GSC)", color: CHART.focusSoft, source: "gsc" },
  { metricName: "sessions", label: "Sessions (GA4)", color: CHART.focusSoft, source: "ga4" },
  { metricName: "key_events", label: "Conversions (GA4)", color: CHART.proof, source: "ga4" },
  { metricName: "ctr", label: "CTR (GSC)", color: CHART.focus, source: "gsc" },
  { metricName: "position", label: "Avg Position (GSC)", color: CHART.mist, source: "gsc" },
  { metricName: "clicks", label: "Paid Clicks", color: CHART.momentum, sources: PAID_SOURCES },
  {
    metricName: "conversions",
    label: "Ad Conversions",
    color: CHART.focusSoft,
    sources: PAID_SOURCES,
  },
  {
    metricName: "sov_presence",
    label: "Share of Voice",
    color: CHART.mist,
    source: "serp",
  },
];

const PERIODS: { value: PeriodOption; label: string }[] = [
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "60d", label: "60d" },
  { value: "90d", label: "90d" },
  { value: "1y", label: "YoY" },
];

const COMPARE_OPTIONS = [
  { value: 0, label: "Off" },
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
] as const;

const GRID_SIZES = ["2-col", "3-col", "4-col"] as const;

type Props = {
  metrics: Metric[];
  clientId?: number;
};

export default function ChartsView({ metrics, clientId }: Props) {
  const [period, setPeriod] = useState<PeriodOption>("30d");
  const [showProjection, setShowProjection] = useState(false);
  const [compareDays, setCompareDays] = useState<number>(0);
  const [gridSize, setGridSize] = useState<(typeof GRID_SIZES)[number]>("2-col");
  const [events, setEvents] = useState<KnownEventOverlay[]>([]);

  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    api.actions
      .getKnownEvents(clientId)
      .then((data) => {
        if (!cancelled && data.events) setEvents(data.events);
      })
      .catch((e) => {
        console.warn("Known events fetch failed", e);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const lookbackDays = useMemo(() => {
    if (period === "1y") return 365;
    if (period === "90d") return 90;
    if (period === "60d") return 60;
    if (period === "30d") return 30;
    return 7;
  }, [period]);

  const liveTrends = useMemo(
    () =>
      TREND_DEFS.filter(
        (t) =>
          seriesByDate(metrics, {
            metricName: t.metricName,
            source: t.sources ? undefined : t.source,
            sources: t.sources,
            lookbackDays,
          }).length > 0
      ),
    [metrics, lookbackDays]
  );

  const primaryTrends = liveTrends.slice(0, 6);
  const extraTrends = liveTrends.slice(6);

  const gridClass = useMemo(() => {
    switch (gridSize) {
      case "3-col":
        return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";
      case "4-col":
        return "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4";
      default:
        return "grid-cols-1 lg:grid-cols-2";
    }
  }, [gridSize]);

  const totalMetrics = useMemo(() => {
    if (metrics.length === 0) return null;
    const latestDate = [...new Set(metrics.map((m) => m.date))].sort().pop();
    const recent = latestDate ? metrics.filter((m) => m.date === latestDate) : metrics;

    const clicks = recent
      .filter((m) => m.source === "gsc" && m.metric_name === "clicks")
      .reduce((s, m) => s + m.value, 0);
    const sessions = recent
      .filter((m) => m.source === "ga4" && m.metric_name === "sessions")
      .reduce((s, m) => s + m.value, 0);
    const conversions = recent
      .filter((m) => m.source === "ga4" && m.metric_name === "key_events")
      .reduce((s, m) => s + m.value, 0);

    return { clicks, sessions, conversions };
  }, [metrics]);

  const exportChartsCSV = () => {
    if (!totalMetrics) return;
    const headers = ["Metric", "Latest Value"];
    const rows = [
      `"Clicks (GSC)",${totalMetrics.clicks}`,
      `"Sessions (GA4)",${totalMetrics.sessions}`,
      `"Conversions (GA4)",${totalMetrics.conversions}`,
      `"Series count",${liveTrends.length}`,
    ];
    downloadCSV("kinexis-charts", headers, rows);
  };

  return (
    <div className="animate-fade-up space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-lg bg-surface-border/30 p-0.5">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setPeriod(p.value)}
              className={`rounded-md px-3 py-1 text-[12px] font-medium transition-all duration-micro ${
                period === p.value
                  ? "bg-surface-elevated text-ink shadow-panel"
                  : "text-muted hover:text-ink-secondary"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <SegmentedControl
            size="sm"
            ariaLabel="Grid size"
            value={gridSize}
            onChange={(g) => setGridSize(g as (typeof GRID_SIZES)[number])}
            options={GRID_SIZES.map((g) => ({ id: g, label: g }))}
          />
          <button
            type="button"
            onClick={() => setShowProjection((p) => !p)}
            className={`rounded-md px-3 py-1 text-[11px] font-medium transition-all duration-micro ${
              showProjection
                ? "bg-kinexis-focus/10 text-kinexis-focus"
                : "text-muted hover:text-ink-secondary"
            }`}
          >
            <TrendingUp size={10} className="mr-1 inline" />
            {showProjection ? "Hide forecast" : "Forecast"}
          </button>
          <div className="flex rounded-lg bg-surface-border/30 p-0.5">
            {COMPARE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setCompareDays(opt.value)}
                className={`rounded-md px-2 py-1 text-[11px] font-medium transition-all duration-micro ${
                  compareDays === opt.value
                    ? "bg-surface-elevated text-ink shadow-panel"
                    : "text-muted hover:text-ink-secondary"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {totalMetrics && (
            <button
              type="button"
              onClick={exportChartsCSV}
              className="text-muted rounded-md px-2 py-1 text-[11px] font-medium hover:text-ink-secondary"
              title="Export chart data as CSV"
            >
              <Download size={11} className="mr-0.5 inline" />
              Export
            </button>
          )}
        </div>
      </div>

      {compareDays > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-kinexis-focus/20 bg-kinexis-focus/5 px-3 py-2 text-xs text-ink-secondary">
          <GitCompare size={12} className="text-kinexis-focus" />
          Comparing current period with {compareDays}d prior — dashed line shows the previous period
        </div>
      )}

      {liveTrends.length === 0 && (
        <Panel padding="lg" className="!border-dashed text-center">
          <Layers size={20} className="text-muted mx-auto mb-2" />
          <p className="text-[13px] font-medium text-ink">No trend data yet</p>
          <p className="text-muted mt-1 text-xs">Sync data connectors to see performance charts.</p>
        </Panel>
      )}

      {totalMetrics && liveTrends.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          <Stat
            label="Latest clicks"
            value={totalMetrics.clicks.toLocaleString()}
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
          <Stat
            label="Latest sessions"
            value={totalMetrics.sessions.toLocaleString()}
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
          <Stat
            label="Latest conversions"
            value={totalMetrics.conversions.toLocaleString()}
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
        </div>
      )}

      {liveTrends.length > 0 && (
        <div>
          <p className="text-muted mb-4 text-xs">
            {liveTrends.length} series
            {extraTrends.length > 0 && " · showing top 6"}
          </p>
          <div className={`grid ${gridClass} gap-3`}>
            {primaryTrends.map((t) => (
              <DashboardChart
                key={`${t.source || "paid"}-${t.metricName}-${t.label}-${lookbackDays}`}
                metrics={metrics}
                metricName={t.metricName}
                label={t.label}
                color={t.color}
                source={t.source}
                sources={t.sources}
                projectionDays={showProjection ? 30 : 0}
                lookbackDays={lookbackDays}
                compareDays={compareDays > 0 ? compareDays : 0}
                events={events.length > 0 ? events : undefined}
              />
            ))}
          </div>
          {extraTrends.length > 0 && (
            <CollapsibleSection label={`${extraTrends.length} more series`} className="!mt-2">
              <div className={`grid ${gridClass} gap-3`}>
                {extraTrends.map((t) => (
                  <DashboardChart
                    key={`${t.source || "paid"}-${t.metricName}-${t.label}-${lookbackDays}-extra`}
                    metrics={metrics}
                    metricName={t.metricName}
                    label={t.label}
                    color={t.color}
                    source={t.source}
                    sources={t.sources}
                    projectionDays={showProjection ? 30 : 0}
                    lookbackDays={lookbackDays}
                    compareDays={compareDays > 0 ? compareDays : 0}
                    events={events.length > 0 ? events : undefined}
                  />
                ))}
              </div>
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  );
}
