import { API_BASE, getApiHeaders, request } from "../client";
import type { Insight } from "../types";

export const insights = {
  list: (params?: {
    client_id?: number;
    resolved?: boolean;
    kind?: "problem" | "opportunity" | "all";
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.client_id) qs.set("client_id", String(params.client_id));
    if (params?.resolved !== undefined) qs.set("resolved", String(params.resolved));
    if (params?.kind && params.kind !== "all") qs.set("kind", params.kind);
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const qStr = qs.toString();
    return request<Insight[]>(`/insights/${qStr ? "?" + qStr : ""}`);
  },
  generate: (clientId: number) =>
    request<{ insights_generated: number }>(`/insights/generate/${clientId}`, { method: "POST" }),
  resolve: (insightId: number, resolve_reason?: "shipped" | "wont_fix" | "user" | "duplicate") =>
    request<{ ok: boolean; resolve_reason?: string }>(`/insights/${insightId}/resolve`, {
      method: "PUT",
      body: JSON.stringify({ resolve_reason: resolve_reason || "user" }),
    }),
  unresolve: (insightId: number) =>
    request<{ ok: boolean }>(`/insights/${insightId}/unresolve`, { method: "PUT" }),
  downloadAgentFixMd: async (
    clientId: number,
    opts?: {
      severity?: "high" | "medium" | "low" | "all";
      kind?: "problem" | "opportunity" | "all";
    }
  ) => {
    const qs = new URLSearchParams();
    if (opts?.severity && opts.severity !== "all") qs.set("severity", opts.severity);
    if (opts?.kind && opts.kind !== "all") qs.set("kind", opts.kind);
    const qStr = qs.toString();
    const res = await fetch(`${API_BASE}/insights/agent-md/${clientId}${qStr ? `?${qStr}` : ""}`, {
      headers: await getApiHeaders(),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`${res.status}: ${err}`);
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = /filename="?([^"]+)"?/.exec(cd);
    const filename = match?.[1] || `kinexis-agent-fix-brief-${clientId}.md`;
    const url = URL.createObjectURL(blob);
    if (typeof document !== "undefined") {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
  importShipLog: (
    clientId: number,
    data: { markdown: string; mark_done?: boolean; assigned_to?: string }
  ) =>
    request<{
      status: string;
      message: string;
      applied: {
        fix_id: number;
        task_id: number;
        created: boolean;
        status: string;
        baselines_captured: number;
        title?: string;
      }[];
      errors?: string[];
    }>(`/insights/ship-log/${clientId}`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const notifications = {
  pending: () =>
    request<{
      items: {
        id: number;
        client_id: number;
        insight_id: number | null;
        severity: string;
        title: string;
        body: string;
        created_at: string | null;
      }[];
    }>("/insights/notifications/pending"),
  markDelivered: (ids: number[]) =>
    request<{ ok: boolean }>("/insights/notifications/delivered", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
};
