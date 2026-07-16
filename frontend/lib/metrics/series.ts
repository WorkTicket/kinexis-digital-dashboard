import { Metric } from "@/lib/api";

export const SITE_TOTAL_DIMENSION: Record<string, string | null> = {
  gsc: "device",
  bing: "query",
  ga4: "landing_page",
  ads_csv: "campaign",
  google_ads: "campaign",
  meta_ads: "campaign",
  backlinks: null,
  gbp: null,
  crux: null,
  serp: null,
};

export const AVG_METRICS = new Set([
  "ctr",
  "position",
  "bounce_rate",
  "scroll_depth",
  "sov_presence",
  "sov_loss_rate",
  "frequency",
]);

export const PAID_SOURCES = ["ads_csv", "google_ads", "meta_ads"] as const;

type SeriesPoint = { date: string; value: number };

function isEmptyDim(dimensionType: string | null | undefined): boolean {
  return dimensionType == null || dimensionType === "";
}

function isSiteLevelRow(m: Metric): boolean {
  const preferred = SITE_TOTAL_DIMENSION[m.source];
  if (preferred === undefined) return true;
  if (preferred === null) return isEmptyDim(m.dimension_type);
  // Accept true site totals ("") and the preferred breakdown dim
  return isEmptyDim(m.dimension_type) || m.dimension_type === preferred;
}

export function filterMetricsByDimension(
  metrics: Metric[],
  dimensionType: string,
  dimensionValue?: string
): Metric[] {
  if (!dimensionValue) {
    return metrics.filter((m) => m.dimension_type === dimensionType || m.dimension_type == null);
  }
  return metrics.filter(
    (m) =>
      (m.dimension_type === dimensionType && m.dimension_value === dimensionValue) ||
      m.dimension_type == null
  );
}

export function getUniqueDimensionValues(metrics: Metric[], dimensionType: string): string[] {
  const values = new Set<string>();
  for (const m of metrics) {
    if (m.dimension_type === dimensionType && m.dimension_value) {
      values.add(m.dimension_value);
    }
  }
  return [...values].sort();
}

export function linearRegression(
  points: { x: number; y: number }[]
): { slope: number; intercept: number; r2: number } | null {
  const n = points.length;
  if (n < 3) return null;
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0,
    sumY2 = 0;
  for (const p of points) {
    sumX += p.x;
    sumY += p.y;
    sumXY += p.x * p.y;
    sumX2 += p.x * p.x;
    sumY2 += p.y * p.y;
  }
  const denom = n * sumX2 - sumX * sumX;
  if (denom === 0) return null;
  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  const meanY = sumY / n;
  const ssRes = points.reduce((s, p) => s + (p.y - (slope * p.x + intercept)) ** 2, 0);
  const ssTot = points.reduce((s, p) => s + (p.y - meanY) ** 2, 0);
  const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 0;
  return { slope, intercept, r2 };
}

export function generateProjection(series: SeriesPoint[], projectionDays: number): SeriesPoint[] {
  if (series.length === 0 || projectionDays <= 0) return [];
  const projections: SeriesPoint[] = [];
  const lastPoint = series[series.length - 1];
  if (!lastPoint) return [];
  const lastDate = new Date(lastPoint.date + "T00:00:00");

  function makeDate(i: number): string {
    const d = new Date(lastDate);
    d.setDate(d.getDate() + i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  if (series.length >= 3) {
    const points = series.map((p, i) => ({ x: i, y: p.value }));
    const reg = linearRegression(points);
    if (reg && reg.r2 >= 0.3) {
      for (let i = 1; i <= projectionDays; i++) {
        const predicted = Math.max(0, reg.slope * (points.length + i - 1) + reg.intercept);
        projections.push({ date: makeDate(i), value: Math.round(predicted * 100) / 100 });
      }
      return projections;
    }
  }

  if (series.length >= 2) {
    const firstVal = series[0]?.value ?? 0;
    const lastVal = series[series.length - 1]?.value ?? 0;
    const slope = (lastVal - firstVal) / series.length;
    for (let i = 1; i <= projectionDays; i++) {
      const predicted = Math.max(0, lastVal + slope * i);
      projections.push({ date: makeDate(i), value: Math.round(predicted * 100) / 100 });
    }
    return projections;
  }

  const recentAvg =
    series.slice(-Math.min(series.length, 7)).reduce((s, p) => s + p.value, 0) /
    Math.min(series.length, 7);
  for (let i = 1; i <= projectionDays; i++) {
    projections.push({ date: makeDate(i), value: Math.round(recentAvg * 100) / 100 });
  }
  return projections;
}

export function buildPageMetrics(
  metrics: Metric[],
  periodDays = 30
): {
  url: string;
  clicks: number;
  impressions: number;
  ctr: number;
  sessions: number;
  conversions: number;
  cvr: number;
}[] {
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - periodDays);
  const cutoffStr = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, "0")}-${String(cutoff.getDate()).padStart(2, "0")}`;

  const pageMap = new Map<
    string,
    {
      clicks: number;
      impressions: number;
      sessions: number;
      conversions: number;
    }
  >();

  for (const m of metrics) {
    if (m.date < cutoffStr) continue;
    if (m.dimension_type !== "landing_page" || !m.dimension_value) continue;
    const init = { clicks: 0, impressions: 0, sessions: 0, conversions: 0 };
    if (!pageMap.has(m.dimension_value)) {
      pageMap.set(m.dimension_value, init);
    }
    const entry = pageMap.get(m.dimension_value) ?? init;
    if (m.metric_name === "clicks" && (m.source === "gsc" || m.source === "bing")) {
      entry.clicks += m.value;
    } else if (m.metric_name === "impressions") {
      entry.impressions += m.value;
    } else if (m.metric_name === "sessions" && m.source === "ga4") {
      entry.sessions += m.value;
    } else if (m.metric_name === "key_events" && m.source === "ga4") {
      entry.conversions += m.value;
    }
  }

  const results: ReturnType<typeof buildPageMetrics> = [];
  for (const [url, data] of pageMap) {
    if (data.clicks === 0 && data.impressions === 0 && data.sessions === 0) continue;
    results.push({
      url,
      clicks: data.clicks,
      impressions: data.impressions,
      ctr: data.impressions > 0 ? data.clicks / data.impressions : 0,
      sessions: data.sessions,
      conversions: data.conversions,
      cvr: data.sessions > 0 ? data.conversions / data.sessions : 0,
    });
  }
  results.sort((a, b) => b.clicks - a.clicks);
  return results;
}

function seriesKey(source: string, metricName: string): string {
  return `${source}\0${metricName}`;
}

function buildSeriesMap(metrics: Metric[]): Map<string, SeriesPoint[]> {
  // When both preferred-dim and empty site totals exist for a date, prefer preferred
  // so we never double-count (e.g. GSC device + site "").
  const preferredDates = new Set<string>();
  for (const m of metrics) {
    const preferred = SITE_TOTAL_DIMENSION[m.source];
    if (preferred && m.dimension_type === preferred) {
      preferredDates.add(`${m.source}\0${m.metric_name}\0${m.date}`);
    }
  }

  const buckets = new Map<string, Map<string, { sum: number; count: number }>>();

  for (const m of metrics) {
    if (!isSiteLevelRow(m)) continue;
    const preferred = SITE_TOTAL_DIMENSION[m.source];
    if (preferred && isEmptyDim(m.dimension_type)) {
      if (preferredDates.has(`${m.source}\0${m.metric_name}\0${m.date}`)) continue;
    }
    const key = seriesKey(m.source, m.metric_name);
    let byDate = buckets.get(key);
    if (!byDate) {
      byDate = new Map();
      buckets.set(key, byDate);
    }
    const cur = byDate.get(m.date) || { sum: 0, count: 0 };
    cur.sum += m.value;
    cur.count += 1;
    byDate.set(m.date, cur);
  }

  const out = new Map<string, SeriesPoint[]>();
  for (const [key, byDate] of buckets) {
    const metricName = key.split("\0")[1] || "";
    const useAvg = AVG_METRICS.has(metricName);
    const series = Array.from(byDate.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, { sum, count }]) => ({
        date,
        value: useAvg && count > 0 ? sum / count : sum,
      }));
    out.set(key, series);
  }

  for (const source of Object.keys(SITE_TOTAL_DIMENSION)) {
    const clicks = out.get(seriesKey(source, "clicks"));
    const imps = out.get(seriesKey(source, "impressions"));
    if (!clicks?.length || !imps?.length) continue;
    const impsByDate = new Map(imps.map((p) => [p.date, p.value]));
    out.set(
      seriesKey(source, "ctr"),
      clicks.map((p) => {
        const denom = impsByDate.get(p.date) || 0;
        return { date: p.date, value: denom > 0 ? p.value / denom : 0 };
      })
    );
  }

  return out;
}

export function filterSiteMetrics(
  metrics: Metric[],
  opts: { metricName: string; source?: string }
): Metric[] {
  return metrics.filter((m) => {
    if (m.metric_name !== opts.metricName) return false;
    if (opts.source && m.source !== opts.source) return false;
    if (!opts.source) {
      if (["clicks", "impressions", "ctr", "position"].includes(opts.metricName)) {
        if (m.source === "gsc" || m.source === "bing") return isSiteLevelRow(m);
      }
    }
    return isSiteLevelRow(m);
  });
}

export function seriesByDate(
  metrics: Metric[],
  opts: { metricName: string; source?: string; sources?: readonly string[]; lookbackDays?: number }
): SeriesPoint[] {
  const map = buildSeriesMap(metrics);
  let result: SeriesPoint[];

  if (opts.sources?.length) {
    const merged = new Map<string, { sum: number; count: number }>();
    for (const source of opts.sources) {
      const series = map.get(seriesKey(source, opts.metricName)) || [];
      for (const p of series) {
        const cur = merged.get(p.date) || { sum: 0, count: 0 };
        cur.sum += p.value;
        cur.count += 1;
        merged.set(p.date, cur);
      }
    }
    const useAvg = AVG_METRICS.has(opts.metricName);
    result = Array.from(merged.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, { sum, count }]) => ({
        date,
        value: useAvg && count > 0 ? sum / count : sum,
      }));
  } else if (opts.source) {
    result = map.get(seriesKey(opts.source, opts.metricName)) || [];
  } else {
    const merged = new Map<string, { sum: number; count: number }>();
    for (const [key, series] of map) {
      const [, name] = key.split("\0");
      if (name !== opts.metricName) continue;
      for (const p of series) {
        const cur = merged.get(p.date) || { sum: 0, count: 0 };
        cur.sum += p.value;
        cur.count += 1;
        merged.set(p.date, cur);
      }
    }
    const useAvg = AVG_METRICS.has(opts.metricName);
    result = Array.from(merged.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, { sum, count }]) => ({
        date,
        value: useAvg && count > 0 ? sum / count : sum,
      }));
  }

  if (opts.lookbackDays != null && opts.lookbackDays > 0) {
    const cutoff = isoDaysAgo(opts.lookbackDays);
    result = result.filter((p) => p.date >= cutoff);
  }

  return result;
}

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
