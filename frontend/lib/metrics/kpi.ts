import { Metric } from "@/lib/api";
import { seriesByDate, PAID_SOURCES } from "./series";

export type PeriodOption = "7d" | "30d" | "60d" | "90d" | "1y";

export type KpiSummary = {
  key: string;
  label: string;
  value: number;
  previous: number;
  changePct: number | null;
  format: "number" | "percent" | "decimal" | "currency";
  hint: string;
  source: string;
  target?: number;
};

export type KpiTarget = {
  key: string;
  target: number;
  label: string;
};

export const KPI_DEFAULTS: Record<string, KpiTarget> = {
  clicks: { key: "clicks", target: 500, label: "Monthly search clicks target" },
  impressions: { key: "impressions", target: 5000, label: "Monthly impressions target" },
  ctr: { key: "ctr", target: 0.04, label: "CTR target (4%)" },
  sessions: { key: "sessions", target: 400, label: "Monthly sessions target" },
  conversions: { key: "conversions", target: 20, label: "Monthly conversions target" },
  cvr: { key: "cvr", target: 0.05, label: "Conversion rate target (5%)" },
  leads: { key: "leads", target: 15, label: "Monthly leads target" },
  revenue: { key: "revenue", target: 10000, label: "Monthly revenue target" },
} as const;

function periodDateRange(days: number): {
  currentStart: string;
  currentEnd: string;
  prevStart: string;
  prevEnd: string;
} {
  return {
    currentStart: isoDaysAgo(days - 1),
    currentEnd: isoDaysAgo(0),
    prevStart: isoDaysAgo(days * 2 - 1),
    prevEnd: isoDaysAgo(days),
  };
}

function yoyDateRange(): {
  currentStart: string;
  currentEnd: string;
  prevStart: string;
  prevEnd: string;
} {
  const windowDays = 30;
  const maxLookback = 365;
  return {
    currentStart: isoDaysAgo(windowDays - 1),
    currentEnd: isoDaysAgo(0),
    prevStart: isoDaysAgo(maxLookback - 1),
    prevEnd: isoDaysAgo(maxLookback - windowDays),
  };
}

function sumInRange(series: { date: string; value: number }[], start: string, end: string): number {
  return series
    .filter((d) => d.date >= start && d.date <= end)
    .reduce((acc, d) => acc + d.value, 0);
}

function avgInRange(series: { date: string; value: number }[], start: string, end: string): number {
  const slice = series.filter((d) => d.date >= start && d.date <= end);
  if (slice.length === 0) return 0;
  return slice.reduce((acc, d) => acc + d.value, 0) / slice.length;
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function buildKpiSummaries(metrics: Metric[], period: PeriodOption = "7d"): KpiSummary[] {
  const isYoy = period === "1y";
  const days = isYoy
    ? 30
    : period === "30d"
      ? 30
      : period === "60d"
        ? 60
        : period === "90d"
          ? 90
          : 7;
  const { currentStart, currentEnd, prevStart, prevEnd } = isYoy
    ? yoyDateRange()
    : periodDateRange(days);
  const periodLabel = isYoy
    ? "last 30 days vs 1 year ago"
    : period === "30d"
      ? "last 30 days"
      : period === "60d"
        ? "last 60 days"
        : period === "90d"
          ? "last 90 days"
          : "last 7 days";

  const defs: {
    key: string;
    label: string;
    metricName: string;
    source: string;
    sources?: readonly string[];
    format: KpiSummary["format"];
    hint: string;
    aggregate: "sum" | "avg";
  }[] = [
    {
      key: "clicks",
      label: "Search Clicks",
      metricName: "clicks",
      source: "gsc",
      format: "number",
      hint: "Google Search clicks · last 7 days",
      aggregate: "sum",
    },
    {
      key: "impressions",
      label: "Impressions",
      metricName: "impressions",
      source: "gsc",
      format: "number",
      hint: "How often you showed in Google · last 7 days",
      aggregate: "sum",
    },
    {
      key: "ctr",
      label: "CTR",
      metricName: "ctr",
      source: "gsc",
      format: "percent",
      hint: "Click-through rate from search · last 7 days",
      aggregate: "avg",
    },
    {
      key: "sessions",
      label: "Sessions",
      metricName: "sessions",
      source: "ga4",
      format: "number",
      hint: "Site visits (GA4) · last 7 days",
      aggregate: "sum",
    },
    {
      key: "conversions",
      label: "Conversions",
      metricName: "key_events",
      source: "ga4",
      format: "number",
      hint: "Key events / conversions · last 7 days",
      aggregate: "sum",
    },
    {
      key: "bing_clicks",
      label: "Bing Clicks",
      metricName: "clicks",
      source: "bing",
      format: "number",
      hint: "Bing Search clicks · last 7 days",
      aggregate: "sum",
    },
    {
      key: "leads",
      label: "Leads",
      metricName: "leads",
      source: "hubspot",
      format: "number",
      hint: "New HubSpot leads · last 7 days",
      aggregate: "sum",
    },
    {
      key: "opportunities",
      label: "Opportunities",
      metricName: "opportunities",
      source: "hubspot",
      format: "number",
      hint: "New HubSpot opportunities · last 7 days",
      aggregate: "sum",
    },
    {
      key: "closed_won",
      label: "Deals Won",
      metricName: "closed_won",
      source: "hubspot",
      format: "number",
      hint: "Closed-won deals · last 7 days",
      aggregate: "sum",
    },
    {
      key: "revenue",
      label: "Revenue",
      metricName: "revenue",
      source: "hubspot",
      format: "currency",
      hint: "Closed revenue · last 7 days",
      aggregate: "sum",
    },
    {
      key: "ad_clicks",
      label: "Paid Clicks",
      metricName: "clicks",
      source: "paid",
      sources: PAID_SOURCES,
      format: "number",
      hint: "Paid ad clicks (all channels) · last 7 days",
      aggregate: "sum",
    },
    {
      key: "ad_conversions",
      label: "Ad Conversions",
      metricName: "conversions",
      source: "paid",
      sources: PAID_SOURCES,
      format: "number",
      hint: "Ad platform conversions (all channels) · last 7 days",
      aggregate: "sum",
    },
    {
      key: "ad_cost",
      label: "Ad Spend",
      metricName: "cost",
      source: "paid",
      sources: PAID_SOURCES,
      format: "currency",
      hint: "Paid media cost (all channels) · last 7 days",
      aggregate: "sum",
    },
    {
      key: "ad_value",
      label: "Ad Value",
      metricName: "conversion_value",
      source: "paid",
      sources: PAID_SOURCES,
      format: "currency",
      hint: "Ad conversion value (all channels) · last 7 days",
      aggregate: "sum",
    },
    {
      key: "google_ads_clicks",
      label: "GA Clicks",
      metricName: "clicks",
      source: "google_ads",
      format: "number",
      hint: "Google Ads clicks · last 7 days",
      aggregate: "sum",
    },
    {
      key: "meta_ads_clicks",
      label: "Meta Clicks",
      metricName: "clicks",
      source: "meta_ads",
      format: "number",
      hint: "Meta Ads clicks · last 7 days",
      aggregate: "sum",
    },
    {
      key: "google_ads_cost",
      label: "GA Spend",
      metricName: "cost",
      source: "google_ads",
      format: "currency",
      hint: "Google Ads spend · last 7 days",
      aggregate: "sum",
    },
    {
      key: "meta_ads_cost",
      label: "Meta Spend",
      metricName: "cost",
      source: "meta_ads",
      format: "currency",
      hint: "Meta Ads spend · last 7 days",
      aggregate: "sum",
    },
    {
      key: "google_ads_conversions",
      label: "GA Conv.",
      metricName: "conversions",
      source: "google_ads",
      format: "number",
      hint: "Google Ads conversions · last 7 days",
      aggregate: "sum",
    },
  ];

  const kpis: KpiSummary[] = defs.map((def) => {
    const series = seriesByDate(metrics, {
      metricName: def.metricName,
      source: def.sources ? undefined : def.source,
      sources: def.sources,
    });
    const value =
      def.aggregate === "avg"
        ? avgInRange(series, currentStart, currentEnd)
        : sumInRange(series, currentStart, currentEnd);
    const previous =
      def.aggregate === "avg"
        ? avgInRange(series, prevStart, prevEnd)
        : sumInRange(series, prevStart, prevEnd);
    const changePct = previous > 0 ? ((value - previous) / previous) * 100 : null;
    const target = KPI_DEFAULTS[def.key]?.target;

    return {
      key: def.key,
      label: def.label,
      value,
      previous,
      changePct,
      format: def.format,
      hint: def.hint.replace("last 7 days", periodLabel),
      source: def.source,
      target,
    };
  });

  const clicksKpi = kpis.find((k) => k.key === "clicks");
  const impsKpi = kpis.find((k) => k.key === "impressions");
  const ctrIdx = kpis.findIndex((k) => k.key === "ctr");
  if (clicksKpi && impsKpi && ctrIdx >= 0) {
    const value = impsKpi.value > 0 ? clicksKpi.value / impsKpi.value : 0;
    const previous = impsKpi.previous > 0 ? clicksKpi.previous / impsKpi.previous : 0;
    const ctrKpiEntry = kpis[ctrIdx];
    if (!ctrKpiEntry) return kpis.filter((k) => k.value > 0 || k.previous > 0);
    kpis[ctrIdx] = {
      ...ctrKpiEntry,
      value,
      previous,
      changePct: previous > 0 ? ((value - previous) / previous) * 100 : null,
    };
  }

  const sessions = kpis.find((k) => k.key === "sessions");
  const conversions = kpis.find((k) => k.key === "conversions");
  if (sessions && conversions) {
    const cvr = sessions.value > 0 ? conversions.value / sessions.value : 0;
    const prevCvr = sessions.previous > 0 ? conversions.previous / sessions.previous : 0;
    kpis.push({
      key: "cvr",
      label: "Conv. Rate",
      value: cvr,
      previous: prevCvr,
      changePct: prevCvr > 0 ? ((cvr - prevCvr) / prevCvr) * 100 : null,
      format: "percent",
      hint: `Conversions ÷ sessions · ${periodLabel}`,
      source: "ga4",
    });
  }

  return kpis.filter((k) => k.value > 0 || k.previous > 0);
}

export function formatKpiValue(value: number, format: KpiSummary["format"]): string {
  if (format === "percent") {
    const pct = value > 3 ? value : value * 100;
    return `${pct.toFixed(1)}%`;
  }
  if (format === "currency") {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return `$${Math.round(value).toLocaleString()}`;
  }
  if (format === "decimal") return value.toFixed(1);
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return Math.round(value).toLocaleString();
}
