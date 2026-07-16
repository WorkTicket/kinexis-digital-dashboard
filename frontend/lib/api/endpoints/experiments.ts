import { request } from "../client";

export type Experiment = {
  id: number;
  client_id: number;
  task_id?: number | null;
  recommendation_id?: number | null;
  hypothesis: string;
  control?: string | null;
  treatment?: string | null;
  success_metric?: string | null;
  status: string;
  start_at?: string | null;
  end_at?: string | null;
  outcome_lift_pct?: number | null;
  notes?: string | null;
  created_at?: string | null;
};

export type ExperimentCreate = {
  client_id: number;
  hypothesis: string;
  control?: string;
  treatment?: string;
  success_metric?: string;
  task_id?: number;
  recommendation_id?: number;
  status?: string;
  notes?: string;
};

export const experiments = {
  list: (opts?: { client_id?: number; status?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.client_id != null) params.set("client_id", String(opts.client_id));
    if (opts?.status) params.set("status", opts.status);
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    const q = params.toString();
    return request<Experiment[]>(q ? `/experiments/?${q}` : "/experiments/");
  },
  create: (body: ExperimentCreate) =>
    request<Experiment>("/experiments/", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (
    id: number,
    body: Partial<{
      hypothesis: string;
      control: string;
      treatment: string;
      success_metric: string;
      status: string;
      outcome_lift_pct: number;
      notes: string;
    }>
  ) =>
    request<Experiment>(`/experiments/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: number) => request<{ ok: boolean }>(`/experiments/${id}`, { method: "DELETE" }),
};
