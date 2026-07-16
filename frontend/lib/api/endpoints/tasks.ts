import { request } from "../client";
import type { Task, WeeklySummary } from "../types";

export const tasks = {
  list: (params?: { client_id?: number; status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.client_id) qs.set("client_id", String(params.client_id));
    if (params?.status) qs.set("status", params.status);
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.offset !== undefined) qs.set("offset", String(params.offset));
    const qStr = qs.toString();
    return request<Task[]>(`/tasks/${qStr ? "?" + qStr : ""}`);
  },
  create: (data: {
    client_id: number;
    insight_id?: number;
    assigned_to?: string;
    due_date?: string;
    result_notes?: string;
    brief_id?: number;
    lever_id?: number;
    playbook_pattern?: string;
    action_plan_id?: number;
    target_query?: string;
    target_url?: string;
  }) => request<Task>("/tasks/", { method: "POST", body: JSON.stringify(data) }),
  update: (taskId: number, data: Partial<Task>) =>
    request<Task>(`/tasks/${taskId}`, { method: "PUT", body: JSON.stringify(data) }),
  delete: (taskId: number) => request<{ ok: boolean }>(`/tasks/${taskId}`, { method: "DELETE" }),
};

export const summaries = {
  list: (params?: { client_id?: number }) => {
    const qs = new URLSearchParams();
    if (params?.client_id) qs.set("client_id", String(params.client_id));
    const qStr = qs.toString();
    return request<WeeklySummary[]>(`/summaries/${qStr ? "?" + qStr : ""}`);
  },
  generate: (clientId: number) =>
    request<{ status: string; summary_id?: number; message?: string }>(
      `/summaries/generate/${clientId}`,
      { method: "POST" },
      300000
    ),
  review: (summaryId: number) =>
    request<{ ok: boolean }>(`/summaries/${summaryId}/review`, { method: "PUT" }),
};
