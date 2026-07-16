import { request } from "../client";
import type { KeywordHistory, RankingsReport } from "../types";

export const rankings = {
  get: (
    clientId: number,
    opts?: {
      days?: number;
      bucket?: string;
      q?: string;
      tracked_only?: boolean;
      brand?: "all" | "brand" | "non_brand";
      limit?: number;
    }
  ) => {
    const qs = new URLSearchParams();
    if (opts?.days) qs.set("days", String(opts.days));
    if (opts?.bucket && opts.bucket !== "all") qs.set("bucket", opts.bucket);
    if (opts?.q) qs.set("q", opts.q);
    if (opts?.tracked_only) qs.set("tracked_only", "true");
    if (opts?.brand && opts.brand !== "all") qs.set("brand", opts.brand);
    if (opts?.limit) qs.set("limit", String(opts.limit));
    const qStr = qs.toString();
    return request<RankingsReport>(`/rankings/${clientId}${qStr ? `?${qStr}` : ""}`);
  },
  history: (clientId: number, keyword: string, days = 90) => {
    const qs = new URLSearchParams({ keyword, days: String(days) });
    return request<KeywordHistory>(`/rankings/${clientId}/history?${qs}`);
  },
  track: (clientId: number, data: { keyword: string; target_url?: string; notes?: string }) =>
    request<{
      id: number;
      keyword: string;
      target_url: string | null;
      notes: string | null;
      created_at: string | null;
    }>(`/rankings/${clientId}/tracked`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  untrack: (clientId: number, trackedId: number) =>
    request<{ ok: boolean }>(`/rankings/${clientId}/tracked/${trackedId}`, {
      method: "DELETE",
    }),
  listTracked: (clientId: number) =>
    request<
      {
        id: number;
        keyword: string;
        target_url: string | null;
        notes: string | null;
        created_at: string | null;
      }[]
    >(`/rankings/${clientId}/tracked`),
  serp: (clientId: number, opts?: { query?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (opts?.query) qs.set("query", opts.query);
    if (opts?.limit) qs.set("limit", String(opts.limit));
    const qStr = qs.toString();
    return request<{
      enabled: boolean;
      snapshots: {
        id: number;
        query: string;
        provider: string | null;
        fetched_at: string | null;
        results: { position?: number; url?: string; title?: string; snippet?: string }[];
      }[];
    }>(`/rankings/${clientId}/serp${qStr ? `?${qStr}` : ""}`);
  },
  refreshSerp: (clientId: number, keyword?: string) => {
    const qs = keyword ? `?keyword=${encodeURIComponent(keyword)}` : "";
    return request<{
      ok: boolean;
      count?: number;
      snapshot?: unknown;
      snapshots?: unknown[];
    }>(`/rankings/${clientId}/serp/refresh${qs}`, { method: "POST" });
  },
};
