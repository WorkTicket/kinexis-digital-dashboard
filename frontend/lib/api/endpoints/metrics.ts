import { request } from "../client";
import type { DataSource, Metric, Opportunities } from "../types";

export const metrics = {
  list: (params: {
    client_id: number;
    source?: string;
    start_date?: string;
    end_date?: string;
    metric_name?: string;
    /** Default true on the API — one dimension per multi-dim source. */
    site_totals_only?: boolean;
    /** Lookback days (default 90). Ignored when start_date is set. */
    days?: number;
  }) => {
    const qs = new URLSearchParams();
    qs.set("client_id", String(params.client_id));
    if (params.source) qs.set("source", params.source);
    if (params.start_date) qs.set("start_date", params.start_date);
    if (params.end_date) qs.set("end_date", params.end_date);
    if (params.metric_name) qs.set("metric_name", params.metric_name);
    if (params.site_totals_only === false) qs.set("site_totals_only", "false");
    if (params.days != null) qs.set("days", String(params.days));
    return request<Metric[]>(`/metrics/?${qs.toString()}`);
  },
  health: (clientId: number) =>
    request<{
      client_id: number;
      last_synced_at: string | null;
      has_errors: boolean;
      sources: DataSource[];
    }>(`/metrics/health/${clientId}`),
  sync: (clientId: number) =>
    request<{
      client_id: number;
      synced_at: string;
      results: Record<string, string>;
      sources?: DataSource[];
      insights_created?: number;
      new_insights?: { id: number; type: string; severity: string; message: string }[];
    }>(`/metrics/sync/${clientId}`, { method: "POST" }, 120000),
  syncAll: () =>
    request<{
      queued?: boolean;
      client_count?: number;
      client_ids?: number[];
      message?: string;
      synced_at?: string;
      clients?: {
        client_id: number;
        name: string;
        results?: Record<string, string>;
        insights_created?: number;
        error?: string;
      }[];
    }>("/metrics/sync-all", { method: "POST" }, 300000),
  opportunities: (clientId: number, days = 28) =>
    request<Opportunities>(`/metrics/opportunities/${clientId}?days=${days}`),
};
